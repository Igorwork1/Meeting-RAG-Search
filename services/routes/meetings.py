"""HTTP-роуты: полный пайплайн встречи (транскрибация → БД), в фоне."""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile

from services.db import save_meeting_record
from services.job_progress import JobProgress, build_steps
from services.transcribe import DEFAULT_CHUNK_SECONDS, transcribe_file

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

# job_id → статус задачи (в памяти, пока крутится uvicorn)
_JOBS: dict[str, dict[str, Any]] = {}


def _process_meeting_sync(
    job_id: str,
    audio_path: str,
    meta: dict[str, str],
    *,
    chunk_seconds: int,
    file_name: str | None,
) -> dict[str, Any]:
    """Тяжёлая синхронная работа: транскрибация → суммаризация → БД."""
    progress = JobProgress(_JOBS, job_id)
    on_progress = progress.callback()

    try:
        transcript = transcribe_file(
            audio_path,
            chunk_seconds=chunk_seconds,
            on_progress=on_progress,
        )
        saved = save_meeting_record(
            transcript,
            meta,
            file_name=file_name,
            on_progress=on_progress,
        )
        progress.set_stage("done", "Обработка завершена")
        return {
            "status": "done",
            "id": saved["id"],
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "chunks_saved": saved.get("chunks_saved", 0),
        }
    finally:
        try:
            os.unlink(audio_path)
        except OSError:
            pass


async def _run_job(
    job_id: str,
    audio_path: str,
    meta: dict[str, str],
    *,
    chunk_seconds: int,
    file_name: str | None,
) -> None:
    """Фоновая задача — не блокирует ответ API."""
    progress = JobProgress(_JOBS, job_id)
    progress.set_stage("loading_model", "Подготовка к обработке…")
    try:
        result = await asyncio.to_thread(
            _process_meeting_sync,
            job_id,
            audio_path,
            meta,
            chunk_seconds=chunk_seconds,
            file_name=file_name,
        )
        _JOBS[job_id].update(result)
    except Exception as e:
        stage = _JOBS.get(job_id, {}).get("stage", "transcribing")
        progress.set_stage(stage, str(e), failed=True)
        _JOBS[job_id]["error"] = str(e)


@router.post("/process")
async def process_meeting(
    file: UploadFile = File(...),
    date: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    participants: str = Form(""),
    chunk_seconds: int = Form(DEFAULT_CHUNK_SECONDS),
):
    """
    Принимает файл и сразу отдаёт job_id.
    Обработка идёт в фоне — можно уйти со страницы и пользоваться чатом.
    """
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        audio_path = tmp.name

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    meta = {
        "date": date,
        "title": title,
        "description": description,
        "participants": participants,
        "file_name": file.filename or "",
    }

    progress = JobProgress(_JOBS, job_id)
    _JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "title": title,
        "date": date,
        "file_name": file.filename or "",
        "created_at": time.time(),
    }
    progress.set_stage("queued", "Файл принят, ожидает обработки")

    asyncio.create_task(
        _run_job(
            job_id,
            audio_path,
            meta,
            chunk_seconds=chunk_seconds,
            file_name=file.filename,
        )
    )

    job = _JOBS[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "title": title,
        "date": date,
        "stage": job.get("stage"),
        "stage_label": job.get("stage_label"),
        "steps": job.get("steps", build_steps("queued")),
        "progress_percent": job.get("progress_percent", 0),
    }


@router.get("/jobs")
async def list_jobs():
    """Список всех фоновых задач (новые первыми)."""
    jobs = sorted(
        _JOBS.values(),
        key=lambda j: j.get("created_at", 0),
        reverse=True,
    )
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Статус фоновой задачи: queued | processing | done | failed + этапы."""
    job = _JOBS.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "not_found"}
    return job

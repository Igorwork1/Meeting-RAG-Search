# services/api.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import uuid
import time

# ====== Заглушечное "хранилище" ======
# job_id -> {"created_at": float, "meta":..., "file":...}
_JOBS: Dict[str, Dict[str, Any]] = {}

# Этапы и длительности (сек) — просто имитация
_STAGES = [
    ("uploading", 4),
    ("transcribing", 12),
    ("summarizing", 6),
    ("indexing", 6),
]
_TOTAL = sum(d for _, d in _STAGES)


@dataclass
class UploadMeta:
    date: str
    title: str
    description: str = ""


def upload_audio(file_name: str, file_bytes: bytes, mime_type: str, meta: UploadMeta) -> str:
    """Создаёт job и "запускает" процесс (по времени)."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _JOBS[job_id] = {
        "created_at": time.time(),
        "meta": {"date": meta.date, "title": meta.title, "description": meta.description},
        "file": {"name": file_name, "mime": mime_type, "size": len(file_bytes)},
    }
    return job_id


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Возвращает статус/этап/прогресс по прошедшему времени."""
    job = _JOBS.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "not_found"}

    elapsed = time.time() - job["created_at"]

    # вычисляем текущий этап
    acc = 0
    stage = "queued"
    stage_idx = 0
    stage_progress = 0.0

    for i, (name, dur) in enumerate(_STAGES, start=1):
        if elapsed < acc + dur:
            stage = name
            stage_idx = i
            stage_progress = max(0.0, min(1.0, (elapsed - acc) / dur))
            break
        acc += dur
    else:
        # всё завершилось
        return {
            "job_id": job_id,
            "status": "done",
            "stage": "done",
            "stage_index": len(_STAGES),
            "stage_total": len(_STAGES),
            "progress": 1.0,
            "meta": job["meta"],
            "file": job["file"],
            "result": {
                "transcript_preview": "Заглушка транскрипта (процесс завершён).",
                "chunks_indexed": 12,
            },
        }

    # общий прогресс
    overall = max(0.0, min(1.0, elapsed / _TOTAL))

    return {
        "job_id": job_id,
        "status": "processing",
        "stage": stage,
        "stage_index": stage_idx,
        "stage_total": len(_STAGES),
        "progress": overall,
        "stage_progress": stage_progress,
        "meta": job["meta"],
        "file": job["file"],
    }


def chat(message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Заглушка чата — как было."""
    conv_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    answer = f"Got it: {message}"
    quotes = ["«Заглушка цитаты #1…»", "«Заглушка цитаты #2…»"]
    return {"conversation_id": conv_id, "answer": answer, "quotes": quotes}
"""HTTP-роуты транскрибации."""
from __future__ import annotations

from pathlib import Path
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile

from services.transcribe import DEFAULT_CHUNK_SECONDS, transcribe_file

router = APIRouter(prefix="/api", tags=["transcribe"])


@router.post("/transcribe")
async def api_transcribe(
    file: UploadFile = File(...),
    date: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    participants: str = Form(""),
    chunk_seconds: int = Form(DEFAULT_CHUNK_SECONDS),
):
    """Только транскрибация аудио → текст."""
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        audio_path = tmp.name

    try:
        transcript = transcribe_file(audio_path, chunk_seconds=chunk_seconds)
    finally:
        try:
            os.unlink(audio_path)
        except OSError:
            pass

    return {
        "status": "done",
        "meta": {
            "date": date,
            "title": title,
            "description": description,
            "participants": participants,
            "file_name": file.filename,
        },
        "transcript": transcript,
    }

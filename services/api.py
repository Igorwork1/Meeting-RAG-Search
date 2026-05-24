# HTTP-клиент для FastAPI-бэкенда (services/main.py).
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = (
    os.getenv("TRANSCRIBE_API_URL")
    or os.getenv("API_URL")
    or "http://127.0.0.1:8000"
).rstrip("/")

TRANSCRIBE_TIMEOUT_SEC = float(os.getenv("TRANSCRIBE_TIMEOUT_SEC", "7200"))
CHAT_TIMEOUT_SEC = float(os.getenv("CHAT_TIMEOUT_SEC", "120"))


@dataclass
class UploadMeta:
    date: str
    title: str
    description: str = ""
    participants: str = ""


def _upload_form(
    file_name: str,
    file_bytes: bytes,
    mime_type: str,
    meta: UploadMeta,
    *,
    chunk_seconds: int = 10,
) -> tuple[dict, dict]:
    files = {"file": (file_name, file_bytes, mime_type)}
    data = {
        "date": meta.date,
        "title": meta.title,
        "description": meta.description,
        "participants": meta.participants,
        "chunk_seconds": str(chunk_seconds),
    }
    return files, data


def transcribe_audio(
    file_name: str,
    file_bytes: bytes,
    mime_type: str,
    meta: UploadMeta,
    *,
    chunk_seconds: int = 10,
) -> Dict[str, Any]:
    """POST /api/transcribe — только транскрибация."""
    files, data = _upload_form(file_name, file_bytes, mime_type, meta, chunk_seconds=chunk_seconds)
    url = f"{API_BASE_URL}/api/transcribe"

    with httpx.Client(timeout=TRANSCRIBE_TIMEOUT_SEC) as client:
        response = client.post(url, files=files, data=data)
        response.raise_for_status()
        return response.json()


def process_meeting(
    file_name: str,
    file_bytes: bytes,
    mime_type: str,
    meta: UploadMeta,
    *,
    chunk_seconds: int = 10,
) -> Dict[str, Any]:
    """
    POST /api/meetings/process — запускает обработку в фоне, сразу возвращает job_id.
  """
    files, data = _upload_form(file_name, file_bytes, mime_type, meta, chunk_seconds=chunk_seconds)
    url = f"{API_BASE_URL}/api/meetings/process"

    # Только загрузка файла — ответ приходит быстро
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, files=files, data=data)
        response.raise_for_status()
        return response.json()


def get_meeting_job_status(job_id: str) -> Dict[str, Any]:
    """GET /api/meetings/jobs/{job_id} — проверка статуса фоновой задачи."""
    url = f"{API_BASE_URL}/api/meetings/jobs/{job_id}"

    with httpx.Client(timeout=10.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def ask_chat(question: str, chat_history: str = "") -> Dict[str, Any]:
    """POST /api/chat/ask — RAG-ответ."""
    url = f"{API_BASE_URL}/api/chat/ask"
    payload = {"question": question, "chat_history": chat_history}

    with httpx.Client(timeout=CHAT_TIMEOUT_SEC) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def check_api_health() -> bool:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{API_BASE_URL}/health")
            return r.status_code == 200
    except httpx.HTTPError:
        return False

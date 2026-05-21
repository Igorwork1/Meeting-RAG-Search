# Клиент для FastAPI-бэкенда транскрибации.
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

# URL бэкенда: uvicorn services.transcribe:app --port 8000
TRANSCRIBE_API_URL = (
    os.getenv("TRANSCRIBE_API_URL")
    or os.getenv("API_URL")
    or "http://127.0.0.1:8000"
).rstrip("/")

# Таймаут на длинные файлы (секунды)
TRANSCRIBE_TIMEOUT_SEC = float(os.getenv("TRANSCRIBE_TIMEOUT_SEC", "7200"))


@dataclass
class UploadMeta:
    date: str
    title: str
    description: str = ""


def transcribe_audio(
    file_name: str,
    file_bytes: bytes,
    mime_type: str,
    meta: UploadMeta,
    *,
    chunk_seconds: int = 10,
) -> Dict[str, Any]:
    """
    Отправляет файл на FastAPI /api/transcribe и ждёт готовый транскрипт.
    Вызывать из Streamlit внутри st.spinner — пока запрос идёт, крутится индикатор.
    """
    url = f"{TRANSCRIBE_API_URL.rstrip('/')}/api/transcribe"

    files = {"file": (file_name, file_bytes, mime_type)}
    data = {
        "date": meta.date,
        "title": meta.title,
        "description": meta.description,
        "chunk_seconds": str(chunk_seconds),
    }

    with httpx.Client(timeout=TRANSCRIBE_TIMEOUT_SEC) as client:
        response = client.post(url, files=files, data=data)
        response.raise_for_status()
        return response.json()


def check_api_health() -> bool:
    """True, если бэкенд отвечает на /health."""
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{TRANSCRIBE_API_URL.rstrip('/')}/health")
            return r.status_code == 200
    except httpx.HTTPError:
        return False

"""
Нагрузочное тестирование Cyberecho API (Locust).

Запуск из корня проекта (бэкенд должен быть поднят):

    pip install locust
    locust -f tests/locustfile.py --host http://127.0.0.1:8000

Web UI: http://localhost:8089

Переменные окружения:
    LOCUST_HEAVY=1        — включить POST /api/transcribe и /api/meetings/process
    LOCUST_AUDIO_PATH=... — путь к аудио (.wav/.mp3); иначе используется короткий WAV
"""
from __future__ import annotations

import os
import struct
import time
import uuid
from pathlib import Path

from locust import HttpUser, between, tag, task

# Короткий моно-WAV (~0.1 с тишины) — для smoke-нагрузки без внешнего файла
_MINIMAL_WAV: bytes | None = None

CHAT_QUESTIONS = [
    "Какие темы обсуждались на последней встрече?",
    "Какие решения были приняты?",
    "Кто участвовал в обсуждении?",
    "Есть ли открытые задачи после встречи?",
    "Кратко перескажи основные моменты.",
]


def _minimal_wav_bytes(duration_sec: float = 0.1, sample_rate: int = 8000) -> bytes:
    global _MINIMAL_WAV
    if _MINIMAL_WAV is not None:
        return _MINIMAL_WAV

    num_samples = max(1, int(sample_rate * duration_sec))
    pcm = b"\x00\x00" * num_samples
    byte_rate = sample_rate * 2
    block_align = 2
    data_size = len(pcm)
    riff_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        byte_rate,
        block_align,
        16,
        b"data",
        data_size,
    )
    _MINIMAL_WAV = header + pcm
    return _MINIMAL_WAV


def _load_audio_payload() -> tuple[bytes, str, str]:
    audio_path = os.getenv("LOCUST_AUDIO_PATH", "").strip()
    if audio_path:
        path = Path(audio_path)
        if path.is_file():
            return path.read_bytes(), path.name, "audio/mpeg" if path.suffix.lower() == ".mp3" else "audio/wav"
    return _minimal_wav_bytes(), "locust_sample.wav", "audio/wav"


def _heavy_enabled() -> bool:
    return os.getenv("LOCUST_HEAVY", "").strip().lower() in {"1", "true", "yes", "on"}


class CyberechoUser(HttpUser):
    """Виртуальный пользователь API Cyberecho."""

    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self._job_ids: list[str] = []
        self._audio_bytes, self._audio_name, self._audio_mime = _load_audio_payload()

    @tag("light")
    @task(10)
    def health(self) -> None:
        with self.client.get("/health", name="GET /health", catch_response=True) as resp:
            if resp.status_code != 200 or resp.json().get("status") != "ok":
                resp.failure(f"unexpected health response: {resp.status_code} {resp.text}")

    @tag("light")
    @task(3)
    def db_health(self) -> None:
        self.client.get("/db/health", name="GET /db/health")

    @tag("light")
    @task(2)
    def root(self) -> None:
        self.client.get("/", name="GET /")

    @tag("light", "chat")
    @task(8)
    def chat_ask(self) -> None:
        question = CHAT_QUESTIONS[int(uuid.uuid4().int % len(CHAT_QUESTIONS))]
        payload = {"question": question, "chat_history": ""}
        with self.client.post(
            "/api/chat/ask",
            json=payload,
            name="POST /api/chat/ask",
            catch_response=True,
            timeout=120,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"chat failed: {resp.status_code} {resp.text[:200]}")
            elif not resp.json().get("answer"):
                resp.failure("chat response without answer")

    @tag("light", "meetings")
    @task(4)
    def meeting_job_status(self) -> None:
        if self._job_ids:
            job_id = self._job_ids[-1]
        else:
            job_id = f"job_{uuid.uuid4().hex[:12]}"
        self.client.get(
            f"/api/meetings/jobs/{job_id}",
            name="GET /api/meetings/jobs/{job_id}",
        )

    @tag("heavy", "transcribe")
    @task(1)
    def transcribe(self) -> None:
        if not _heavy_enabled():
            return

        files = {"file": (self._audio_name, self._audio_bytes, self._audio_mime)}
        data = {
            "date": "2025-09-30",
            "title": f"locust-{uuid.uuid4().hex[:8]}",
            "description": "locust load test",
            "participants": "locust",
        }
        with self.client.post(
            "/api/transcribe",
            files=files,
            data=data,
            name="POST /api/transcribe",
            catch_response=True,
            timeout=600,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"transcribe failed: {resp.status_code} {resp.text[:200]}")
            elif resp.json().get("status") != "done":
                resp.failure(f"transcribe status: {resp.json()}")

    @tag("heavy", "meetings")
    @task(1)
    def process_meeting(self) -> None:
        if not _heavy_enabled():
            return

        files = {"file": (self._audio_name, self._audio_bytes, self._audio_mime)}
        data = {
            "date": "2025-09-30",
            "title": f"locust-meeting-{uuid.uuid4().hex[:8]}",
            "description": "locust meeting pipeline",
            "participants": "locust",
        }
        with self.client.post(
            "/api/meetings/process",
            files=files,
            data=data,
            name="POST /api/meetings/process",
            catch_response=True,
            timeout=60,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"process failed: {resp.status_code} {resp.text[:200]}")
                return
            job_id = resp.json().get("job_id")
            if job_id:
                self._job_ids.append(job_id)
                if len(self._job_ids) > 20:
                    self._job_ids.pop(0)

    @tag("heavy", "meetings")
    @task(2)
    def poll_recent_jobs(self) -> None:
        if not _heavy_enabled() or not self._job_ids:
            return
        for job_id in self._job_ids[-3:]:
            self.client.get(
                f"/api/meetings/jobs/{job_id}",
                name="GET /api/meetings/jobs/{job_id} [poll]",
            )
            time.sleep(0.1)

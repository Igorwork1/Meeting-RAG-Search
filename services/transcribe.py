"""
Транскрибация аудио (GigaAM) и FastAPI-бэкенд для загрузки файлов.
Запуск API: uvicorn services.transcribe:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

from typing import Optional
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from transformers import AutoModel
import uvicorn

load_dotenv()

# GigaAM transcribe() падает на длинных wav — режем короткими сегментами (сек)
DEFAULT_CHUNK_SECONDS = int(os.getenv("TRANSCRIBE_CHUNK_SECONDS", "10"))

_GIGAAM_MODEL = None
_GIGAAM_REVISION: Optional[str] = None


def get_gigaam_model(revision: str = "e2e_rnnt"):
    """Загружает модель один раз и держит в памяти."""
    global _GIGAAM_MODEL, _GIGAAM_REVISION

    if _GIGAAM_MODEL is not None and _GIGAAM_REVISION == revision:
        return _GIGAAM_MODEL

    print(f"[transcribe] loading ai-sage/GigaAM-v3 revision={revision!r}")

    _GIGAAM_MODEL = AutoModel.from_pretrained(
        "ai-sage/GigaAM-v3",
        revision=revision,
        trust_remote_code=True,
    )

    _GIGAAM_REVISION = revision
    return _GIGAAM_MODEL


def _ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found. Install ffmpeg and add it to PATH.")


def _split_audio_to_chunks(
    audio_path: str,
    chunks_dir: str,
    *,
    chunk_seconds: int,
) -> list[str]:
    """Нарезает аудио через ffmpeg на WAV 16 kHz mono чанки."""
    _ensure_ffmpeg()

    output_pattern = str(Path(chunks_dir) / "chunk_%04d.wav")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        audio_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        output_pattern,
    ]

    print(f"[transcribe] splitting audio into {chunk_seconds}s chunks...")
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    chunks = sorted(str(p) for p in Path(chunks_dir).glob("chunk_*.wav"))
    if not chunks:
        raise RuntimeError("ffmpeg did not create any chunks")
    return chunks


def _transcribe_wav(model, wav_path: str) -> str:
    """Один wav-файл → текст. При 'Too long' режет на 5 сек и склеивает."""
    try:
        return str(model.transcribe(wav_path)).strip()
    except (ValueError, Exception) as e:
        if "Too long" not in str(e):
            raise

    # запасной вариант: ещё мельче нарезка одного чанка
    print(f"[transcribe] re-split (5s): {wav_path}")
    with tempfile.TemporaryDirectory(prefix="gigaam_sub_") as subdir:
        sub_chunks = _split_audio_to_chunks(wav_path, subdir, chunk_seconds=5)
        parts = []
        for sub in sub_chunks:
            try:
                t = str(model.transcribe(sub)).strip()
                if t:
                    parts.append(t)
            except Exception as sub_e:
                print(f"[transcribe] sub-chunk failed: {sub_e}")
        return " ".join(parts)


def transcribe_file(
    audio_path: str,
    *,
    revision: str = "e2e_rnnt",
    chunk_seconds: int | None = None,
) -> str:
    """
    Транскрибирует mp3/wav через нарезку ffmpeg (короткие сегменты для GigaAM).
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    chunk_seconds = chunk_seconds or DEFAULT_CHUNK_SECONDS
    model = get_gigaam_model(revision=revision)
    parts: list[str] = []

    with tempfile.TemporaryDirectory(prefix="gigaam_chunks_") as tmpdir:
        chunks = _split_audio_to_chunks(
            audio_path=audio_path,
            chunks_dir=tmpdir,
            chunk_seconds=chunk_seconds,
        )

        for i, chunk_path in enumerate(chunks, start=1):
            try:
                text = _transcribe_wav(model, chunk_path)
            except Exception as e:
                print(f"[transcribe] chunk {i} failed: {e}")
                text = ""

            if text:
                start_sec = (i - 1) * chunk_seconds
                mm, ss = divmod(start_sec, 60)
                parts.append(f"[{mm:02d}:{ss:02d}] {text}")

    result = "\n".join(parts)
    if not result.strip():
        raise RuntimeError(
            "Транскрипт пустой — все чанки не распознались. "
            "Попробуйте другой файл или уменьшите TRANSCRIBE_CHUNK_SECONDS в .env"
        )

    print("[transcribe] done")
    return result


# --- FastAPI ---

app = FastAPI(title="Cyberecho Transcribe API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/transcribe")
async def api_transcribe(
    file: UploadFile = File(...),
    date: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    chunk_seconds: int = Form(DEFAULT_CHUNK_SECONDS),
):
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
            "file_name": file.filename,
        },
        "transcript": transcript,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

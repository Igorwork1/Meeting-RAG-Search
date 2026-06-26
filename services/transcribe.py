"""
Транскрибация аудио через GigaAM-v3 e2e_ctc (только логика, без HTTP).
"""
from __future__ import annotations

from typing import Callable
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from dotenv import load_dotenv
from transformers import AutoModel

load_dotenv()

# Модель: e2e_ctc — end-to-end CTC с пунктуацией и нормализацией текста.
# Быстрее e2e_rnnt примерно в 10× на CPU при сопоставимом качестве для встреч.
# Чтобы сменить вариант — поменяйте GIGAAM_REVISION (доступны: ctc, rnnt, e2e_rnnt).
GIGAAM_REVISION = "e2e_ctc"

# GigaAM transcribe() падает на wav длиннее 25 с — режем короткими сегментами (сек).
# Для ускорения можно поднять до 20–22; при пустом транскрипте — уменьшить.
DEFAULT_CHUNK_SECONDS = int(os.getenv("TRANSCRIBE_CHUNK_SECONDS", "10"))

_GIGAAM_MODEL = None


def is_gigaam_loaded() -> bool:
    return _GIGAAM_MODEL is not None


def get_gigaam_model():
    """Загружает GigaAM-v3 (e2e_ctc) один раз и держит в памяти."""
    global _GIGAAM_MODEL

    if _GIGAAM_MODEL is not None:
        return _GIGAAM_MODEL

    print(f"[transcribe] loading ai-sage/GigaAM-v3 revision={GIGAAM_REVISION!r}")

    _GIGAAM_MODEL = AutoModel.from_pretrained(
        "ai-sage/GigaAM-v3",
        revision=GIGAAM_REVISION,
        trust_remote_code=True,
    )

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
    chunk_seconds: int | None = None,
    on_progress: Callable[[str, str], None] | None = None,
) -> str:
    """Транскрибирует mp3/wav через GigaAM e2e_ctc и нарезку ffmpeg."""
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    def _report(stage: str, message: str = "") -> None:
        if on_progress:
            on_progress(stage, message)

    chunk_seconds = chunk_seconds or DEFAULT_CHUNK_SECONDS

    _report("loading_model", "Загрузка GigaAM-v3 (e2e_ctc)…")
    model = get_gigaam_model()
    parts: list[str] = []

    with tempfile.TemporaryDirectory(prefix="gigaam_chunks_") as tmpdir:
        _report("splitting", f"Нарезка на фрагменты по {chunk_seconds} с…")
        chunks = _split_audio_to_chunks(
            audio_path=audio_path,
            chunks_dir=tmpdir,
            chunk_seconds=chunk_seconds,
        )

        total = len(chunks)
        for i, chunk_path in enumerate(chunks, start=1):
            _report("transcribing", f"Фрагмент {i} из {total}")
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

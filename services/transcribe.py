# from __future__ import annotations

# from typing import Optional
# import os
# import pickle

# from dotenv import load_dotenv
# import torch
# from transformers import AutoModel

# load_dotenv()

# # ==========================================
# # PATCH torch.load for pyannote checkpoints
# # ==========================================
# _original_torch_load = torch.load

# def patched_torch_load(f, map_location=None, pickle_module=pickle, **kwargs):
#     kwargs.pop("weights_only", None)
#     return _original_torch_load(
#         f,
#         map_location=map_location,
#         pickle_module=pickle_module,
#         weights_only=False,
#         **kwargs,
#     )

# torch.load = patched_torch_load

# _GIGAAM_MODEL = None
# _GIGAAM_REVISION: Optional[str] = None


# def get_gigaam_model(revision: str = "e2e_rnnt"):
#     global _GIGAAM_MODEL, _GIGAAM_REVISION

#     if _GIGAAM_MODEL is not None and _GIGAAM_REVISION == revision:
#         return _GIGAAM_MODEL

#     print(f"[transcribe] loading ai-sage/GigaAM-v3 revision={revision!r}")

#     _GIGAAM_MODEL = AutoModel.from_pretrained(
#         "ai-sage/GigaAM-v3",
#         revision=revision,
#         trust_remote_code=True,
#     )

#     _GIGAAM_REVISION = revision
#     return _GIGAAM_MODEL


# def transcribe_file(wav_path: str, *, revision: str = "e2e_rnnt") -> str:
#     if not os.path.exists(wav_path):
#         raise FileNotFoundError(f"Audio file not found: {wav_path}")

#     model = get_gigaam_model(revision=revision)

#     try:
#         transcription = model.transcribe(wav_path)
#     except ValueError as e:
#         if "Too long wav file" in str(e):
#             if not os.getenv("HF_TOKEN"):
#                 raise RuntimeError("HF_TOKEN is required for transcribe_longform") from e

#             print("[transcribe] file is long, using transcribe_longform")
#             transcription = model.transcribe_longform(wav_path)
#         else:
#             raise

#     print("[transcribe] done")
#     return transcription


from __future__ import annotations

from typing import Optional
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from dotenv import load_dotenv
from transformers import AutoModel

load_dotenv()

_GIGAAM_MODEL = None
_GIGAAM_REVISION: Optional[str] = None


def get_gigaam_model(revision: str = "e2e_rnnt"):
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
    chunk_seconds: int = 30,
) -> list[str]:
    """
    Нарезает любое аудио через ffmpeg на WAV 16kHz mono чанки.
    """
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

    # print(f"[transcribe] chunks created: {len(chunks)}")
    return chunks


def transcribe_file(
    audio_path: str,
    *,
    revision: str = "e2e_rnnt",
    chunk_seconds: int = 30,
) -> str:
    """
    Транскрибирует длинный mp3/wav через ручную нарезку.
    Не использует transcribe_longform, pyannote и torchcodec.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = get_gigaam_model(revision=revision)

    parts: list[str] = []

    with tempfile.TemporaryDirectory(prefix="gigaam_chunks_") as tmpdir:
        chunks = _split_audio_to_chunks(
            audio_path=audio_path,
            chunks_dir=tmpdir,
            chunk_seconds=chunk_seconds,
        )

        for i, chunk_path in enumerate(chunks, start=1):
            # print(f"[transcribe] chunk {i}/{len(chunks)}: {chunk_path}")

            try:
                text = model.transcribe(chunk_path)
            except Exception as e:
                print(f"[transcribe] chunk {i} failed: {e}")
                text = ""

            text = str(text).strip()

            if text:
                start_sec = (i - 1) * chunk_seconds
                mm, ss = divmod(start_sec, 60)
                parts.append(f"[{mm:02d}:{ss:02d}] {text}")

    result = "\n".join(parts)
    print("[transcribe] done")
    return result
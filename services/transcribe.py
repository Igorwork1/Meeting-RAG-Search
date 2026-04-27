from __future__ import annotations

from typing import Optional
import os

from transformers import AutoModel


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


_GIGAAM_MODEL = None
_GIGAAM_REVISION: Optional[str] = None


def get_gigaam_model(revision: str = "e2e_rnnt"):
    global _GIGAAM_MODEL, _GIGAAM_REVISION

    if _GIGAAM_MODEL is not None and _GIGAAM_REVISION == revision:
        return _GIGAAM_MODEL

    print(f"[transcribe] loading ai-sage/GigaAM-v3 revision={revision!r}")
    _GIGAAM_MODEL = AutoModel.from_pretrained(
        "ai-sage/GigaAM-v3",
        revision=revision,  # ssl, ctc, rnnt, e2e_ctc, e2e_rnnt
        trust_remote_code=True,
    )
    _GIGAAM_REVISION = revision
    return _GIGAAM_MODEL


def transcribe_file(
    wav_path: str,
    *,
    revision: str = "e2e_rnnt",
    api_key_env: str = "API_KEY",
    api_key_default: str = "default_key",
):
    # Модель сама по себе ключ не требует, но заготовка под прод окружение полезна.
    api_key = os.getenv(api_key_env, api_key_default)
    print(f"[transcribe] {api_key_env} present={api_key != api_key_default}")

    model = get_gigaam_model(revision=revision)
    transcription = model.transcribe(wav_path)
    print("[transcribe] done")
    return transcription


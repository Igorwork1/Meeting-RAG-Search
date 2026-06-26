"""Тесты разбиения транскрипта и настроек RAG (без вызова LLM)."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.chunking import split_text_to_chunks
from services.summarize import load_summary_prompt


SAMPLE_TRANSCRIPT = (
    "Иван: добрый день, начнём статус. "
    "Мария: закончила интеграцию с API, осталось покрыть тестами. "
    "Пётр: перенёс деплой на следующую неделю из-за бага в staging. "
) * 80


def test_summary_prompt_has_no_rag_chunk_sections() -> None:
    prompt = load_summary_prompt()
    assert "## Чанк" not in prompt
    assert "{chunk_count}" not in prompt
    assert "{summary_max_chars}" in prompt


def test_summary_max_chars_substituted() -> None:
    from services.summarize import SUMMARY_MAX_CHARS, summarize_meeting

    prompt = load_summary_prompt().replace("{summary_max_chars}", str(SUMMARY_MAX_CHARS))
    assert "{summary_max_chars}" not in prompt
    assert str(SUMMARY_MAX_CHARS) in prompt
    assert summarize_meeting.__doc__  # smoke: функция на месте


def test_rag_chunk_defaults() -> None:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"RAG_CHUNK_SIZE_TOKENS", "RAG_CHUNK_OVERLAP_TOKENS"}
    }
    with patch.dict(os.environ, env, clear=True):
        chunking = importlib.import_module("services.chunking")
        importlib.reload(chunking)
        assert chunking.RAG_CHUNK_SIZE_TOKENS == 700
        assert chunking.RAG_CHUNK_OVERLAP_TOKENS == 100


def test_split_text_to_chunks_structure() -> None:
    chunks = split_text_to_chunks(SAMPLE_TRANSCRIPT)
    assert len(chunks) > 1
    for chunk in chunks:
        assert isinstance(chunk["chunk_index"], int)
        assert chunk["chunk_index"] >= 1
        assert chunk["chunk_text"].strip()


def test_split_text_empty() -> None:
    assert split_text_to_chunks("") == []
    assert split_text_to_chunks("   ") == []


def test_top_k_default_is_three() -> None:
    env = {k: v for k, v in os.environ.items() if k != "TOP_K"}
    with patch.dict(os.environ, env, clear=True):
        rag = importlib.import_module("services.rag")
        importlib.reload(rag)
        assert rag.TOP_K == 3


if __name__ == "__main__":
    test_summary_prompt_has_no_rag_chunk_sections()
    test_summary_max_chars_substituted()
    test_rag_chunk_defaults()
    test_split_text_to_chunks_structure()
    test_split_text_empty()
    test_top_k_default_is_three()
    print("OK: all chunking/RAG config tests passed")

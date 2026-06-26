"""
Детерминированное разбиение текста на RAG-чанки (RecursiveCharacterTextSplitter).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

RAG_CHUNK_SIZE_TOKENS = int(os.getenv("RAG_CHUNK_SIZE_TOKENS", "700"))
RAG_CHUNK_OVERLAP_TOKENS = int(os.getenv("RAG_CHUNK_OVERLAP_TOKENS", "100"))


def _clamp_token_settings(size: int, overlap: int) -> tuple[int, int]:
    """Держим параметры в пределах курсовой: size 300–700, overlap 50–100."""
    size = max(300, min(700, size))
    overlap = max(50, min(100, overlap))
    if overlap >= size:
        overlap = min(100, max(50, size // 5))
    return size, overlap


def split_text_to_chunks(text: str) -> list[dict]:
    """
    Разбивает текст (summary_text) на фрагменты для RAG и эмбеддингов.
    Возвращает [{"chunk_index": 1, "chunk_text": "..."}, ...].
    """
    normalized = (text or "").strip()
    if not normalized:
        return []

    chunk_size, chunk_overlap = _clamp_token_settings(
        RAG_CHUNK_SIZE_TOKENS,
        RAG_CHUNK_OVERLAP_TOKENS,
    )

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    parts = splitter.split_text(normalized)

    return [
        {"chunk_index": index, "chunk_text": part.strip()}
        for index, part in enumerate(parts, start=1)
        if part.strip()
    ]


# Обратная совместимость
split_transcript_to_chunks = split_text_to_chunks

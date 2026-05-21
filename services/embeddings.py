"""
Эмбеддинги для чанков встреч (Giga-Embeddings-instruct).
Модель грузится один раз, перед сохранением в meeting_chunks.
"""
from __future__ import annotations

import os
from typing import Optional

import torch
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

_EMBED_MODEL: Optional[SentenceTransformer] = None
_EMBED_DIM: Optional[int] = None

DEFAULT_MODEL = "ai-sage/Giga-Embeddings-instruct"


def _model_name() -> str:
    return os.getenv("GIGA_EMBEDDING_MODEL", DEFAULT_MODEL).strip().strip('"')


def get_embedding_model() -> SentenceTransformer:
    """Загружает модель эмбеддингов в память один раз."""
    global _EMBED_MODEL, _EMBED_DIM

    if _EMBED_MODEL is not None:
        return _EMBED_MODEL

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_kwargs = {"trust_remote_code": True}

    if device == "cuda":
        major, _ = torch.cuda.get_device_capability(0)
        model_kwargs["torch_dtype"] = torch.bfloat16 if major >= 8 else torch.float16

    print(f"[embeddings] loading {_model_name()} on {device}")

    _EMBED_MODEL = SentenceTransformer(
        _model_name(),
        model_kwargs=model_kwargs,
        config_kwargs={"trust_remote_code": True},
        device=device,
    )
    _EMBED_DIM = _EMBED_MODEL.get_sentence_embedding_dimension()
    return _EMBED_MODEL


def get_embedding_dimension() -> int:
    """Размерность вектора для колонки pgvector."""
    get_embedding_model()
    return int(_EMBED_DIM or 0)


def embed_query(text: str) -> list[float]:
    """Эмбеддинг одного поискового запроса для RAG."""
    vectors = embed_texts([text])
    if not vectors:
        raise ValueError("Не удалось получить эмбеддинг запроса")
    return vectors[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Считает эмбеддинги для списка текстов (чанков встречи).
    Возвращает список векторов той же длины, что и texts.
    """
    if not texts:
        return []

    model = get_embedding_model()
    vectors = model.encode(
        [t.strip() or " " for t in texts],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return [vec.tolist() for vec in vectors]


def vector_to_pg(embedding: list[float]) -> str:
    """Формат строки для PostgreSQL ::vector (как в rag.py)."""
    return "[" + ",".join(map(str, embedding)) + "]"

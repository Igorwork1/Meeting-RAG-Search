"""Системные роуты: health, проверка БД."""
from __future__ import annotations

from fastapi import APIRouter

from services.db import check_db_connection
from services.embeddings import is_embedding_model_loaded
from services.transcribe import is_gigaam_loaded

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    models = {
        "gigaam": is_gigaam_loaded(),
        "embeddings": is_embedding_model_loaded(),
    }
    return {
        "status": "ok",
        "models_ready": all(models.values()),
        "models": models,
    }


@router.get("/db/health")
def db_health():
    return check_db_connection()

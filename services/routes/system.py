"""Системные роуты: health, проверка БД."""
from __future__ import annotations

from fastapi import APIRouter

from services.db import check_db_connection

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/db/health")
def db_health():
    return check_db_connection()

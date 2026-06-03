"""HTTP-роуты RAG-чата."""
from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter

from services.rag import ask

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    chat_history: str = ""


@router.post("/ask")
def chat_ask(body: ChatRequest):
    """Вопрос → LLM-препроцессинг → поиск в БД → ответ LLM."""
    return ask(body.question, chat_history=body.chat_history)

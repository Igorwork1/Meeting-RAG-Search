"""
Простой RAG по встречам: parser_data → поиск в pgvector → ответ LLM (LangChain).
"""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from psycopg2.extras import RealDictCursor

from services.db import (
    get_db_connection,
    DB_SCHEMA,
    MEETINGS_TABLE,
    CHUNKS_TABLE,
)
from services.embeddings import embed_query, vector_to_pg
from services.parser_data import ParsedQuery, parse_user_query
from services.summarize import _build_llm

load_dotenv()

TOP_K = int(os.getenv("TOP_K", "5"))

# Подсказки LLM по типу вопроса (intent из parser_data)
INTENT_HINTS = {
    "meeting_summary": "Сфокусируйся на обзоре и итогах встречи.",
    "decisions_search": "Выдели принятые решения и договорённости.",
    "tasks_search": "Выдели задачи, поручения и сроки.",
    "semantic_search": "Ответь по смыслу вопроса по фрагментам.",
}


def _parsed_to_dict(parsed: ParsedQuery) -> dict[str, Any]:
    """Для UI / отладки — что извлек парсер."""
    return {
        "original_query": parsed.original_query,
        "normalized_query": parsed.normalized_query,
        "semantic_query": parsed.semantic_query,
        "intent": parsed.intent,
        "date_from": parsed.date_from.isoformat() if parsed.date_from else None,
        "date_to": parsed.date_to.isoformat() if parsed.date_to else None,
        "sort_by": parsed.sort_by,
        "limit": parsed.limit,
        "corrected_terms": parsed.corrected_terms,
    }


def _parser_context(parsed: ParsedQuery) -> str:
    """Кратко описывает, как понят вопрос (для промпта LLM)."""
    lines = [f"Тип вопроса: {parsed.intent}."]
    if parsed.date_from:
        end = parsed.date_to or parsed.date_from
        lines.append(f"Фильтр по дате встречи: с {parsed.date_from} по {end}.")
    if parsed.sort_by == "date_of_the_meeting_desc":
        lines.append("Нужна информация с последней по дате встречи.")
    if parsed.corrected_terms:
        fixes = ", ".join(f"{k}→{v}" for k, v in parsed.corrected_terms.items())
        lines.append(f"Исправлены опечатки: {fixes}.")
    return " ".join(lines)


def search_documents(parsed: ParsedQuery, top_k: int | None = None) -> list[Document]:
    """
    Векторный поиск по cyberecho_meeting_chunks.
    Текст для эмбеддинга — semantic_query из parser_data (без «сегодня», «созвон» и т.д.).
    """
    limit = parsed.limit or top_k or TOP_K
    search_text = (parsed.semantic_query or parsed.original_query).strip()
    query_vector = vector_to_pg(embed_query(search_text))

    conditions = ["mc.embedding IS NOT NULL"]
    params: list[Any] = []

    if parsed.date_from:
        conditions.append("DATE(m.date_of_the_meeting) >= %s")
        params.append(parsed.date_from)
    if parsed.date_to:
        conditions.append("DATE(m.date_of_the_meeting) <= %s")
        params.append(parsed.date_to)

    # «Последняя встреча» — сначала свежие по дате, внутри — ближе по смыслу
    if parsed.sort_by == "date_of_the_meeting_desc":
        order_clause = (
            "m.date_of_the_meeting DESC NULLS LAST, "
            "mc.embedding <-> %s::vector"
        )
    else:
        order_clause = "mc.embedding <-> %s::vector"

    where_sql = " AND ".join(conditions)
    params.extend([query_vector, limit])

    sql = f"""
        SELECT
            mc.chunk_text,
            mc.chunk_index,
            m.id AS meeting_id,
            m.name_of_the_meeting,
            m.date_of_the_meeting,
            m.description
        FROM {DB_SCHEMA}.{CHUNKS_TABLE} mc
        JOIN {DB_SCHEMA}.{MEETINGS_TABLE} m ON m.id = mc.meeting_id
        WHERE {where_sql}
        ORDER BY {order_clause}
        LIMIT %s
    """

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    documents: list[Document] = []
    for row in rows:
        meeting_date = row.get("date_of_the_meeting")
        date_str = meeting_date.isoformat() if meeting_date else ""

        documents.append(
            Document(
                page_content=row["chunk_text"],
                metadata={
                    "meeting_id": row["meeting_id"],
                    "meeting_title": row.get("name_of_the_meeting", ""),
                    "meeting_date": date_str,
                    "chunk_index": row.get("chunk_index"),
                    "description": row.get("description", ""),
                },
            )
        )
    return documents


def _format_docs_block(documents: list[Document]) -> str:
    if not documents:
        return "Релевантных фрагментов не найдено."

    parts: list[str] = []
    for i, doc in enumerate(documents, start=1):
        meta = doc.metadata
        header = (
            f"[Фрагмент {i} | Встреча: {meta.get('meeting_title', '—')} | "
            f"Дата: {meta.get('meeting_date', '—')} | Чанк: {meta.get('chunk_index', '—')}]"
        )
        parts.append(f"{header}\n{doc.page_content}")
    return "\n\n".join(parts)


def _quotes_from_documents(documents: list[Document]) -> list[str]:
    quotes: list[str] = []
    for doc in documents[:3]:
        title = doc.metadata.get("meeting_title", "Встреча")
        text = doc.page_content.strip()
        if len(text) > 220:
            text = text[:220] + "…"
        quotes.append(f"«{title}»: {text}")
    return quotes


def generate_response(
    parsed: ParsedQuery,
    documents: list[Document],
    chat_history: str = "",
) -> str:
    """Ответ LLM: оригинальный вопрос + контекст парсера + чанки из БД."""
    docs_block = _format_docs_block(documents)
    intent_hint = INTENT_HINTS.get(parsed.intent, INTENT_HINTS["semantic_search"])

    prompt = ChatPromptTemplate.from_template(
        """
Ты — AI-помощник команды MetaPrompt. Отвечай на вопросы о содержании созвонов и встреч.

Правила:
- Используй только фрагменты из контекста ниже
- Если в контексте нет ответа — честно скажи, что в сохранённых встречах этого нет
- Отвечай на русском, кратко и по делу
- Учитывай историю диалога

==== Как понят вопрос (парсер) ====
{parser_context}
Подсказка: {intent_hint}

==== История диалога ====
{chat_history}

==== Фрагменты из встреч ====
{docs_block}

==== Вопрос пользователя ====
{user_message}

Ответ:
"""
    )

    llm = _build_llm()
    return (prompt | llm).invoke(
        {
            "user_message": parsed.original_query,
            "docs_block": docs_block,
            "chat_history": chat_history or "—",
            "parser_context": _parser_context(parsed),
            "intent_hint": intent_hint,
        }
    ).content


def ask(question: str, chat_history: str = "") -> dict[str, Any]:
    """
    Точка входа RAG:
    1) parse_user_query — нормализация и извлечение дат/intent
    2) search_documents — поиск по semantic_query
    3) generate_response — ответ LLM
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("Пустой вопрос")

    parsed = parse_user_query(question)
    documents = search_documents(parsed)
    answer = generate_response(parsed, documents, chat_history)

    return {
        "answer": str(answer).strip(),
        "quotes": _quotes_from_documents(documents),
        "sources_count": len(documents),
        "parsed": _parsed_to_dict(parsed),
    }

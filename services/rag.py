"""
Простой RAG по встречам: LLM-препроцессинг запроса → поиск в pgvector → ответ LLM (LangChain).
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
    save_meeting_ask,
)
from services.embeddings import embed_query, vector_to_pg
from services.query_preprocess import PreprocessedQuery, preprocess_user_question
from services.summarize import invoke_llm_messages

load_dotenv()

TOP_K = int(os.getenv("TOP_K", "5"))

# Подсказки LLM по типу вопроса (intent из LLM-препроцессинга)
INTENT_HINTS = {
    "meeting_summary": "Сфокусируйся на обзоре и итогах встречи.",
    "decisions_search": "Выдели принятые решения и договорённости.",
    "tasks_search": "Выдели задачи, поручения и сроки.",
    "semantic_search": "Ответь по смыслу вопроса по фрагментам.",
}


def _parsed_to_dict(parsed: PreprocessedQuery) -> dict[str, Any]:
    """Для UI / отладки — что извлек препроцессор."""
    return {
        "original_query": parsed.original_question,
        "normalized_query": parsed.normalized_question,
        "semantic_query": parsed.semantic_query,
        "intent": parsed.intent,
        "date": parsed.date.isoformat() if parsed.date else None,
        "date_from": parsed.date_from.isoformat() if parsed.date_from else None,
        "date_to": parsed.date_to.isoformat() if parsed.date_to else None,
    }


def _parser_context(parsed: PreprocessedQuery) -> str:
    """Кратко описывает, как понят вопрос (для промпта LLM)."""
    lines = [f"Тип вопроса: {parsed.intent}."]
    if parsed.date_from or parsed.date_to:
        start = parsed.date_from or parsed.date_to
        end = parsed.date_to or parsed.date_from
        if start and end and start == end:
            lines.append(f"Фильтр по дате встречи: {start}.")
        elif start and end:
            lines.append(f"Фильтр по дате встречи: с {start} по {end}.")
    else:
        # date всегда выставлен, даже если фильтр не применяем
        lines.append(f"Дата сейчас (default date): {parsed.date}.")
    return " ".join(lines)


def _cosine_similarity_from_distance(distance: float | None) -> float | None:
    """pgvector <=>: для нормализованных векторов similarity = 1 - distance."""
    if distance is None:
        return None
    return max(0.0, min(1.0, 1.0 - float(distance)))


def search_documents(parsed: PreprocessedQuery, top_k: int | None = None) -> list[Document]:
    """
    Векторный поиск по cyberecho_meeting_chunks (косинусное расстояние pgvector <=>).
    Текст для эмбеддинга — semantic_query из LLM-препроцессинга.
    """
    limit = top_k or TOP_K
    search_text = (parsed.semantic_query or parsed.original_question).strip()
    query_vector = vector_to_pg(embed_query(search_text))

    conditions = ["mc.embedding IS NOT NULL"]
    params: list[Any] = [query_vector]  # SELECT: cosine_distance

    if parsed.date_from:
        conditions.append("DATE(m.date_of_the_meeting) >= %s")
        params.append(parsed.date_from)
    if parsed.date_to:
        conditions.append("DATE(m.date_of_the_meeting) <= %s")
        params.append(parsed.date_to)

    order_clause = "mc.embedding <=> %s::vector"
    params.append(query_vector)  # ORDER BY
    params.append(limit)  # LIMIT

    where_sql = " AND ".join(conditions)

    sql = f"""
        SELECT
            mc.chunk_text,
            mc.chunk_index,
            m.id AS meeting_id,
            m.name_of_the_meeting,
            m.date_of_the_meeting,
            m.description,
            m.participants,
            m.summary_text,
            (mc.embedding <=> %s::vector) AS cosine_distance
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
        cosine_distance = row.get("cosine_distance")
        if cosine_distance is not None:
            cosine_distance = float(cosine_distance)
        cosine_similarity = _cosine_similarity_from_distance(cosine_distance)

        documents.append(
            Document(
                page_content=row["chunk_text"],
                metadata={
                    "meeting_id": row["meeting_id"],
                    "meeting_title": row.get("name_of_the_meeting", ""),
                    "meeting_date": date_str,
                    "chunk_index": row.get("chunk_index"),
                    "description": row.get("description", ""),
                    "participants": row.get("participants", ""),
                    "summary_text": row.get("summary_text", "") or "",
                    "cosine_distance": cosine_distance,
                    "cosine_similarity": cosine_similarity,
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


def _format_meeting_summaries_block(documents: list[Document]) -> str:
    """
    Достаём summary_text из связанных встреч для уже найденных чанков,
    чтобы LLM мог использовать резюме как дополнительный контекст.
    """
    summaries_by_meeting: dict[Any, str] = {}
    meta_by_meeting: dict[Any, dict[str, Any]] = {}

    for doc in documents:
        meta = doc.metadata or {}
        meeting_id = meta.get("meeting_id")
        summary_text = (meta.get("summary_text") or "").strip()
        if not meeting_id or not summary_text:
            continue
        if meeting_id in summaries_by_meeting:
            continue
        summaries_by_meeting[meeting_id] = summary_text
        meta_by_meeting[meeting_id] = meta

    if not summaries_by_meeting:
        return "—"

    parts: list[str] = []
    for meeting_id, summary_text in summaries_by_meeting.items():
        meta = meta_by_meeting.get(meeting_id, {})
        header = (
            f"[Встреча: {meta.get('meeting_title', '—')} | "
            f"Дата: {meta.get('meeting_date', '—')} | id: {meeting_id}]"
        )
        parts.append(f"{header}\n{summary_text}")

    return "\n\n".join(parts)


def _snippet(text: str, max_len: int = 220) -> str:
    text = (text or "").strip()
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


def _sources_from_documents(documents: list[Document]) -> list[dict[str, Any]]:
    """Структурированные источники с косинусной похожестью для API и UI."""
    sources: list[dict[str, Any]] = []
    for i, doc in enumerate(documents, start=1):
        meta = doc.metadata or {}
        distance = meta.get("cosine_distance")
        similarity = meta.get("cosine_similarity")
        if similarity is None:
            similarity = _cosine_similarity_from_distance(distance)

        sources.append(
            {
                "rank": i,
                "meeting_id": meta.get("meeting_id"),
                "meeting_title": meta.get("meeting_title", ""),
                "meeting_date": meta.get("meeting_date", ""),
                "chunk_index": meta.get("chunk_index"),
                "cosine_distance": round(float(distance), 4) if distance is not None else None,
                "cosine_similarity": round(float(similarity), 4) if similarity is not None else None,
                "relevance_percent": round(float(similarity) * 100, 1) if similarity is not None else None,
                "snippet": _snippet(doc.page_content),
            }
        )
    return sources


def _quotes_from_documents(documents: list[Document]) -> list[str]:
    quotes: list[str] = []
    for doc in documents[:3]:
        title = doc.metadata.get("meeting_title", "Встреча")
        similarity = doc.metadata.get("cosine_similarity")
        score = ""
        if similarity is not None:
            score = f" (релевантность {round(float(similarity) * 100, 1)}%)"
        quotes.append(f"«{title}»{score}: {_snippet(doc.page_content)}")
    return quotes


def generate_response(
    parsed: PreprocessedQuery,
    documents: list[Document],
    chat_history: str = "",
) -> str:
    """Ответ LLM: оригинальный вопрос + контекст парсера + чанки из БД."""
    docs_block = _format_docs_block(documents)
    meeting_summaries_block = _format_meeting_summaries_block(documents)
    intent_hint = INTENT_HINTS.get(parsed.intent, INTENT_HINTS["semantic_search"])

    prompt = ChatPromptTemplate.from_template(
        """
Ты — AI-помощник команды MetaPromt. Отвечай на вопросы о содержании созвонов и встреч.

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

==== Резюме встреч (summary_text) ====
{meeting_summaries_block}

==== Фрагменты из встреч ====
{docs_block}

==== Вопрос пользователя ====
{user_message}

Ответ:
"""
    )

    return invoke_llm_messages(
        prompt.format_messages(
            user_message=parsed.original_question,
            docs_block=docs_block,
            meeting_summaries_block=meeting_summaries_block,
            chat_history=chat_history or "—",
            parser_context=_parser_context(parsed),
            intent_hint=intent_hint,
        )
    )


def ask(question: str, chat_history: str = "") -> dict[str, Any]:
    """
    Точка входа RAG:
    1) preprocess_user_question — LLM-препроцессинг (semantic_query + date)
    2) search_documents — поиск по semantic_query (+ фильтр по датам, если найден)
    3) generate_response — ответ LLM
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("Пустой вопрос")

    parsed = preprocess_user_question(question)
    documents = search_documents(parsed)
    fallback = (
        "К сожалению, в базе знаний нет информации по этому запросу. "
        "Пожалуйста, уточните ваш вопрос"
    )

    # Если самый релевантный фрагмент слишком далёк по смыслу — не вызываем LLM.
    top_meta = (documents[0].metadata or {}) if documents else {}
    top_distance = top_meta.get("cosine_distance")
    top_similarity = top_meta.get("cosine_similarity")
    if top_similarity is None:
        top_similarity = _cosine_similarity_from_distance(top_distance)

    if top_distance is not None and float(top_distance) > 0.65:
        return {
            "answer": fallback,
            "quotes": [],
            "sources": [],
            "sources_count": 0,
            "parsed": _parsed_to_dict(parsed),
        }

    if top_similarity is not None and float(top_similarity) < 0.38:
        return {
            "answer": fallback,
            "quotes": [],
            "sources": [],
            "sources_count": 0,
            "parsed": _parsed_to_dict(parsed),
        }

    answer = generate_response(parsed, documents, chat_history)
    answer_str = str(answer).strip()

    # Логирование диалога в БД не должно ломать сам ответ.
    try:
        save_meeting_ask(question, answer_str)
    except Exception:
        pass

    return {
        "answer": answer_str,
        "quotes": _quotes_from_documents(documents),
        "sources": _sources_from_documents(documents),
        "sources_count": len(documents),
        "parsed": _parsed_to_dict(parsed),
    }

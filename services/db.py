"""
PostgreSQL: cyberecho_meetings + cyberecho_meeting_chunks.
Порядок: суммаризация → эмбеддинги → INSERT.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable
import os

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

DB_SCHEMA = os.getenv("SCHEMA", "public").strip()
MEETINGS_TABLE = os.getenv("MEETINGS_TABLE", "cyberecho_meetings").strip()
CHUNKS_TABLE = os.getenv("CHUNKS_TABLE", "cyberecho_meeting_chunks").strip()
ASKS_TABLE = os.getenv("ASKS_TABLE", "cyberecho_meeting_asks").strip()
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "2048"))


def _connection_string() -> str:
    """Строка подключения из .env (убираем пробелы и кавычки)."""
    raw = os.getenv("POSTGRES_CONNECTION_STRING", "")
    return raw.strip().strip('"').strip("'")


def get_db_connection():
    """Подключение к PostgreSQL."""
    conn_str = _connection_string()
    if not conn_str:
        raise RuntimeError("Задай POSTGRES_CONNECTION_STRING в .env")
    try:
        return psycopg2.connect(conn_str)
    except Exception as e:
        raise RuntimeError(f"Ошибка подключения к базе данных: {e}") from e


def _full_table(name: str) -> str:
    return f"{DB_SCHEMA}.{name}"


def check_db_connection() -> dict[str, Any]:
    """
    Проверка подключения и наличия таблиц cyberecho_meetings / cyberecho_meeting_chunks / cyberecho_meeting_asks.
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()["version"]

            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name IN (%s, %s, %s)
                ORDER BY table_name
                """,
                (DB_SCHEMA, MEETINGS_TABLE, CHUNKS_TABLE, ASKS_TABLE),
            )
            found_tables = [r["table_name"] for r in cur.fetchall()]

            meetings_count = None
            chunks_count = None
            asks_count = None
            if MEETINGS_TABLE in found_tables:
                cur.execute(f"SELECT COUNT(*) AS c FROM {_full_table(MEETINGS_TABLE)}")
                meetings_count = cur.fetchone()["c"]
            if CHUNKS_TABLE in found_tables:
                cur.execute(f"SELECT COUNT(*) AS c FROM {_full_table(CHUNKS_TABLE)}")
                chunks_count = cur.fetchone()["c"]
            if ASKS_TABLE in found_tables:
                cur.execute(f"SELECT COUNT(*) AS c FROM {_full_table(ASKS_TABLE)}")
                asks_count = cur.fetchone()["c"]

        return {
            "ok": MEETINGS_TABLE in found_tables
            and CHUNKS_TABLE in found_tables
            and ASKS_TABLE in found_tables,
            "version": version,
            "schema": DB_SCHEMA,
            "tables_found": found_tables,
            "meetings_table": MEETINGS_TABLE,
            "chunks_table": CHUNKS_TABLE,
            "asks_table": ASKS_TABLE,
            "meetings_count": meetings_count,
            "chunks_count": chunks_count,
            "asks_count": asks_count,
        }
    finally:
        conn.close()


def ensure_meetings_tables() -> None:
    """
    Создаёт таблицы по вашей схеме (если ещё нет).
    embedding фиксированно VECTOR(2048).
    """
    sql = f"""
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS {_full_table(MEETINGS_TABLE)} (
        id SERIAL PRIMARY KEY,
        date_of_the_meeting TIMESTAMP,
        name_of_the_meeting VARCHAR(255),
        description TEXT,
        participants TEXT DEFAULT '',
        summary_text TEXT
    );

    CREATE TABLE IF NOT EXISTS {_full_table(CHUNKS_TABLE)} (
        id SERIAL PRIMARY KEY,
        meeting_id INTEGER NOT NULL REFERENCES {_full_table(MEETINGS_TABLE)}(id) ON DELETE CASCADE,
        chunk_index INTEGER,
        chunk_text TEXT,
        embedding VECTOR({EMBEDDING_DIM})
    );

    CREATE TABLE IF NOT EXISTS {_full_table(ASKS_TABLE)} (
        id SERIAL PRIMARY KEY,
        question TEXT,
        answer TEXT
    );
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                f"""
                ALTER TABLE {_full_table(MEETINGS_TABLE)}
                ADD COLUMN IF NOT EXISTS participants TEXT DEFAULT ''
                """
            )
        conn.commit()
    finally:
        conn.close()


def save_meeting_ask(question: str, answer: str) -> int | None:
    """
    Сохраняет вопрос пользователя и ответ чат-бота в cyberecho_meeting_asks.
    Возвращает id вставленной записи (или None, если вставка не удалась).
    """
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        return None

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_full_table(ASKS_TABLE)} (question, answer)
                VALUES (%s, %s)
                RETURNING id
                """,
                (question, answer),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return int(new_id)
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def _parse_meeting_datetime(value: str) -> datetime | None:
    """Дата из recall.py → TIMESTAMP (начало дня)."""
    value = (value or "").strip()
    if not value or value == "—":
        return None
    try:
        d = date.fromisoformat(value[:10])
        return datetime.combine(d, time.min)
    except ValueError:
        return None


def save_meeting_record(
    transcript: str,
    meta: dict[str, Any],
    *,
    file_name: str | None = None,
    on_progress: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """
    1) Суммаризация (summarize.py)
    2) Эмбеддинги для каждого чанка
    3) INSERT в cyberecho_meetings и cyberecho_meeting_chunks
    """

    def _report(stage: str, message: str = "") -> None:
        if on_progress:
            on_progress(stage, message)

    check = check_db_connection()
    if not check["ok"]:
        raise RuntimeError(
            f"Таблицы не найдены в схеме {DB_SCHEMA}: "
            f"ожидались {MEETINGS_TABLE}, {CHUNKS_TABLE}; найдено: {check['tables_found']}"
        )

    from services.embeddings import embed_texts, vector_to_pg
    from services.summarize import build_meeting_json

    _report("summarizing", "LLM формирует структуру встречи…")
    data = build_meeting_json(transcript, meta, file_name=file_name)
    chunks = data.get("chunks") or []

    if not chunks:
        raise ValueError("Нет чанков для сохранения — проверь формат суммаризации")

    chunk_texts = [c["chunk_text"] for c in chunks]
    _report("embedding", f"Векторизация {len(chunk_texts)} фрагментов…")
    vectors = embed_texts(chunk_texts)
    if len(vectors) != len(chunks):
        raise RuntimeError("Число эмбеддингов не совпало с числом чанков")

    meeting_dt = _parse_meeting_datetime(data.get("date_of_the_meeting", ""))

    _report("saving", "Запись встречи и чанков в PostgreSQL…")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                ALTER TABLE {_full_table(MEETINGS_TABLE)}
                ADD COLUMN IF NOT EXISTS participants TEXT DEFAULT ''
                """
            )
            cur.execute(
                f"""
                INSERT INTO {_full_table(MEETINGS_TABLE)} (
                    date_of_the_meeting,
                    name_of_the_meeting,
                    description,
                    participants,
                    summary_text
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    meeting_dt,
                    data.get("name_of_the_meeting", ""),
                    data.get("description", ""),
                    data.get("participants", ""),
                    data.get("summary_text", ""),
                ),
            )
            meeting_id = cur.fetchone()[0]

            for chunk, vector in zip(chunks, vectors):
                cur.execute(
                    f"""
                    INSERT INTO {_full_table(CHUNKS_TABLE)} (
                        meeting_id, chunk_index, chunk_text, embedding
                    )
                    VALUES (%s, %s, %s, %s::vector)
                    """,
                    (
                        meeting_id,
                        chunk["chunk_index"],
                        chunk["chunk_text"],
                        vector_to_pg(vector),
                    ),
                )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "id": meeting_id,
        "date_of_the_meeting": data.get("date_of_the_meeting"),
        "name_of_the_meeting": data.get("name_of_the_meeting"),
        "description": data.get("description"),
        "participants": data.get("participants", ""),
        "summary_text": data.get("summary_text"),
        "summary": data.get("summary_text"),
        "transcript": data.get("transcript", ""),
        "chunks_saved": len(chunks),
        "meta": {
            "date": data.get("date_of_the_meeting"),
            "title": data.get("name_of_the_meeting"),
            "description": data.get("description"),
            "participants": data.get("participants", ""),
            "file_name": data.get("file_name", ""),
        },
    }

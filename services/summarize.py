"""
Суммаризация транскрипта встречи через LiteLLM (OpenAI-совместимый API).
Принимает текст после transcribe.py и метаданные как в views/recall.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import re

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

load_dotenv()

# Промпт с правилами для LLM
PROMPT_FILE = Path(__file__).parent / "prompts" / "meeting_summary.md"


def _env(name: str, default: str = "") -> str:
    """Читает переменную из .env, убирает кавычки по краям."""
    return os.getenv(name, default).strip().strip('"')


def _chunk_count() -> int:
    """Сколько чанков просить у модели (по умолчанию 8)."""
    return int(_env("SUMMARY_CHUNK_COUNT", "8"))


def load_summary_prompt() -> str:
    """Загружает system-промпт из .md файла."""
    return PROMPT_FILE.read_text(encoding="utf-8")


def _build_llm() -> ChatOpenAI:
    """Клиент к RUVDS LiteLLM из .env."""
    base_url = _env("RUVDS_DE_LITELLM_BASE_URL")
    model = _env("RUVDS_DE_LITELLM_MODEL")
    api_key = _env("RUVDS_DE_LITELLM_METAPROMT_BULLEAD_KEY")

    if not base_url or not model or not api_key:
        raise RuntimeError(
            "Задай в .env: RUVDS_DE_LITELLM_BASE_URL, "
            "RUVDS_DE_LITELLM_MODEL, RUVDS_DE_LITELLM_METAPROMT_BULLEAD_KEY"
        )

    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.2,
    )


def _format_meta(meta: dict[str, Any]) -> dict[str, str]:
    """Поля как в recall.py: дата, название, описание, участники."""
    return {
        "date": str(meta.get("date", "")).strip() or "—",
        "title": str(meta.get("title", "")).strip() or "—",
        "description": str(meta.get("description", "")).strip() or "—",
        "participants": str(meta.get("participants", "")).strip() or "—",
    }


def summarize_meeting(transcript: str, meta: dict[str, Any]) -> str:
    """
    Отправляет транскрипт в LLM и возвращает текст суммаризации в markdown.
    meta — словарь с date, title, description (как после загрузки в recall).
    """
    transcript = (transcript or "").strip()
    if not transcript:
        raise ValueError("Пустой транскрипт — нечего суммаризировать")

    fields = _format_meta(meta)
    chunk_count = _chunk_count()

    # В system-промпт подставляем число чанков и шаблон метаданных
    system_text = load_summary_prompt()
    system_text = system_text.replace("{chunk_count}", str(chunk_count))
    system_text = system_text.replace("{date}", fields["date"])
    system_text = system_text.replace("{title}", fields["title"])
    system_text = system_text.replace("{description}", fields["description"])
    system_text = system_text.replace("{participants}", fields["participants"])

    user_text = f"""
Ниже полный транскрипт встречи. Сделай суммаризацию строго по формату из инструкции.
Чанков в ответе должно быть ровно: {chunk_count}.

=== МЕТАДАННЫЕ (дубль для контекста) ===
Дата: {fields["date"]}
Название: {fields["title"]}
Описание: {fields["description"]}
Участники: {fields["participants"]}

=== ТРАНСКРИПТ ===
{transcript}
""".strip()

    llm = _build_llm()
    response = llm.invoke(
        [
            SystemMessage(content=system_text),
            HumanMessage(content=user_text),
        ]
    )

    return str(response.content).strip()


def parse_summary_chunks(summary_text: str) -> list[dict[str, Any]]:
    """
    Достаёт блоки «## Чанк N» из markdown-суммаризации.
    Если формат сбился — кладёт весь текст в один чанк.
    """
    chunks: list[dict[str, Any]] = []
    pattern = re.compile(
        r"##\s*Чанк\s*(\d+)\s*\n(.*?)(?=\n##\s*|\Z)",
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(summary_text or ""):
        text = match.group(2).strip()
        if text:
            chunks.append({
                "chunk_index": int(match.group(1)),
                "chunk_text": text,
            })

    if not chunks and (summary_text or "").strip():
        chunks.append({"chunk_index": 1, "chunk_text": summary_text.strip()})

    chunks.sort(key=lambda x: x["chunk_index"])
    return chunks


def build_meeting_json(
    transcript: str,
    meta: dict[str, Any],
    *,
    file_name: str | None = None,
) -> dict[str, Any]:
    """
    Собирает данные встречи: метаданные, транскрипт, summary_text, чанки для БД.
    """
    fields = _format_meta(meta)
    summary_text = summarize_meeting(transcript, meta)
    chunks = parse_summary_chunks(summary_text)

    return {
        "date_of_the_meeting": fields["date"],
        "name_of_the_meeting": fields["title"],
        "description": fields["description"],
        "participants": fields["participants"],
        "summary_text": summary_text,
        "transcript": transcript.strip(),
        "chunks": chunks,
        "file_name": (file_name or meta.get("file_name") or "").strip(),
    }


def meeting_json_to_file(payload: dict[str, Any], path: str | Path) -> Path:
    """Записывает JSON на диск (для отладки или экспорта)."""
    out = Path(path)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out

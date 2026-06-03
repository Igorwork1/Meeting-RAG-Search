"""
LLM-препроцессинг пользовательского вопроса для RAG.

Цель: до векторного поиска получить:
- semantic_query (что эмбеддить)
- date/date_from/date_to (если в вопросе указано, когда была встреча)

Важно: по умолчанию date = текущая (самая актуальная) дата.
Если в вопросе есть явное/относительное указание времени встречи ("вчера", "26 октября",
"в прошлый вторник"), date может быть изменена на соответствующую дату.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import re
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from services.summarize import _build_llm


@dataclass
class PreprocessedQuery:
    original_question: str
    normalized_question: str
    semantic_query: str

    # "date" — дата встречи, если вопрос её явно подразумевает.
    # По умолчанию выставляется на текущую дату, но может быть изменена LLM.
    date: date
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    intent: str = "semantic_search"
    raw_llm: str = ""


_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None

    m = _JSON_RE.search(text)
    if not m:
        return None

    blob = m.group(0)
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _parse_iso_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"null", "none", "-"}:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def preprocess_user_question(question: str, *, now: datetime | None = None) -> PreprocessedQuery:
    """
    Превращает исходный вопрос в контекст для поиска:
    - date (по умолчанию сегодня; может измениться, если в вопросе указана дата встречи)
    - semantic_query (очищенный смысловой запрос для эмбеддингов)
    """
    q = (question or "").strip()
    if not q:
        raise ValueError("Пустой вопрос")

    now = now or datetime.now()
    current_date = now.date()

    system_text = f"""
Ты — модуль препроцессинга запросов для RAG-системы по протоколам встреч.

Дано:
- Текущая дата (самая актуальная): {current_date.isoformat()}
- Вопрос пользователя на русском.

Нужно:
1) Ввести переменную date: по умолчанию date = текущая дата.
2) Если в вопросе есть указание, когда было совещание (явная дата или относительная: "вчера", "позавчера",
   "на прошлой неделе", "в прошлый вторник", "26 октября" и т.п.), измени date на нужную дату.
   Если указана именно дата встречи — используй её. Если указан диапазон — заполни date_from/date_to.
3) Сформируй semantic_query — короткий смысловой запрос, который нужно эмбеддить для поиска по чанкам встреч.
   Убери из semantic_query служебные фразы про даты/временные указатели, если они не несут смысла вопроса.

Верни ТОЛЬКО валидный JSON без пояснений и без markdown. Схема:
{{
  "normalized_question": "строка (переформулированный/нормализованный вопрос, без потери смысла)",
  "semantic_query": "строка (для эмбеддингов)",
  "intent": "semantic_search|meeting_summary|decisions_search|tasks_search",
  "date": "YYYY-MM-DD",
  "date_from": "YYYY-MM-DD или null",
  "date_to": "YYYY-MM-DD или null"
}}

Правила:
- date обязателен всегда (если нет указаний в вопросе — ставь текущую дату).
- date_from/date_to можно вернуть null.
""".strip()

    llm = _build_llm()
    resp = llm.invoke(
        [
            SystemMessage(content=system_text),
            HumanMessage(content=q),
        ]
    )
    raw = str(getattr(resp, "content", "")).strip()
    data = _extract_json(raw) or {}

    normalized_question = str(data.get("normalized_question") or q).strip() or q
    semantic_query = str(data.get("semantic_query") or q).strip() or q

    # date: по умолчанию текущая; если LLM вернул дату — подставляем её.
    meeting_date = _parse_iso_date(data.get("date")) or current_date
    date_from = _parse_iso_date(data.get("date_from"))
    date_to = _parse_iso_date(data.get("date_to"))

    # Если модель отдала диапазон из одного дня — нормализуем как один день.
    if date_from and not date_to:
        date_to = date_from
    if date_to and not date_from:
        date_from = date_to

    intent = str(data.get("intent") or "semantic_search").strip() or "semantic_search"
    if intent not in {"semantic_search", "meeting_summary", "decisions_search", "tasks_search"}:
        intent = "semantic_search"

    return PreprocessedQuery(
        original_question=q,
        normalized_question=normalized_question,
        semantic_query=semantic_query,
        date=meeting_date,
        date_from=date_from,
        date_to=date_to,
        intent=intent,
        raw_llm=raw,
    )


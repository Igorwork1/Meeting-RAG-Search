# pip install rapidfuzz dateparser

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import dateparser
from rapidfuzz import process, fuzz


@dataclass
class ParsedQuery:
    original_query: str
    normalized_query: str

    intent: str
    semantic_query: str

    date_from: Optional[date] = None
    date_to: Optional[date] = None

    status: Optional[str] = None
    object_type: Optional[str] = None

    sort_by: Optional[str] = None
    limit: Optional[int] = None

    corrected_terms: dict = field(default_factory=dict)


RELATIVE_DATE_WORDS = {
    "сегодня": "today",
    "вчера": "yesterday",
    "позавчера": "day_before_yesterday",
    "завтра": "tomorrow",
}

STATUS_WORDS = {
    "готово": "completed",
    "готовые": "completed",
    "завершено": "completed",
    "завершенные": "completed",
    "завершенные": "completed",
    "обработано": "completed",

    "в обработке": "processing",
    "обрабатывается": "processing",

    "ошибка": "failed",
    "упало": "failed",
    "не обработалось": "failed",
    "необработанные": "failed",
}

OBJECT_WORDS = {
    "собрание": "meeting",
    "собрании": "meeting",
    "встреча": "meeting",
    "встрече": "meeting",
    "созвон": "call",
    "созвоне": "call",
    "звонок": "call",
    "звонке": "call",
    "разговор": "call",
    "разговоре": "call",
}

WEEKDAYS = {
    "понедельник": 0,
    "понедельникe": 0,
    "вторник": 1,
    "вторнике": 1,
    "среда": 2,
    "среду": 2,
    "среде": 2,
    "четверг": 3,
    "четверге": 3,
    "пятница": 4,
    "пятницу": 4,
    "пятнице": 4,
    "суббота": 5,
    "субботу": 5,
    "субботе": 5,
    "воскресенье": 6,
    "воскресенье": 6,
}

FUZZY_DICTIONARY = (
    list(RELATIVE_DATE_WORDS.keys())
    + list(STATUS_WORDS.keys())
    + list(OBJECT_WORDS.keys())
    + list(WEEKDAYS.keys())
    + [
        "прошлый", "прошлую", "прошлое",
        "этот", "эту", "это",
        "последний", "последнем", "последняя", "последнюю",
    ]
)


def normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s\.\-\/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fix_typos(text: str, threshold: int = 78) -> tuple[str, dict]:
    words = text.split()
    result = []
    corrected = {}

    for word in words:
        if len(word) < 4:
            result.append(word)
            continue

        match = process.extractOne(
            word,
            FUZZY_DICTIONARY,
            scorer=fuzz.ratio,
        )

        if match:
            best_word, score, _ = match
            if score >= threshold and best_word != word:
                corrected[word] = best_word
                result.append(best_word)
                continue

        result.append(word)

    return " ".join(result), corrected


def parse_relative_date(text: str, today: date) -> tuple[Optional[date], Optional[date]]:
    if "сегодня" in text:
        return today, today

    if "позавчера" in text:
        d = today - timedelta(days=2)
        return d, d

    if "вчера" in text:
        d = today - timedelta(days=1)
        return d, d

    if "завтра" in text:
        d = today + timedelta(days=1)
        return d, d

    if "на этой неделе" in text or "за эту неделю" in text:
        start = today - timedelta(days=today.weekday())
        return start, today

    if "на прошлой неделе" in text or "за прошлую неделю" in text:
        start_this_week = today - timedelta(days=today.weekday())
        start_prev_week = start_this_week - timedelta(days=7)
        end_prev_week = start_this_week - timedelta(days=1)
        return start_prev_week, end_prev_week

    if "в этом месяце" in text or "за этот месяц" in text:
        start = today.replace(day=1)
        return start, today

    return None, None


def parse_relative_weekday(text: str, today: date) -> tuple[Optional[date], Optional[date]]:
    found_weekday = None

    for word, weekday_index in WEEKDAYS.items():
        if word in text:
            found_weekday = weekday_index
            break

    if found_weekday is None:
        return None, None

    days_ago = (today.weekday() - found_weekday) % 7

    if any(x in text for x in ["прошлый", "прошлую", "прошлое"]):
        days_ago = days_ago + 7 if days_ago != 0 else 7

    elif any(x in text for x in ["этот", "эту", "это"]):
        days_ago = days_ago

    else:
        # "во вторник" без уточнения — ближайший прошедший вторник
        days_ago = days_ago if days_ago != 0 else 7

    d = today - timedelta(days=days_ago)
    return d, d


def parse_explicit_date(text: str, today: date) -> tuple[Optional[date], Optional[date]]:
    settings = {
        "PREFER_DATES_FROM": "past",
        "RELATIVE_BASE": datetime(today.year, today.month, today.day),
        "DATE_ORDER": "DMY",
    }

    parsed = dateparser.parse(
        text,
        languages=["ru"],
        settings=settings,
    )

    if parsed:
        d = parsed.date()
        return d, d

    return None, None


def extract_status(text: str) -> Optional[str]:
    for ru_status, db_status in STATUS_WORDS.items():
        if ru_status in text:
            return db_status
    return None


def extract_object_type(text: str) -> Optional[str]:
    for word, object_type in OBJECT_WORDS.items():
        if word in text:
            return object_type
    return None


def extract_recency_rule(text: str) -> tuple[Optional[str], Optional[int]]:
    if any(x in text for x in ["последний", "последнем", "последняя", "последнюю"]):
        return "date_of_the_meeting_desc", 1

    return None, None


def detect_intent(text: str) -> str:
    if any(x in text for x in ["что было", "о чем", "обсуждали", "итоги", "резюме"]):
        return "meeting_summary"

    if any(x in text for x in ["что решили", "решения", "договорились"]):
        return "decisions_search"

    if any(x in text for x in ["задачи", "что сделать", "поручения"]):
        return "tasks_search"

    if any(x in text for x in ["найди", "покажи", "где говорили"]):
        return "semantic_search"

    return "semantic_search"


def build_semantic_query(text: str) -> str:
    service_phrases = [
        "сегодня", "вчера", "позавчера", "завтра",
        "на этой неделе", "за эту неделю",
        "на прошлой неделе", "за прошлую неделю",
        "в этом месяце", "за этот месяц",
        "прошлый", "прошлую", "прошлое",
        "этот", "эту", "это",
        "последний", "последнем", "последняя", "последнюю",
    ]

    semantic = text

    for phrase in service_phrases:
        semantic = semantic.replace(phrase, " ")

    for word in list(OBJECT_WORDS.keys()) + list(STATUS_WORDS.keys()) + list(WEEKDAYS.keys()):
        semantic = semantic.replace(word, " ")

    semantic = re.sub(r"\s+", " ", semantic).strip()

    weak_queries = {
        "",
        "что было",
        "о чем говорили",
        "что обсуждали",
        "что решили",
    }

    if semantic in weak_queries:
        return "краткое содержание встречи обсуждения решения итоги задачи"

    return semantic


def parse_user_query(query: str, today: Optional[date] = None) -> ParsedQuery:
    today = today or date.today()

    original = query
    normalized = normalize_text(query)
    fixed, corrected_terms = fix_typos(normalized)

    date_from, date_to = parse_relative_date(fixed, today)

    if not date_from:
        date_from, date_to = parse_relative_weekday(fixed, today)

    if not date_from:
        date_from, date_to = parse_explicit_date(fixed, today)

    status = extract_status(fixed)
    object_type = extract_object_type(fixed)
    sort_by, limit = extract_recency_rule(fixed)

    intent = detect_intent(fixed)
    semantic_query = build_semantic_query(fixed)

    return ParsedQuery(
        original_query=original,
        normalized_query=fixed,
        intent=intent,
        semantic_query=semantic_query,
        date_from=date_from,
        date_to=date_to,
        status=status,
        object_type=object_type,
        sort_by=sort_by,
        limit=limit,
        corrected_terms=corrected_terms,
    )


if __name__ == "__main__":
    examples = [
        "Что было на собрании сеолня?",
        "Что обсуждали на созвоне сегодня?",
        "Что было в прошлый вторник?",
        "Что решили в последнем разговоре?",
        "Покажи завершенные встречи за прошлую неделю",
        "Что решили 26 октября?",
        "Найди где говорили про архитектуру RAG",
    ]

    for q in examples:
        parsed = parse_user_query(q, today=date(2026, 5, 8))
        print("\nQUERY:", q)
        print(parsed)
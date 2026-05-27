import streamlit as st

try:
    from services.api import ask_chat
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from services.api import ask_chat


st.title("Chat Bot")
st.caption("Вопросы по сохранённым созвонам (RAG)")


def format_chat_history(messages: list[dict], last_n: int = 6) -> str:
    lines: list[str] = []
    for msg in messages[-last_n:]:
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines) if lines else "—"


def render_sources(sources: list[dict]) -> None:
    """Показывает найденные фрагменты и косинусную релевантность."""
    if not sources:
        return

    with st.expander(f"Источники ({len(sources)})", expanded=False):
        for src in sources:
            rank = src.get("rank", "—")
            title = src.get("meeting_title") or "Встреча"
            meeting_date = src.get("meeting_date") or "—"
            chunk_index = src.get("chunk_index", "—")
            relevance = src.get("relevance_percent")
            similarity = src.get("cosine_similarity")
            distance = src.get("cosine_distance")

            if relevance is not None:
                score_line = f"**Релевантность:** {relevance}% (cosine similarity {similarity:.4f}, distance {distance:.4f})"
            else:
                score_line = "**Релевантность:** —"

            st.markdown(
                f"**#{rank}** · {title} · {meeting_date} · чанк {chunk_index}\n\n"
                f"{score_line}"
            )
            snippet = src.get("snippet") or ""
            if snippet:
                st.caption(snippet)
            st.divider()


if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Привет! Я Кибер-помощник команды MetaPrompt. "
                "Спроси, что обсуждали на созвонах — поищу в базе встреч."
            ),
        }
    ]

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sources"):
            render_sources(m["sources"])

prompt = st.chat_input("Ваш вопрос о встречах…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    history = format_chat_history(st.session_state.messages[:-1])
    sources: list[dict] = []

    try:
        with st.spinner("Разбираю вопрос и ищу в базе встреч…"):
            resp = ask_chat(prompt, chat_history=history)
    except Exception as e:
        answer = f"Не удалось получить ответ: {e}"
    else:
        answer = resp["answer"]
        sources = resp.get("sources") or []
        if resp.get("sources_count", 0) == 0:
            answer += "\n\n_В базе пока нет чанков встреч. Сначала загрузите аудио на странице Download._"

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources}
    )
    with st.chat_message("assistant"):
        st.markdown(answer)
        if sources:
            render_sources(sources)

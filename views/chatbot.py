import streamlit as st

try:
    from services.rag import ask
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from services.rag import ask


st.title("Chat Bot")
st.caption("Вопросы по сохранённым созвонам (RAG)")


def format_chat_history(messages: list[dict], last_n: int = 6) -> str:
    """Последние реплики для контекста LLM."""
    lines: list[str] = []
    for msg in messages[-last_n:]:
        role = "Пользователь" if msg["role"] == "user" else "Ассистент"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines) if lines else "—"


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

prompt = st.chat_input("Ваш вопрос о встречах…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    history = format_chat_history(st.session_state.messages[:-1])
    parsed_info = None

    try:
        with st.spinner("Разбираю вопрос и ищу в базе встреч…"):
            resp = ask(prompt, chat_history=history)
    except Exception as e:
        answer = f"Не удалось получить ответ: {e}"
        quotes = []
    else:
        answer = resp["answer"]
        quotes = resp.get("quotes", [])
        parsed_info = resp.get("parsed")
        if resp.get("sources_count", 0) == 0:
            answer += "\n\n_В базе пока нет чанков встреч. Сначала загрузите аудио на странице Download._"

    if quotes:
        answer += "\n\n**Источники:**\n" + "\n".join(f"- {q}" for q in quotes)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)
        if parsed_info:
            with st.expander("Как понят вопрос"):
                st.write(f"**Поиск в базе:** {parsed_info.get('semantic_query', '—')}")
                st.write(f"**Тип:** {parsed_info.get('intent', '—')}")
                if parsed_info.get("date_from"):
                    st.write(
                        f"**Даты:** {parsed_info.get('date_from')} — "
                        f"{parsed_info.get('date_to') or parsed_info.get('date_from')}"
                    )
                if parsed_info.get("corrected_terms"):
                    st.write("**Опечатки:**", parsed_info.get("corrected_terms"))

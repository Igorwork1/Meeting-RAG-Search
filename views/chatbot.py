import streamlit as st

try:
    from services.api import chat
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from services.api import chat

st.title("Chat Bot")

# 1) сообщения
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Привет, я Кибер-помощник команды MetaPromt. Помогу ответить, что было на созвонах!"
        }
    ]

# 2) conversation_id (как будто выдаёт бэк)
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

# отрисовка истории
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ввод
prompt = st.chat_input("Type your message...")
if prompt:
    # user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # assistant (через stub api)
    resp = chat(message=prompt, conversation_id=st.session_state.conversation_id)
    st.session_state.conversation_id = resp["conversation_id"]

    answer = resp["answer"]
    quotes = resp.get("quotes", [])

    # красиво добавим цитаты курсивом
    if quotes:
        answer += "\n\n" + "\n".join([f"*{q}*" for q in quotes])

    st.session_state.messages.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)
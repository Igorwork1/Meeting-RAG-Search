import streamlit as st

# ---SHARED ON ALL PAGES ---
st.set_page_config(page_title="MetaPromt: CyberEcho", layout="wide")
st.sidebar.text("Service for the team")

# -- PAGE SETUP ---
about_service = st.Page(
    page = "about_service.py",
    title = "About Service",
    icon = ":material/info:",
    default=True,
)

project_1_page = st.Page(
    page = "recall.py",
    title = "Download Page",
    icon = ":material/download:",
)

project_2_page = st.Page(
    page = "chatbot.py",
    title = "Chat Bot",
    icon = ":material/smart_toy:",
)

# -- NAVIGATION SETUP [WITH SECTIONS] ---
pg = st.navigation(
    {
        "Tools": [project_1_page, project_2_page],
        "Info": [about_service],
    }
)
# -- NAVIGATION RUN ---
pg.run()
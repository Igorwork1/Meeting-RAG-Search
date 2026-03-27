import streamlit as st
from pathlib import Path
import sys

# Allow running Streamlit from `views/` while importing top-level modules like `services.*`
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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

# -- NAVIAGATION SETUP [WITH SECTIONS] ---
pg = st.navigation(
    {
        "Tools": [project_1_page, project_2_page],
        "Info": [about_service],
    }
)
# -- NAVIAGATION RUN ---
pg.run()
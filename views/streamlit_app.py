import streamlit as st

st.set_page_config(page_title="MetaPromt: CyberEcho", layout="wide")
st.sidebar.text("Service for the team")


def _refresh_meeting_jobs() -> None:
    """Обновляет статусы фоновых задач (общий session_state для всех страниц)."""
    if "meeting_jobs" not in st.session_state:
        st.session_state.meeting_jobs = []
        return

    try:
        from services import api as services_api
    except ModuleNotFoundError:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from services import api as services_api

    import importlib

    importlib.reload(services_api)
    get_meeting_job_status = services_api.get_meeting_job_status

    updated: list[dict] = []
    for job in st.session_state.meeting_jobs:
        if job.get("status") in ("done", "failed"):
            updated.append(job)
            continue
        try:
            status = get_meeting_job_status(job["job_id"])
            updated.append({**job, **status})
        except Exception:
            updated.append(job)
    st.session_state.meeting_jobs = updated


_refresh_meeting_jobs()

active = [j for j in st.session_state.meeting_jobs if j.get("status") in ("queued", "processing")]
if active:
    st.sidebar.markdown("**Фоновая обработка**")
    for job in active:
        stage = job.get("stage_label") or job.get("stage", "…")
        pct = job.get("progress_percent")
        suffix = f" ({pct}%)" if pct is not None else ""
        st.sidebar.caption(f"⏳ {job.get('title', '—')}")
        st.sidebar.caption(f"   {stage}{suffix}")

about_service = st.Page(
    page="about_service.py",
    title="About Service",
    icon=":material/info:",
    default=True,
)

project_1_page = st.Page(
    page="recall.py",
    title="Download Page",
    icon=":material/download:",
)

project_2_page = st.Page(
    page="chatbot.py",
    title="Chat Bot",
    icon=":material/smart_toy:",
)

pg = st.navigation(
    {
        "Tools": [project_1_page, project_2_page],
        "Info": [about_service],
    }
)
pg.run()

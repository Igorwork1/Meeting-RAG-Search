import importlib
from datetime import date

import streamlit as st

try:
    from services import api as services_api
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from services import api as services_api

# Streamlit кэширует модули — подтягиваем актуальный UploadMeta с полем participants
importlib.reload(services_api)
process_meeting = services_api.process_meeting
check_api_health = services_api.check_api_health
UploadMeta = services_api.UploadMeta

_STEP_ICONS = {
    "done": "✅",
    "current": "🔄",
    "pending": "⬜",
    "failed": "❌",
}


def _render_job_card(job: dict) -> None:
    title = job.get("title") or "—"
    job_id = job.get("job_id", "")
    status = job.get("status", "")
    stage_label = job.get("stage_label") or status
    message = job.get("message", "")
    pct = job.get("progress_percent", 0)

    st.markdown(f"**{title}** · `{job_id}`")
    if status in ("queued", "processing"):
        st.progress(min(max(int(pct), 0), 100) / 100.0, text=stage_label)
        if message:
            st.caption(message)

    steps = job.get("steps") or []
    if steps:
        for step in steps:
            icon = _STEP_ICONS.get(step.get("status", ""), "•")
            label = step.get("label", step.get("id", ""))
            line = f"{icon} {label}"
            if step.get("status") == "current" and message and step.get("id") == job.get("stage"):
                line += f" — _{message}_"
            st.markdown(line)
    elif status == "done":
        st.success("Готово")
    elif status == "failed":
        st.error(job.get("error", "неизвестно"))


st.title("Загрузка")
st.caption("Загрузка аудио + метаданные (дата, название, описание)")

if not check_api_health():
    st.warning(
        "Бэкенд не запущен. "
        "В отдельном терминале: `uvicorn services.main:app --host 127.0.0.1 --port 8000`"
    )

if "meeting_jobs" not in st.session_state:
    st.session_state.meeting_jobs = []

active = [j for j in st.session_state.meeting_jobs if j.get("status") in ("queued", "processing")]
done = [j for j in st.session_state.meeting_jobs if j.get("status") == "done"]
failed = [j for j in st.session_state.meeting_jobs if j.get("status") == "failed"]

if st.session_state.meeting_jobs:
    st.subheader("Задачи обработки")
    if active:
        st.info(
            f"В фоне: **{len(active)}** — можно перейти в **Чат**, задача не прервётся."
        )
        for job in active:
            with st.container(border=True):
                _render_job_card(job)
        if st.button("Обновить статус", key="refresh_jobs"):
            st.rerun()
    else:
        st.caption("Нет активных задач.")

    for job in done:
        with st.container(border=True):
            st.success(f"Готово: **{job.get('title', '—')}** · id `{job.get('id')}`")
            _render_job_card(job)

    for job in failed:
        with st.container(border=True):
            st.error(f"Ошибка «{job.get('title', '—')}»: {job.get('error', 'неизвестно')}")
            _render_job_card(job)

    if st.button("Очистить список задач"):
        st.session_state.meeting_jobs = []
        st.rerun()
    st.divider()

with st.form("upload_form", clear_on_submit=False):
    audio_file = st.file_uploader(
        "Аудиофайл",
        type=["mp3", "wav"],
        accept_multiple_files=False,
        help="Поддерживаются MP3/WAV.",
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        meeting_date = st.date_input("Дата", value=date.today())
    with col2:
        title = st.text_input("Название (обязательно)")

    description = st.text_area("Краткое описание (опционально)")
    participants = st.text_input("Участники (опционально)", placeholder="Иван, Мария, …")

    submit = st.form_submit_button("Запустить обработку")

st.markdown(
    """
<style>
div[data-testid="stFileUploaderDropzoneInstructions"] { display: none; }
</style>
""",
    unsafe_allow_html=True,
)

if submit:
    if audio_file is None:
        st.error("Выбери аудиофайл.")
        st.stop()
    if not title.strip():
        st.error("Название обязательно.")
        st.stop()

    meta = UploadMeta(
        date=meeting_date.isoformat(),
        title=title.strip(),
        description=description.strip(),
        participants=participants.strip(),
    )

    try:
        with st.spinner("Отправка файла на сервер…"):
            result = process_meeting(
                file_name=audio_file.name,
                file_bytes=audio_file.getvalue(),
                mime_type=audio_file.type or "application/octet-stream",
                meta=meta,
            )
    except Exception as e:
        st.error(f"Ошибка: {e}")
        st.stop()

    st.session_state.meeting_jobs.append(
        {
            "job_id": result.get("job_id"),
            "status": result.get("status", "queued"),
            "title": meta.title,
            "date": meta.date,
            "stage": result.get("stage", "queued"),
            "stage_label": result.get("stage_label", "В очереди"),
            "steps": result.get("steps", []),
            "progress_percent": result.get("progress_percent", 0),
            "message": "",
        }
    )
    st.rerun()

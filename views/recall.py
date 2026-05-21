from datetime import date

import streamlit as st

try:
    from services.api import transcribe_audio, check_api_health, UploadMeta
    from services.db import save_meeting_record
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from services.api import transcribe_audio, check_api_health, UploadMeta
    from services.db import save_meeting_record


st.title("Download Recall")
st.caption("Загрузка аудио + метаданные (дата, название, описание)")

if not check_api_health():
    st.warning(
        "Бэкенд транскрибации не запущен. "
        "В отдельном терминале: `uvicorn services.transcribe:app --host 127.0.0.1 --port 8000`"
    )

# Только краткий итог после сохранения (без транскрипта и суммаризации на экране)
if "last_success" not in st.session_state:
    st.session_state.last_success = None

if st.session_state.last_success:
    info = st.session_state.last_success
    st.success(
        f"Встреча **{info.get('title', '—')}** ({info.get('date', '')}) "
        f"сохранена в БД. id: `{info.get('id')}`"
    )
    if st.button("Загрузить ещё одну встречу"):
        st.session_state.last_success = None
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

    submit = st.form_submit_button("Транскрибировать и сохранить")

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
    )

    try:
        with st.spinner("Обработка: транскрибация → суммаризация → сохранение в БД…"):
            result = transcribe_audio(
                file_name=audio_file.name,
                file_bytes=audio_file.getvalue(),
                mime_type=audio_file.type or "application/octet-stream",
                meta=meta,
            )
            meta_dict = result.get(
                "meta",
                {"date": meta.date, "title": meta.title, "description": meta.description},
            )
            meta_dict["file_name"] = audio_file.name

            saved = save_meeting_record(
                result.get("transcript", ""),
                meta_dict,
                file_name=audio_file.name,
            )
    except Exception as e:
        st.error(f"Ошибка: {e}")
        st.stop()

    st.session_state.last_success = {
        "id": saved.get("id"),
        "title": meta.title,
        "date": meta.date,
    }
    st.rerun()

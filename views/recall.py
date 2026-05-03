import time
from datetime import date

import streamlit as st

try:
    from services.api import upload_audio, get_job_status, UploadMeta
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from services.api import upload_audio, get_job_status, UploadMeta

POLL_INTERVAL_SEC = 8  # фиксированный polling раз в 8 секунд


st.title("Download Recall")
st.caption("Загрузка аудио + метаданные (дата, название, описание)")

# --- session state init
if "active_job_id" not in st.session_state:
    st.session_state.active_job_id = None
if "last_job_id" not in st.session_state:
    st.session_state.last_job_id = ""


# --- если есть активный job — покажем прогресс + авто-обновление
active_status = None
is_processing = False

if st.session_state.active_job_id:
    active_status = get_job_status(st.session_state.active_job_id)
    status = active_status.get("status")

    if status == "processing":
        is_processing = True

        stage = active_status.get("stage", "processing")
        stage_i = active_status.get("stage_index", 1)
        stage_total = active_status.get("stage_total", 1)
        overall = float(active_status.get("progress", 0.0))

        st.info(f"⏳ Обработка идёт. Job: `{st.session_state.active_job_id}`")
        st.progress(overall)
        st.write(f"Этап: **{stage}** ({stage_i}/{stage_total})")

        with st.expander("Детали"):
            st.write(active_status.get("meta", {}))
            st.write(active_status.get("file", {}))

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔄 Обновить сейчас"):
                st.rerun()
        with col2:
            if st.button("🧹 Сбросить job (если зависло)"):
                # Для MVP — просто очистка состояния UI.
                # В реальном бэке лучше: /cancel или /jobs/{id}/cancel
                st.session_state.active_job_id = None
                st.rerun()

        # --- авто polling (MVP): раз в 8 секунд дергаем статус
        time.sleep(POLL_INTERVAL_SEC)
        st.rerun()

    elif status == "done":
        st.success(f"✅ Готово! Job: `{st.session_state.active_job_id}`")
        res = active_status.get("result", {})
        st.write(res.get("transcript_preview", ""))

        # освобождаем upload
        st.session_state.active_job_id = None

    elif status == "not_found":
        st.warning("Job не найден. Возможно, был сброшен или потерян.")
        st.session_state.active_job_id = None

st.divider()

# --- upload form (блокируем, пока processing)
disable_upload = is_processing

with st.form("upload_form", clear_on_submit=False):
    audio_file = st.file_uploader(
        "Аудиофайл",
        type=["mp3", "wav"],
        accept_multiple_files=False,
        help="Поддерживаются MP3/WAV.",
        disabled=disable_upload,
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        meeting_date = st.date_input("Дата", value=date.today(), disabled=disable_upload)
    with col2:
        title = st.text_input("Название (обязательно)", disabled=disable_upload)

    description = st.text_area("Краткое описание (опционально)", disabled=disable_upload)

    submit = st.form_submit_button("Load / Upload", disabled=disable_upload)

# косметика (опционально)
st.markdown("""
<style>
div[data-testid="stFileUploaderDropzoneInstructions"] { display: none; }
</style>
""", unsafe_allow_html=True)

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

    job_id = upload_audio(
        file_name=audio_file.name,
        file_bytes=audio_file.getvalue(),
        mime_type=audio_file.type or "application/octet-stream",
        meta=meta,
    )

    st.session_state.active_job_id = job_id
    st.session_state.last_job_id = job_id
    st.success(f"Задача создана: `{job_id}`")

    # сразу обновимся, чтобы увидеть прогресс
    st.rerun()
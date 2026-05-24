"""Этапы фоновой обработки встречи (транскрибация → БД)."""
from __future__ import annotations

from typing import Any, Callable

# (id, подпись для UI)
PIPELINE_STEPS: list[tuple[str, str]] = [
    ("queued", "В очереди"),
    ("loading_model", "Загрузка модели GigaAM"),
    ("splitting", "Нарезка аудио"),
    ("transcribing", "Транскрибация"),
    ("summarizing", "Суммаризация встречи"),
    ("embedding", "Создание эмбеддингов"),
    ("saving", "Сохранение в БД"),
    ("done", "Готово"),
]

WORK_STEP_IDS = [sid for sid, _ in PIPELINE_STEPS if sid != "done"]
STEP_LABELS = dict(PIPELINE_STEPS)

ProgressCallback = Callable[[str, str], None]


def build_steps(current_stage: str, *, failed: bool = False) -> list[dict[str, str]]:
    """Список этапов со статусами: done | current | pending | failed."""
    try:
        cur_idx = WORK_STEP_IDS.index(current_stage)
    except ValueError:
        cur_idx = len(WORK_STEP_IDS) - 1 if current_stage == "done" else 0

    steps: list[dict[str, str]] = []
    for i, step_id in enumerate(WORK_STEP_IDS):
        label = STEP_LABELS[step_id]
        if failed and i == cur_idx:
            status = "failed"
        elif current_stage == "done" or i < cur_idx:
            status = "done"
        elif i == cur_idx:
            status = "current"
        else:
            status = "pending"
        steps.append({"id": step_id, "label": label, "status": status})

    if current_stage == "done":
        steps.append({"id": "done", "label": STEP_LABELS["done"], "status": "done"})
    return steps


def progress_percent(current_stage: str, *, chunk_current: int = 0, chunk_total: int = 0) -> int:
    n = len(WORK_STEP_IDS)
    if n == 0:
        return 0
    try:
        idx = WORK_STEP_IDS.index(current_stage)
    except ValueError:
        return 100 if current_stage == "done" else 0

    base = (idx / n) * 100
    if current_stage == "transcribing" and chunk_total > 0:
        chunk_part = (chunk_current / chunk_total) * (100 / n)
        return min(99, int(base + chunk_part))
    if current_stage == "done":
        return 100
    return min(99, int(base))


class JobProgress:
    """Обновляет запись задачи в _JOBS по мере прохождения пайплайна."""

    def __init__(self, jobs: dict[str, dict[str, Any]], job_id: str) -> None:
        self._jobs = jobs
        self._job_id = job_id
        self._chunk_current = 0
        self._chunk_total = 0

    def set_stage(
        self,
        stage_id: str,
        message: str = "",
        *,
        failed: bool = False,
        chunk_current: int | None = None,
        chunk_total: int | None = None,
    ) -> None:
        job = self._jobs.get(self._job_id)
        if not job:
            return

        if chunk_current is not None:
            self._chunk_current = chunk_current
        if chunk_total is not None:
            self._chunk_total = chunk_total

        job["stage"] = stage_id
        job["stage_label"] = STEP_LABELS.get(stage_id, stage_id)
        job["message"] = message
        job["steps"] = build_steps(stage_id, failed=failed)
        job["progress_percent"] = progress_percent(
            stage_id,
            chunk_current=self._chunk_current,
            chunk_total=self._chunk_total,
        )
        if chunk_total:
            job["chunk_current"] = self._chunk_current
            job["chunk_total"] = self._chunk_total

        if stage_id == "done":
            job["status"] = "done"
        elif failed:
            job["status"] = "failed"
        elif stage_id != "queued":
            job["status"] = "processing"

    def callback(self) -> ProgressCallback:
        def _cb(stage_id: str, message: str = "") -> None:
            kw: dict[str, Any] = {}
            if stage_id == "transcribing" and " из " in message:
                # «Фрагмент 3 из 12»
                try:
                    parts = message.split()
                    kw["chunk_current"] = int(parts[1])
                    kw["chunk_total"] = int(parts[3])
                except (ValueError, IndexError):
                    pass
            self.set_stage(stage_id, message, **kw)

        return _cb

"""Ручная проверка transcribe_file. Запуск из корня проекта:

    python tests\\test_transcribe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# При `python tests/test_transcribe.py` в sys.path попадает tests/, а не корень — добавляем его
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.transcribe import transcribe_file

# AUDIO_PATH = r"C:\Users\prese\Downloads\Dora_-_lonli_lav_81100286.mp3"
# AUDIO_PATH_60 = r"C:\Users\prese\Downloads\МЕТАПР - Интелоджик - 30 September 2025 (online-audio-converter.com).mp3"
# AUDIO_PATH = r"C:\Users\prese\Downloads\МЕТАПР - статус звонок - 12 May 2026.wav"
# AUDIO_PATH_60 = r"C:\Users\prese\Downloads\1. Аудиозапись семинара_15 мая_2026.m4a"
AUDIO_PATH_120 = r"C:\Users\prese\Downloads\тест120.wav"


def main() -> None:
    text = transcribe_file(AUDIO_PATH_120, chunk_seconds=10)
    print("\n=== TRANSCRIPTION (Проверяем созвон) ===")
    print(text)


if __name__ == "__main__":
    main()

from services.transcribe import transcribe_file

# AUDIO_PATH = r"C:\Users\prese\Downloads\Dora_-_lonli_lav_81100286.mp3"
AUDIO_PATH = r"C:\Users\prese\Downloads\МЕТАПР - Интелоджик - 30 September 2025 (online-audio-converter.com).mp3"

text = transcribe_file(AUDIO_PATH, chunk_seconds=10)

print("\n=== TRANSCRIPTION (Проверяем созвон) ===")
print(text)
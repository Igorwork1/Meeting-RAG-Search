CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS cyberecho_meetings (
    id SERIAL PRIMARY KEY,
    date_of_the_meeting TIMESTAMP,
    name_of_the_meeting VARCHAR(255),
    description TEXT,
    participants TEXT DEFAULT '',
    summary_text TEXT
);

CREATE TABLE IF NOT EXISTS cyberecho_meeting_chunks (
    id SERIAL PRIMARY KEY,
    meeting_id INTEGER NOT NULL REFERENCES cyberecho_meetings(id) ON DELETE CASCADE,
    chunk_index INTEGER,
    chunk_text TEXT,
    embedding VECTOR(2048)
);

CREATE TABLE IF NOT EXISTS cyberecho_meeting_asks (
    id SERIAL PRIMARY KEY,
    question TEXT,
    answer TEXT
);

-- если таблица уже была без participants:
ALTER TABLE cyberecho_meetings
    ADD COLUMN IF NOT EXISTS participants TEXT DEFAULT '';

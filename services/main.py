"""
Главный FastAPI-бэкенд Cyberecho.
Запуск: uvicorn services.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from services.routes import chat, meetings, system, transcribe

load_dotenv()

app = FastAPI(title="Cyberecho API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роуты из отдельных модулей
app.include_router(system.router)
app.include_router(transcribe.router)
app.include_router(meetings.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {
        "service": "Cyberecho API",
        "docs": "/docs",
        "endpoints": [
            "GET  /health",
            "GET  /db/health",
            "POST /api/transcribe",
            "POST /api/meetings/process",
            "GET  /api/meetings/jobs",
            "GET  /api/meetings/jobs/{job_id}",
            "POST /api/chat/ask",
        ],
    }


if __name__ == "__main__":
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)

import os

from dotenv import load_dotenv
import psycopg2

load_dotenv()

POSTGRES_CONNECTION_STRING = os.getenv("POSTGRES_CONNECTION_STRING")


# Подключение к PostgreSQL (строка из .env / окружения)
def get_db_connection():
    try:
        conn = psycopg2.connect(POSTGRES_CONNECTION_STRING)
        return conn
    except Exception as e:
        raise RuntimeError(f"Ошибка подключения к базе данных: {e}") from e
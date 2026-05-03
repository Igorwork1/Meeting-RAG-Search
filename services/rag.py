import json
import os

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from psycopg2.extras import RealDictCursor

from services.db import get_db_connection

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
POSTGRES_CONNECTION_STRING = os.getenv("POSTGRES_CONNECTION_STRING")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gpt-4o")
TOP_K = int(os.getenv("TOP_K", "5"))
COMPANY_ID = os.getenv("COMPANY_ID", "")
SOURCE_TYPE = os.getenv("SOURCE_TYPE", "")


# Получение эмбеддинга
def get_embedding(query):
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, openai_api_key=OPENAI_API_KEY)
    return embeddings.embed_query(query)

# Поиск документов
def search_documents(query):
    embedding_str = f"[{','.join(map(str, get_embedding(query)))}]"
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT content, metadata
                FROM public.documents
                WHERE company_id = %s AND source_type = %s AND emb IS NOT NULL
                ORDER BY emb <-> %s::vector
                LIMIT %s
            """, (COMPANY_ID, SOURCE_TYPE, embedding_str, TOP_K))
            results = cur.fetchall()
            return [
                Document(page_content=row["content"], metadata=json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"])
                for row in results
            ]
    finally:
        conn.close()

# Генерация ответа
def generate_response(query, documents, history):
    docs_block = "\n".join([doc.page_content for doc in documents])
    prompt = ChatPromptTemplate.from_template(
        """
            Ты — консультант компании СмартХим. Используй информацию о продуктах ниже для ответа на вопросы клиентов.

            ВАЖНО:
            - Отвечай только на основе предоставленной информации о продуктах
            - Если вопрос не касается продуктов компании, вежливо объясни, что можешь помочь только с информацией о продукции СмартХим
            - Будь дружелюбным и профессиональным
            - Учитывай контекст предыдущих сообщений

            ==== КОНТЕКСТ ПЕРЕПИСКИ ====
            {chat_history}

            ==== ПРОДУКТЫ КОМПАНИИ ====
            {docs_block}

            ==== ТЕКУЩИЙ ВОПРОС ====
            Вопрос: {user_message}

            Ответ (коротко и по делу, на русском):
            """
    )
    llm = ChatOpenAI(model=GENERATION_MODEL, openai_api_key=OPENAI_API_KEY)
    return (prompt | llm).invoke({"user_message": query, "docs_block": docs_block, "chat_history": history}).content

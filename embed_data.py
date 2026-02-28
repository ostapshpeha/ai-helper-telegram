import asyncio
import re
from pathlib import Path

from google import genai
from pymongo import AsyncMongoClient
from beanie import init_beanie

from app.core.config import settings
from app.models.knowledge import KnowledgeChunk

_KB_PATH = Path(__file__).parent / "data" / "info.md"

api_key = settings.GEMINI_API_KEY
if not api_key:
    raise ValueError("GEMINI_API_KEY не знайдено у файлі .env")

ai_client = genai.Client(api_key=api_key)


def chunk_knowledge_base(text: str) -> list[dict]:
    """
    Split info.md into semantic chunks following its section structure:
    - Major sections separated by '---' dividers
    - Sub-sections detected by patterns like '3.1.', '6.2.', '7.3.'
    Each chunk keeps its section title as context.
    """
    chunks = []

    # Split on the horizontal rule dividers
    major_sections = re.split(r"-{10,}", text)

    for section_text in major_sections:
        section_text = section_text.strip()
        if len(section_text) < 50:
            continue

        # Section title = first non-empty line
        first_line = next(
            (l.strip() for l in section_text.split("\n") if l.strip()), ""
        )

        # Split by sub-sections (e.g. "3.1.", "6.2.", "7.3.")
        sub_chunks = re.split(r"\n(?=\d+\.\d+\.)", section_text)

        if len(sub_chunks) > 1:
            for sub in sub_chunks:
                sub = sub.strip()
                if len(sub) < 50:
                    continue
                sub_title = next(
                    (l.strip() for l in sub.split("\n") if l.strip()), first_line
                )
                chunks.append({"content": sub, "section": sub_title})
        else:
            chunks.append({"content": section_text, "section": first_line})

    return chunks


async def embed(text: str) -> list[float]:
    """Embed a single text chunk using Gemini embedding-001."""
    response = await asyncio.to_thread(
        lambda: ai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config={"task_type": "RETRIEVAL_DOCUMENT"},
        )
    )
    return response.embeddings[0].values


async def process_and_save_embeddings():
    print("Підключення до MongoDB...")
    db_client = AsyncMongoClient(settings.MONGO_DB_URL)
    await init_beanie(
        database=db_client[settings.MONGO_DB_NAME],
        document_models=[KnowledgeChunk],
    )

    print("Очищення старих чанків...")
    await KnowledgeChunk.delete_all()

    print(f"Читання {_KB_PATH}...")
    try:
        text = _KB_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Файл {_KB_PATH} не знайдено!")
        return

    chunks = chunk_knowledge_base(text)
    print(f"Розбито на {len(chunks)} чанків. Починаємо векторизацію...")

    for i, chunk in enumerate(chunks, start=1):
        vector = await embed(chunk["content"])
        await KnowledgeChunk(
            content=chunk["content"],
            section=chunk["section"],
            source="info.md",
            embedding=vector,
        ).insert()
        print(f"[{i}/{len(chunks)}] {chunk['section'][:60]}")

    print("Векторизацію завершено. Дані збережено в MongoDB.")


if __name__ == "__main__":
    asyncio.run(process_and_save_embeddings())

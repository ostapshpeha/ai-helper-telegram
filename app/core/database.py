import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie
from app.core.config import settings

logger = logging.getLogger(__name__)
from app.models.knowledge import KnowledgeChunk

_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def init_db():
    global _db
    client = AsyncIOMotorClient(settings.MONGO_DB_URL)
    _db = client[settings.MONGO_DB_NAME]

    await init_beanie(
        database=_db,
        document_models=[KnowledgeChunk],
    )
    logger.info("Connected to MongoDB: %s", settings.MONGO_DB_NAME)

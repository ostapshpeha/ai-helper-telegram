from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie
from app.core.config import settings
from app.models.knowledge import KnowledgeChunk
from app.models.ligtning import ChatLog
from app.models.service import Mechanic, ServiceSlot, Parts

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
        document_models=[Mechanic, ServiceSlot, ChatLog, Parts, KnowledgeChunk],
    )
    print("Successfully connected to MongoDB!")

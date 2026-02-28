from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings
from app.models.knowledge import KnowledgeChunk
from app.models.ligtning import ChatLog
from app.models.service import Mechanic, ServiceSlot, Parts


async def init_db():
    client = AsyncIOMotorClient(settings.MONGO_DB_URL)
    database = client[settings.MONGO_DB_NAME]

    await init_beanie(
        database=database,
        document_models=[Mechanic, ServiceSlot, ChatLog, Parts, KnowledgeChunk],
    )
    print("Successfully connected to MongoDB!")

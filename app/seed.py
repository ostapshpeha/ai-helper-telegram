import asyncio
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from core.config import settings
from models.service import Mechanic, ServiceSlot, SlotStatus, ClientInfo


async def seed_database():
    print("Connecting to database...")
    client = AsyncIOMotorClient(settings.MONGO_DB_URL)
    database = client[settings.MONGO_DB_NAME]

    await init_beanie(database=database, document_models=[Mechanic, ServiceSlot])

    print("Deleting old data...")
    await Mechanic.delete_all()
    await ServiceSlot.delete_all()

    print("Creating mechanics...")
    mechanic_1 = Mechanic(
        name="Олександр (Ходова та ТО)", specialization=["Ходова", "ТО", "Двигун"]
    )
    mechanic_2 = Mechanic(
        name="Андрій (Електрика та Гібриди)",
        specialization=["Електрика", "Гібридні установки", "Діагностика"],
    )

    await mechanic_1.insert()
    await mechanic_2.insert()

    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)

    # Генеруємо час: Завтра на 10:00 та 14:00
    slot_1_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    slot_2_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)

    # 1. Вільний слот до Олександра
    slot_available = ServiceSlot(
        mechanic=mechanic_1,
        start_time=slot_1_time,
        end_time=slot_1_time + timedelta(hours=2),
        status=SlotStatus.AVAILABLE,
    )

    # 2. Зайнятий слот до Андрія (з даними клієнта)
    slot_booked = ServiceSlot(
        mechanic=mechanic_2,
        start_time=slot_2_time,
        end_time=slot_2_time + timedelta(hours=2),
        status=SlotStatus.BOOKED,
        client=ClientInfo(
            name="Ігор",
            phone="+380501234567",
            car_model="Honda CR-V 2024",
            issue_description="Горить помилка гібридної системи",
        ),
    )

    await slot_available.insert()
    await slot_booked.insert()

    print("✅ Data Base seeded!")


if __name__ == "__main__":
    asyncio.run(seed_database())

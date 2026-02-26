import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from core.config import settings
from models.service import Mechanic, ServiceSlot, SlotStatus, ClientInfo, Parts, Car


async def seed_database():
    print("Connecting to database...")
    client = AsyncIOMotorClient(settings.MONGO_DB_URL)
    database = client[settings.MONGO_DB_NAME]

    await init_beanie(database=database, document_models=[Mechanic, ServiceSlot, Parts])

    print("Deleting old data...")
    await Mechanic.delete_all()
    await ServiceSlot.delete_all()
    await Parts.delete_all()

    # ── Mechanics ────────────────────────────────────────────────────────────
    print("Creating mechanics...")
    mechanic_1 = Mechanic(
        name="Олександр Коваль",
        specialization=["Ходова", "ТО", "Двигун", "Трансмісія"],
    )
    mechanic_2 = Mechanic(
        name="Андрій Бондаренко",
        specialization=["Електрика", "Гібридні установки", "Діагностика"],
    )
    mechanic_3 = Mechanic(
        name="Василь Мельник",
        specialization=["Кузов", "Лакофарбові роботи", "Детейлінг"],
        is_active=True,
    )
    mechanic_4 = Mechanic(
        name="Іван Шевченко",
        specialization=["Шиномонтаж", "Балансування", "Гальма", "ТО"],
        is_active=True,
    )

    await mechanic_1.insert()
    await mechanic_2.insert()
    await mechanic_3.insert()
    await mechanic_4.insert()

    # ── Service Slots ─────────────────────────────────────────────────────────
    print("Creating service slots...")
    now = datetime.utcnow()

    def make_slot(
        days_ahead: int, hour: int, mechanic, status=SlotStatus.AVAILABLE, client=None
    ):
        base = (now + timedelta(days=days_ahead)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        return ServiceSlot(
            mechanic=mechanic,
            start_time=base,
            end_time=base + timedelta(hours=2),
            status=status,
            client=client,
        )

    slots = [
        # Tomorrow
        make_slot(1, 9, mechanic_1),
        make_slot(1, 11, mechanic_1),
        make_slot(1, 14, mechanic_2),
        make_slot(1, 16, mechanic_4),
        make_slot(
            1,
            10,
            mechanic_2,
            SlotStatus.BOOKED,
            ClientInfo(
                name="Ігор Петренко",
                phone="+380501234567",
                car_model="Honda CR-V 2024",
                issue_description="Горить помилка гібридної системи",
            ),
        ),
        # Day after tomorrow
        make_slot(2, 9, mechanic_3),
        make_slot(2, 11, mechanic_4),
        make_slot(2, 14, mechanic_1),
        make_slot(2, 16, mechanic_1),
        make_slot(
            2,
            13,
            mechanic_3,
            SlotStatus.BOOKED,
            ClientInfo(
                name="Марія Лисенко",
                phone="+380672345678",
                car_model="Honda Civic 2023",
                issue_description="Подряпини на передньому бампері, потрібне полірування",
            ),
        ),
        # In 3 days
        make_slot(3, 9, mechanic_2),
        make_slot(3, 11, mechanic_2),
        make_slot(3, 14, mechanic_4),
        make_slot(3, 16, mechanic_3),
        make_slot(
            3,
            10,
            mechanic_1,
            SlotStatus.BOOKED,
            ClientInfo(
                name="Дмитро Савченко",
                phone="+380933456789",
                car_model="Acura MDX 2022",
                issue_description="Планове ТО, заміна масла та фільтрів",
            ),
        ),
        # In 4 days
        make_slot(4, 9, mechanic_1),
        make_slot(4, 11, mechanic_3),
        make_slot(4, 14, mechanic_2),
        make_slot(4, 16, mechanic_4),
    ]

    for slot in slots:
        await slot.insert()

    # ── Parts ─────────────────────────────────────────────────────────────────
    print("Creating car parts...")

    civic = [
        Car(name="Honda Civic", year=2021),
        Car(name="Honda Civic", year=2022),
        Car(name="Honda Civic", year=2023),
    ]
    crv = [
        Car(name="Honda CR-V", year=2022),
        Car(name="Honda CR-V", year=2023),
        Car(name="Honda CR-V", year=2024),
    ]
    hrv = [Car(name="Honda HR-V", year=2022), Car(name="Honda HR-V", year=2023)]
    accord = [
        Car(name="Honda Accord", year=2021),
        Car(name="Honda Accord", year=2022),
        Car(name="Honda Accord", year=2023),
    ]
    pilot = [
        Car(name="Honda Pilot", year=2022),
        Car(name="Honda Pilot", year=2023),
        Car(name="Honda Pilot", year=2024),
    ]
    mdx = [
        Car(name="Acura MDX", year=2021),
        Car(name="Acura MDX", year=2022),
        Car(name="Acura MDX", year=2023),
    ]
    rdx = [
        Car(name="Acura RDX", year=2021),
        Car(name="Acura RDX", year=2022),
        Car(name="Acura RDX", year=2023),
    ]
    universal = civic + crv + hrv + accord + pilot

    parts_data = [
        # Filters
        Parts(name="Оливний фільтр Honda", price=Decimal("320"), models=universal),
        Parts(
            name="Повітряний фільтр двигуна",
            price=Decimal("480"),
            models=civic + crv + accord,
        ),
        Parts(name="Фільтр салону (вугільний)", price=Decimal("650"), models=universal),
        Parts(name="Паливний фільтр", price=Decimal("890"), models=civic + accord),
        # Brake system
        Parts(
            name="Гальмівні колодки передні (комплект)",
            price=Decimal("2400"),
            models=civic + crv + hrv,
        ),
        Parts(
            name="Гальмівні колодки задні (комплект)",
            price=Decimal("1950"),
            models=civic + crv + hrv,
        ),
        Parts(
            name="Гальмівний диск передній",
            price=Decimal("3200"),
            models=accord + pilot,
        ),
        Parts(
            name="Гальмівний диск задній", price=Decimal("2800"), models=accord + pilot
        ),
        Parts(
            name="Гальмівна рідина DOT 4 (1л)",
            price=Decimal("420"),
            models=universal + mdx + rdx,
        ),
        # Suspension
        Parts(
            name="Амортизатор передній", price=Decimal("4800"), models=civic + accord
        ),
        Parts(name="Амортизатор задній", price=Decimal("4200"), models=civic + accord),
        Parts(
            name="Стійка стабілізатора передня",
            price=Decimal("680"),
            models=crv + hrv + pilot,
        ),
        Parts(
            name="Сайлентблок переднього важеля",
            price=Decimal("520"),
            models=civic + crv,
        ),
        Parts(name="Кульова опора", price=Decimal("1100"), models=civic + accord + crv),
        # Engine / Fluids
        Parts(
            name="Моторна олива Honda 0W-20 (4л)",
            price=Decimal("1650"),
            models=universal + mdx + rdx,
        ),
        Parts(
            name="Моторна олива Honda 5W-30 (4л)",
            price=Decimal("1550"),
            models=universal,
        ),
        Parts(
            name="Охолоджуюча рідина Honda (1л)",
            price=Decimal("480"),
            models=universal + mdx + rdx,
        ),
        Parts(
            name="Свічка запалювання NGK (1шт)",
            price=Decimal("380"),
            models=civic + accord + hrv,
        ),
        Parts(name="Ремінь ГРМ", price=Decimal("2200"), models=accord + pilot),
        Parts(
            name="Ролик натяжний ременя ГРМ",
            price=Decimal("950"),
            models=accord + pilot,
        ),
        # Battery & Electrical
        Parts(
            name="Акумулятор 12V 60Ah Honda OEM",
            price=Decimal("5800"),
            models=civic + hrv + accord,
        ),
        Parts(
            name="Акумулятор 12V 70Ah Honda OEM",
            price=Decimal("6400"),
            models=crv + pilot + mdx + rdx,
        ),
        Parts(
            name="Щітки склоочисника (комплект)", price=Decimal("760"), models=universal
        ),
        # Hybrid-specific
        Parts(
            name="Гібридна батарея Honda (рекондиційована)",
            price=Decimal("48000"),
            models=[
                Car(name="Honda CR-V Hybrid", year=2023),
                Car(name="Honda CR-V Hybrid", year=2024),
            ],
        ),
        Parts(
            name="Інвертор гібридної системи",
            price=Decimal("32000"),
            models=[
                Car(name="Acura MDX Hybrid", year=2022),
                Car(name="Acura MDX Hybrid", year=2023),
            ],
        ),
        # Acura-specific
        Parts(
            name="Гальмівні колодки передні Acura (комплект)",
            price=Decimal("3800"),
            models=mdx + rdx,
        ),
        Parts(
            name="Амортизатор передній Acura", price=Decimal("7200"), models=mdx + rdx
        ),
        Parts(name="Оливний фільтр Acura", price=Decimal("420"), models=mdx + rdx),
    ]

    for part in parts_data:
        await part.insert()

    print(
        f"✅ Seeded: {len([mechanic_1,mechanic_2,mechanic_3,mechanic_4])} mechanics, {len(slots)} slots, {len(parts_data)} parts."
    )


if __name__ == "__main__":
    asyncio.run(seed_database())

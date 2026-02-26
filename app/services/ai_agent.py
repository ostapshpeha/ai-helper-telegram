import os
from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel

from app.core.config import settings
from app.models.service import Mechanic, ServiceSlot, SlotStatus, Parts

_KB_PATH = Path(__file__).parent.parent.parent / "data" / "info.md"

os.environ.setdefault("GEMINI_API_KEY", settings.GEMINI_API_KEY)

model = GoogleModel("gemini-3-flash-preview")

honda_agent = Agent(
    model=model,
    system_prompt=(
        "Ти — преміальний сервісний консультант дилерського центру Honda та Acura. "
        "Твоя мета — допомагати клієнтам, відповідати на їхні технічні питання та записувати на сервіс.\n\n"
        "Правила:\n"
        "1. Будь ввічливим, емпатичним та професійним.\n"
        "2. Якщо клієнт питає про характеристики, комплектації або ціни авто в нашому салоні — "
        "ОБОВ'ЯЗКОВО використовуй інструмент read_knowledge_base.\n"
        "3. Ніколи не вигадуй ціни на сервісні роботи. Кажи: "
        "'Точну вартість майстер зможе назвати після огляду автомобіля'. "
        "Ціни на запчастини — тільки з бази даних через інструмент read_parts_price.\n"
        "4. Якщо клієнт хоче записатися на сервіс або питає про вільний час — "
        "використовуй інструмент read_db_slots.\n"
        "5. Ніколи не рекомендуй клієнту самостійно ремонтувати авто.\n"
        "6. Відповідай виключно українською мовою."
    ),
)


@lru_cache(maxsize=1)
def _load_knowledge_base() -> str:
    return _KB_PATH.read_text(encoding="utf-8")


@honda_agent.tool
def read_knowledge_base(ctx: RunContext[None], search_query: str) -> str:
    """
    Використовуй цей інструмент, щоб отримати інформацію про автомобілі Honda та Acura:
    комплектації, ціни, послуги салону, детейлінг.
    """
    print(f"[tool] read_knowledge_base: '{search_query}'")
    try:
        content = _load_knowledge_base()
        return (
            f"Ось вміст бази знань. Знайди тут відповідь на запит клієнта:\n\n{content}"
        )
    except FileNotFoundError:
        return "Системна помилка: файл бази знань не знайдено. Скажи клієнту, що інформація тимчасово недоступна."


@honda_agent.tool
async def read_db_slots(ctx: RunContext[None], search_query: str) -> str:
    """
    Використовуй цей інструмент, коли клієнт хоче записатися на сервіс
    або питає про вільні дати та час прийому.
    """
    print(f"[tool] read_db_slots: '{search_query}'")
    try:
        slots = await ServiceSlot.find(
            ServiceSlot.status == SlotStatus.AVAILABLE
        ).to_list()

        if not slots:
            return "Наразі немає вільних слотів для запису. Запропонуй клієнту залишити номер, щоб ми йому передзвонили."

        # Batch mechanic lookup — one query instead of N
        mechanic_ids = [
            s.mechanic.ref.id if hasattr(s.mechanic, "ref") else s.mechanic
            for s in slots
        ]
        mechanics = await Mechanic.find({"_id": {"$in": mechanic_ids}}).to_list()
        mech_map = {m.id: m.name for m in mechanics}

        lines = ["Ось список доступних вільних слотів:"]
        for s in slots:
            mid = s.mechanic.ref.id if hasattr(s.mechanic, "ref") else s.mechanic
            name = mech_map.get(mid, "Черговий майстер")
            start = s.start_time.strftime("%d.%m.%Y о %H:%M")
            lines.append(f"- {start} | Майстер: {name}")

        lines.append("\nЗапропонуй клієнту один із цих варіантів.")
        return "\n".join(lines)

    except Exception as e:
        print(f"[tool] read_db_slots error: {e}")
        return "Виникла технічна помилка доступу до бази даних. Скажи клієнту, що система запису тимчасово недоступна."


@honda_agent.tool
async def read_parts_price(ctx: RunContext[None], search_query: str) -> str:
    """
    Використовуй цей інструмент, коли клієнт питає про ціну на конкретну запчастину.
    search_query — назва деталі, яку шукає клієнт.
    """
    print(f"[tool] read_parts_price: '{search_query}'")
    try:
        parts = await Parts.find(
            {"name": {"$regex": search_query, "$options": "i"}}
        ).to_list()

        if not parts:
            return (
                f"Запчастину '{search_query}' не знайдено в базі даних. "
                "Скажи клієнту, що уточниш наявність і передзвониш."
            )

        lines = [f"Знайдено запчастини за запитом '{search_query}':"]
        for part in parts:
            compatible = ", ".join(f"{c.name} {c.year}" for c in part.models)
            lines.append(
                f"- {part.name}: {part.price} грн | Підходить для: {compatible}"
            )
        lines.append("\nЦіни актуальні на момент останнього оновлення бази.")
        return "\n".join(lines)

    except Exception as e:
        print(f"[tool] read_parts_price error: {e}")
        return "Виникла технічна помилка. Скажи клієнту, що ціни тимчасово недоступні."

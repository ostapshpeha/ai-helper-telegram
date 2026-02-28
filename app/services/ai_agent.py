import asyncio
import os

from google import genai
from google.genai import types
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel

from app.core.config import settings
from app.core.database import get_db
from app.models.service import Mechanic, ServiceSlot, SlotStatus, Parts

os.environ.setdefault("GEMINI_API_KEY", settings.GEMINI_API_KEY)

ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

_VECTOR_INDEX = "vector_index"
_TOP_K = 5

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
        "4. Якщо клієнт хоче записатися на сервіс — "
        "використовуй інструмент read_db_slots."
        "Якщо клієнт хоче записатись на тест драйв - дай йому номер відповідального\n"
        "5. Ніколи не рекомендуй клієнту самостійно ремонтувати авто.\n"
        "6. Відповідай виключно українською мовою."
    ),
)


async def _embed_query(text: str) -> list[float]:
    response = await asyncio.to_thread(
        lambda: ai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
    )
    return response.embeddings[0].values


@honda_agent.tool
async def read_knowledge_base(ctx: RunContext[None], search_query: str) -> str:
    """
    Використовуй цей інструмент, щоб отримати інформацію про автомобілі Honda та Acura:
    комплектації, ціни, послуги салону, детейлінг.
    """
    print(f"[tool] read_knowledge_base: '{search_query}'")
    try:
        query_vector = await _embed_query(search_query)

        pipeline = [
            {
                "$vectorSearch": {
                    "index": _VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": 50,
                    "limit": _TOP_K,
                }
            },
            {
                "$project": {
                    "content": 1,
                    "section": 1,
                    "score": {"$meta": "vectorSearchScore"},
                    "_id": 0,
                }
            },
        ]

        results = (
            await get_db()["knowledge_chunks"]
            .aggregate(pipeline)
            .to_list(length=_TOP_K)
        )

        if not results:
            return (
                "Інформацію не знайдено в базі знань. Скажи клієнту, що уточниш деталі."
            )

        lines = [f"Знайдено {len(results)} релевантних фрагментів:\n"]
        for r in results:
            lines.append(f"[{r['section']}]\n{r['content']}")
            lines.append("---")

        return "\n".join(lines)

    except Exception as e:
        print(f"[tool] read_knowledge_base error: {e}")
        return "Системна помилка доступу до бази знань. Скажи клієнту, що інформація тимчасово недоступна."


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

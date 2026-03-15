import asyncio
import html
import logging
import os
import re
from dataclasses import dataclass

from aiogram import Bot
from google import genai
from google.genai import types
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel

from app.core.config import settings
from app.core.database import get_db
from app.models.service import Mechanic, ServiceSlot, SlotStatus, Parts

logger = logging.getLogger(__name__)


@dataclass
class AgentDeps:
    bot: Bot
    user_id: int


os.environ.setdefault("GEMINI_API_KEY", settings.GEMINI_API_KEY)

ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

_VECTOR_INDEX = "vector_index"
_TOP_K = 7
_NUM_CANDIDATES = 100

model = GoogleModel("gemini-3-flash-preview")

INITIAL_SYSTEM_PROMPT = (
    "Ти — преміальний сервісний консультант дилерського центру Honda та Acura. "
    "Твоя мета — допомагати клієнтам, відповідати на їхні технічні питання та записувати на сервіс."
    "Твій пріорітет це давати номер телефону відповідного відділу (read_knowledge_base)."
    "Ніколи не видумуй номер\n\n"
    "ВАЖЛИВО: Твої повідомлення будуть відображатися в Telegram. "
    "Для форматування тексту використовуй ТІЛЬКИ HTML-теги: <b>для жирного тексту</b>, <i>для курсиву</i>. "
    "ЗАБОРОНЕНО використовувати зірочки (** або *) для форматування.\n\n"
    "Правила:\n"
    "1. Будь ввічливим, емпатичним та професійним.\n"
    "2. Якщо клієнт питає про характеристики, комплектації або ціни авто в нашому салоні — "
    "ОБОВ'ЯЗКОВО використовуй інструмент read_knowledge_base.\n"
    "3. Ніколи не вигадуй ціни на сервісні роботи. Кажи: "
    "'Точну вартість майстер зможе назвати після огляду автомобіля'."
    "Ціни на запчастини — тільки з бази даних через інструмент read_parts_price.\n"
    "4. Якщо клієнт хоче записатися на сервіс — "
    "використовуй інструмент read_db_slots\n"
    "5. Ніколи не рекомендуй клієнту самостійно ремонтувати авто.\n"
    "6. Якщо клієнт надає номер телефону або просить передзвонити — "
    "ОБОВ'ЯЗКОВО використовуй інструмент request_callback, щоб передати контакт персоналу.\n"
    "7. Відповідай виключно українською мовою."
)

honda_agent = Agent(
    model=model,
    deps_type=AgentDeps,
    system_prompt=INITIAL_SYSTEM_PROMPT,
)


async def _embed_query(text: str) -> list[float]:
    response = await asyncio.to_thread(
        lambda: ai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            ),
        )
    )
    return response.embeddings[0].values


async def _expand_query(query: str) -> list[str]:
    """Generate 2 additional reformulations of the query for multi-query retrieval."""
    prompt = (
        f"Перефразуй це пошукове запитання 2 різними способами, щоб знайти більше релевантної інформації. "
        f"Використовуй різні ключові слова та синоніми. "
        f"Поверни лише 2 рядки — по одному перефразуванню на рядок, без нумерації.\n\n"
        f"Запитання: {query}"
    )
    try:
        response = await asyncio.to_thread(
            lambda: ai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=100, temperature=0.3),
            )
        )
        variants = [line.strip() for line in response.text.strip().splitlines() if line.strip()]
        return variants[:2]
    except Exception:
        return []


async def _vector_search(query_vector: list[float]) -> list[dict]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": _VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": _NUM_CANDIDATES,
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
    return await get_db()["knowledge_chunks"].aggregate(pipeline).to_list(length=_TOP_K)


@honda_agent.tool
async def read_knowledge_base(ctx: RunContext[None], search_query: str) -> str:
    """
    Використовуй цей інструмент для пошуку інформації про Honda та Acura:
    комплектації, технічні характеристики, ціни на авто, послуги салону, детейлінг, контакти відділів.

    search_query — детальний пошуковий запит українською з ключовими словами.
    Приклад хорошого запиту: "Honda HR-V комплектації характеристики ціна"
    Приклад поганого запиту: "hr-v"
    """
    logger.info("read_knowledge_base: %s", search_query)
    try:
        # Expand query into variants + embed all in parallel
        variants = await _expand_query(search_query)
        all_queries = [search_query] + variants
        logger.info("read_knowledge_base expanded queries: %s", all_queries)

        vectors = await asyncio.gather(*[_embed_query(q) for q in all_queries])
        result_sets = await asyncio.gather(*[_vector_search(v) for v in vectors])

        # Deduplicate by content, keep highest score per unique chunk
        seen: dict[str, dict] = {}
        for result_list in result_sets:
            for r in result_list:
                key = r["content"]
                if key not in seen or r["score"] > seen[key]["score"]:
                    seen[key] = r

        results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:_TOP_K]

        if not results:
            return "Інформацію не знайдено в базі знань. Скажи клієнту, що уточниш деталі."

        lines = [f"Знайдено {len(results)} релевантних фрагментів:\n"]
        for r in results:
            lines.append(f"[{r['section']}]\n{r['content']}")
            lines.append("---")

        return "\n".join(lines)

    except Exception:
        logger.exception("read_knowledge_base failed")
        return "Системна помилка доступу до бази знань. Скажи клієнту, що інформація тимчасово недоступна."


@honda_agent.tool
async def read_db_slots(ctx: RunContext[None], specialization: str = "") -> str:
    """
    Використовуй цей інструмент, коли клієнт хоче записатися на сервіс
    або питає про вільні дати та час прийому.

    specialization — тип майстра, якого шукає клієнт (наприклад: "двигун", "детейлінг",
    "трансмісія", "електрика"). Якщо клієнт не уточнив — залиш порожнім, повернуться всі слоти.
    """
    logger.info("read_db_slots: specialization=%r", specialization)
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

        # Filter by specialization if provided
        if specialization.strip():
            keyword = specialization.strip().lower()
            mechanics = [
                m for m in mechanics
                if any(keyword in spec.lower() for spec in m.specialization)
            ]
            if not mechanics:
                return (
                    f"Немає вільних майстрів зі спеціалізацією «{specialization}». "
                    "Запропонуй клієнту залишити номер — ми передзвонимо, як тільки з'явиться вільний час."
                )

        mech_ids_filtered = {m.id for m in mechanics}
        mech_map = {m.id: (m.name, m.specialization) for m in mechanics}

        lines = [
            f"Вільні слоти{f' (майстри зі спеціалізацією «{specialization}»)' if specialization.strip() else ''}:"
        ]
        found = False
        for s in slots:
            mid = s.mechanic.ref.id if hasattr(s.mechanic, "ref") else s.mechanic
            if mid not in mech_ids_filtered:
                continue
            found = True
            name, specs = mech_map[mid]
            start = s.start_time.strftime("%d.%m.%Y о %H:%M")
            lines.append(f"- {start} | Майстер: {name} ({', '.join(specs)})")

        if not found:
            return (
                f"Немає вільних слотів для майстрів зі спеціалізацією «{specialization}». "
                "Запропонуй клієнту залишити номер — ми передзвонимо."
            )

        lines.append("\nЗапропонуй клієнту один із цих варіантів.")
        return "\n".join(lines)

    except Exception:
        logger.exception("read_db_slots failed")
        return "Виникла технічна помилка доступу до бази даних. Скажи клієнту, що система запису тимчасово недоступна."


@honda_agent.tool
async def read_parts_price(ctx: RunContext[None], search_query: str) -> str:
    """
    Використовуй цей інструмент, коли клієнт питає про ціну на конкретну запчастину.
    search_query — назва деталі, яку шукає клієнт.
    """
    logger.info("read_parts_price: %s", search_query)
    try:
        safe_query = re.escape(search_query)
        parts = await Parts.find(
            {"name": {"$regex": safe_query, "$options": "i"}}
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

    except Exception:
        logger.exception("read_parts_price failed")
        return "Виникла технічна помилка. Скажи клієнту, що ціни тимчасово недоступні."


@honda_agent.tool
async def request_callback(
    ctx: RunContext[AgentDeps],
    phone: str,
    name: str = "",
    car_model: str = "",
    issue: str = "",
) -> str:
    """
    Використовуй цей інструмент, коли клієнт надає номер телефону або просить передзвонити.
    Передає контактні дані клієнта персоналу через Telegram.
    phone — номер телефону клієнта (обов'язково).
    name — ім'я клієнта (якщо відоме з діалогу).
    car_model — модель автомобіля (якщо відома з діалогу).
    issue — причина звернення (якщо відома з діалогу).
    """
    logger.info("request_callback: phone=%s user_id=%s", phone, ctx.deps.user_id)
    try:
        lines = ["📞 <b>Новий запит на передзвін</b>\n"]
        if name:
            lines.append(f"👤 Ім'я: {html.escape(name)}")
        lines.append(f"📱 Телефон: {html.escape(phone)}")
        if car_model:
            lines.append(f"🚗 Модель: {html.escape(car_model)}")
        if issue:
            lines.append(f"🔧 Питання: {html.escape(issue)}")
        lines.append(f"\n🤖 Telegram ID клієнта: {ctx.deps.user_id}")

        await ctx.deps.bot.send_message(
            chat_id=settings.STAFF_CHAT_ID,
            text="\n".join(lines),
        )
        return "Контактні дані передано персоналу. Наш менеджер зв'яжеться з клієнтом найближчим часом."

    except Exception:
        logger.exception("request_callback failed")
        return "Виникла помилка при передачі контакту. Запропонуй клієнту зателефонувати напряму."


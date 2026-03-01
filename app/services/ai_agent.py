import asyncio
import html
import logging
import os
from dataclasses import dataclass

from aiogram import Bot
from google import genai
from google.genai import types
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel

from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)


@dataclass
class AgentDeps:
    bot: Bot
    user_id: int


os.environ.setdefault("GEMINI_API_KEY", settings.GEMINI_API_KEY)

ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

_VECTOR_INDEX = "vector_index"
_TOP_K = 5

model = GoogleModel("gemini-3-flash-preview")

honda_agent = Agent(
    model=model,
    deps_type=AgentDeps,
    system_prompt=(
        "Ти — преміальний сервісний консультант дилерського центру Honda та Acura. "
        "Твоя мета — допомагати клієнтам, відповідати на їхні технічні питання та записувати на сервіс."
        "Твій пріорітет це давати номер телефону відповідного відділу (read_knowledge_base)."
        "Ніколи не видумуй номер\n\n"
        "ВАЖЛИВО: Твої повідомлення будуть відображатися в Telegram. "
        "Для форматування тексту використовуй ТІЛЬКИ HTML-теги: <b>для жирного тексту</b>, <i>для курсиву</i>. "
        "ЗАБОРОНЕНО використовувати зірочки (** або *) для форматування.\n\n"
        "Правила:\n"
        "1. Будь ввічливим, емпатичним та професійним.\n"
        "2. Якщо клієнт питає про характеристики, комплектації або послуги салону — "
        "ОБОВ'ЯЗКОВО використовуй інструмент read_knowledge_base.\n"
        "3. Ніколи не вигадуй ціни на сервісні роботи. Кажи: "
        "'Точну вартість майстер зможе назвати після огляду автомобіля'.\n"
        "4. Ніколи не рекомендуй клієнту самостійно ремонтувати авто.\n"
        "5. Якщо клієнт надає номер телефону або просить передзвонити — "
        "ОБОВ'ЯЗКОВО використовуй інструмент request_callback, щоб передати контакт персоналу.\n"
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
    logger.info("read_knowledge_base: %s", search_query)
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

    except Exception:
        logger.exception("read_knowledge_base failed")
        return "Системна помилка доступу до бази знань. Скажи клієнту, що інформація тимчасово недоступна."


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

"""
Weekly negative-feedback report.
Pulls last 7 days of thumbs-down logs, asks Gemini to summarise what went wrong,
and sends the report to the admin via Telegram.

Run manually or via cron / docker-compose run --rm reporter
"""
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.database import init_db
from app.models.ligtning import ChatLog, FeedbackScore

_REPORT_PROMPT = """\
Ти — аналітик якості чат-бота. Нижче наведено діалоги, де користувачі поставили \
негативну оцінку відповіді бота Honda/Acura.

Проаналізуй ці діалоги та дай коротку відповідь у форматі:

1. <b>Основні патерни помилок</b> — що бот робив неправильно?
2. <b>Рекомендації</b> — що конкретно змінити у системному промпті або базі знань?

Діалоги:
{dialogues}
"""


async def main() -> None:
    await init_db()

    since = datetime.utcnow() - timedelta(days=7)
    logs = await ChatLog.find(
        ChatLog.feedback == FeedbackScore.NEGATIVE,
        ChatLog.created_at >= since,
    ).to_list()

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    if not logs:
        await bot.send_message(
            settings.STAFF_CHAT_ID,
            "📊 <b>Щотижневий звіт</b>\n\nЗа останні 7 днів негативних відгуків не було. Все добре!",
        )
        await bot.session.close()
        return

    dialogues = "\n\n".join(
        f"---\nКористувач: {log.user_message}\nБот: {log.agent_response}"
        for log in logs
    )

    ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = await asyncio.to_thread(
        lambda: ai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=_REPORT_PROMPT.format(dialogues=dialogues),
            config=types.GenerateContentConfig(max_output_tokens=1024),
        )
    )
    analysis = response.text

    report = (
        f"📊 <b>Щотижневий звіт якості бота</b>\n"
        f"Негативних відгуків за 7 днів: <b>{len(logs)}</b>\n\n"
        f"{analysis}"
    )

    # Telegram max message length is 4096 chars
    if len(report) > 4096:
        report = report[:4090] + "\n…"

    await bot.send_message(settings.STAFF_CHAT_ID, report)
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

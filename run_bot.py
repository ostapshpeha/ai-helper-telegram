import asyncio
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.services.ai_agent import honda_agent
from app.services.chat_history import save_chat_turn

logger = logging.getLogger(__name__)

bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

user_sessions: dict[int, list] = {}


@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    user_sessions[message.from_user.id] = []
    await message.answer(
        f"Вітаю, {message.from_user.full_name}! 👋\n\n"
        "Я — ШІ-консультант дилерського центру Honda. "
        "Можу розповісти про комплектації, підказати вартість запчастин "
        "або допомогти із записом на сервіс. Чим можу допомогти?"
    )


@dp.message(F.text)
async def handle_user_message(message: types.Message) -> None:
    user_id = message.from_user.id
    user_text = message.text
    if not user_text:
        return

    await bot.send_chat_action(chat_id=user_id, action="typing")
    history = user_sessions.get(user_id, [])

    try:
        result = await honda_agent.run(user_text, message_history=history)
        await message.answer(result.output)
        user_sessions[user_id] = result.all_messages()

        await save_chat_turn(
            user_id=user_id,
            user_message=user_text,
            agent_response=result.output,
            tools_called=[],
        )

    except Exception:
        logger.exception("Agent error for user %s", user_id)
        await message.answer("Перепрошую, виникла технічна заминка. Спробуйте запитати ще раз.")


async def main() -> None:
    setup_logging()
    await init_db()
    logger.info("Telegram bot started, polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

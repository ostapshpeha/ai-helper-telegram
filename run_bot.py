import asyncio
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.services.ai_agent import honda_agent, AgentDeps
from app.services.chat_history import save_chat_turn
from app.services.moderation import (
    is_banned,
    is_rate_limited,
    contains_violation,
    handle_violation,
    ban_user,
    unban_user,
)

logger = logging.getLogger(__name__)

bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

user_sessions: dict[int, list] = {}

_MAX_MESSAGE_LEN = 1000  # chars — protects against oversized LLM requests
_MAX_HISTORY_TURNS = 20  # message pairs kept per user — prevents unbounded memory growth


@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    if is_banned(message.from_user.id):
        await message.answer("🚫 Ваш акаунт заблоковано.")
        return
    user_sessions[message.from_user.id] = []
    await message.answer(
        f"Вітаю, {message.from_user.full_name}! 👋\n\n"
        "Я — ШІ-консультант дилерського центру Honda. "
        "Можу розповісти про комплектації, підказати вартість запчастин "
        "або допомогти із записом на сервіс. Чим можу допомогти?"
    )


# ---------------------------------------------------------------------------
# Admin commands — only work for user IDs listed in ADMIN_IDS in .env
# ---------------------------------------------------------------------------

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message) -> None:
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Використання: /ban &lt;user_id&gt; [причина]")
        return
    target_id = int(parts[1])
    ban_user(target_id)
    logger.info("Admin %s manually banned user %s", message.from_user.id, target_id)
    await message.answer(f"✅ Користувача <b>{target_id}</b> заблоковано.")


@dp.message(Command("unban"))
async def cmd_unban(message: types.Message) -> None:
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Використання: /unban &lt;user_id&gt;")
        return
    target_id = int(parts[1])
    ok = unban_user(target_id)
    logger.info("Admin %s unbanned user %s (was_banned=%s)", message.from_user.id, target_id, ok)
    await message.answer(
        f"✅ Користувача <b>{target_id}</b> розблоковано." if ok
        else f"ℹ️ Користувача <b>{target_id}</b> не знайдено в списку заблокованих."
    )


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------

@dp.message(F.text)
async def handle_user_message(message: types.Message) -> None:
    user_id = message.from_user.id
    user_text = message.text
    if not user_text:
        return

    # 1. Ban check
    if is_banned(user_id):
        await message.answer("🚫 Ваш акаунт заблоковано.")
        return

    # 2. Rate limit check
    if is_rate_limited(user_id):
        await message.answer("⏳ Занадто багато повідомлень. Зачекайте хвилину і спробуйте знову.")
        return

    # 3. Message length check
    if len(user_text) > _MAX_MESSAGE_LEN:
        await message.answer("Повідомлення занадто довге. Будь ласка, скоротіть запит.")
        return

    # 4. Content violation check
    if contains_violation(user_text):
        was_banned, reply = handle_violation(user_id)
        await message.answer(reply)
        if was_banned:
            logger.warning("Auto-banned user %s for content violation", user_id)
        return

    await bot.send_chat_action(chat_id=user_id, action="typing")
    history = user_sessions.get(user_id, [])
    if len(history) > _MAX_HISTORY_TURNS * 2:
        history = history[-(_MAX_HISTORY_TURNS * 2):]
        user_sessions[user_id] = history

    try:
        result = await honda_agent.run(
            user_text,
            deps=AgentDeps(bot=bot, user_id=user_id),
            message_history=history,
        )
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

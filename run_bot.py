import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from beanie import PydanticObjectId

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.models.ligtning import ChatLog, FeedbackScore
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


class FeedbackCallback(CallbackData, prefix="fb"):
    log_id: str
    score: int  # 1 = positive, -1 = negative


bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

user_sessions: dict[int, list] = {}

_MAX_MESSAGE_LEN = 1000  # chars — protects against oversized LLM requests
_MAX_HISTORY_TURNS = 20  # message pairs kept per user — prevents unbounded memory growth


def _build_menu_keyboard() -> InlineKeyboardMarkup:
    url = settings.MINI_APP_URL.rstrip("/")
    if url:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗓 Записатись на сервіс",
                                  web_app=WebAppInfo(url=f"{url}/slots.html"))],
            [InlineKeyboardButton(text="🔧 Ціни на запчастини",
                                  web_app=WebAppInfo(url=f"{url}/parts.html"))],
            [InlineKeyboardButton(text="🚗 Моделі та комплектації",
                                  web_app=WebAppInfo(url=f"{url}/models.html"))],
            [InlineKeyboardButton(text="📞 Залишити номер для передзвону",
                                  web_app=WebAppInfo(url=f"{url}/callback.html"))],
        ])
    # Fallback — plain callback buttons when Mini App URL is not set
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓 Записатись на сервіс", callback_data="menu_slots")],
        [InlineKeyboardButton(text="🔧 Ціни на запчастини", callback_data="menu_parts")],
        [InlineKeyboardButton(text="🚗 Моделі та комплектації", callback_data="menu_models")],
        [InlineKeyboardButton(text="📞 Залишити номер для передзвону", callback_data="menu_callback")],
    ])

_HELP_TEXT = (
    "Ось що я вмію:\n\n"
    "🚗 <b>Авто</b> — комплектації, ціни, порівняння моделей Honda та Acura\n"
    "🔧 <b>Запчастини</b> — вартість деталей за назвою\n"
    "🗓 <b>Запис на сервіс</b> — вільні слоти до майстра\n"
    "📞 <b>Передзвін</b> — залиш номер, ми зателефонуємо\n\n"
    "Команди:\n"
    "/menu — головне меню\n"
    "/reset — почати розмову заново\n"
    "/help — ця підказка"
)


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
        "або допомогти із записом на сервіс.\n\n"
        "Оберіть дію або просто напишіть своє питання:",
        reply_markup=_build_menu_keyboard(),
    )


@dp.message(Command("help"))
async def command_help_handler(message: types.Message) -> None:
    await message.answer(_HELP_TEXT)


@dp.message(Command("menu"))
async def command_menu_handler(message: types.Message) -> None:
    await message.answer("Оберіть дію:", reply_markup=_build_menu_keyboard())


@dp.message(Command("reset"))
async def command_reset_handler(message: types.Message) -> None:
    user_sessions[message.from_user.id] = []
    await message.answer("Розмову скинуто. Починаємо з чистого аркуша!")


@dp.callback_query(F.data.startswith("menu_"))
async def handle_menu_action(callback: types.CallbackQuery) -> None:
    actions = {
        "menu_slots": "Які вільні слоти є для запису на сервіс?",
        "menu_parts": "Мене цікавлять ціни на запчастини.",
        "menu_models": "Розкажи про моделі та комплектації Honda та Acura.",
        "menu_callback": "Хочу залишити номер телефону для передзвону.",
    }
    text = actions.get(callback.data)
    await callback.answer()
    if text:
        await callback.message.answer(f"<i>{text}</i>")
        await _run_agent(
            user_id=callback.from_user.id,
            user_text=text,
            reply_target=callback.message,
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


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    since = datetime.utcnow() - timedelta(days=7)
    total = await ChatLog.find(ChatLog.created_at >= since).count()
    positive = await ChatLog.find(
        ChatLog.feedback == FeedbackScore.POSITIVE,
        ChatLog.created_at >= since,
    ).count()
    negative = await ChatLog.find(
        ChatLog.feedback == FeedbackScore.NEGATIVE,
        ChatLog.created_at >= since,
    ).count()
    recent_neg = await ChatLog.find(
        ChatLog.feedback == FeedbackScore.NEGATIVE,
        ChatLog.created_at >= since,
    ).sort(-ChatLog.created_at).limit(3).to_list()

    lines = [
        "📊 <b>Статистика за 7 днів</b>\n",
        f"Всього діалогів: <b>{total}</b>",
        f"👍 Позитивних: <b>{positive}</b>",
        f"👎 Негативних: <b>{negative}</b>",
    ]
    if recent_neg:
        lines.append("\n<b>Останні негативні відгуки:</b>")
        for log in recent_neg:
            lines.append(f"• {log.user_message[:80]}…")
    await message.answer("\n".join(lines))


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

    await _run_agent(user_id=user_id, user_text=user_text, reply_target=message)


async def _run_agent(user_id: int, user_text: str, reply_target: types.Message) -> None:
    await bot.send_chat_action(chat_id=user_id, action="typing")
    history = user_sessions.get(user_id, [])
    if len(history) > _MAX_HISTORY_TURNS * 2:
        history = history[-(_MAX_HISTORY_TURNS * 2):]
        user_sessions[user_id] = history

    async def _keep_typing(stop: asyncio.Event) -> None:
        while not stop.is_set():
            await asyncio.sleep(4)
            if not stop.is_set():
                await bot.send_chat_action(chat_id=user_id, action="typing")

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(stop_typing))

    try:
        result = await honda_agent.run(
            user_text,
            deps=AgentDeps(bot=bot, user_id=user_id),
            message_history=history,
        )

        chat_log = await save_chat_turn(
            user_id=user_id,
            user_message=user_text,
            agent_response=result.output,
            tools_called=[],
        )

        keyboard = None
        if chat_log:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="👍",
                    callback_data=FeedbackCallback(log_id=str(chat_log.id), score=1).pack()
                ),
                InlineKeyboardButton(
                    text="👎",
                    callback_data=FeedbackCallback(log_id=str(chat_log.id), score=-1).pack()
                ),
            ]])

        stop_typing.set()
        typing_task.cancel()
        await reply_target.answer(result.output, reply_markup=keyboard)
        user_sessions[user_id] = result.all_messages()

    except Exception:
        stop_typing.set()
        typing_task.cancel()
        logger.exception("Agent error for user %s", user_id)
        await reply_target.answer("Перепрошую, виникла технічна заминка. Спробуйте запитати ще раз.")



@dp.callback_query(FeedbackCallback.filter())
async def handle_feedback(callback: types.CallbackQuery, callback_data: FeedbackCallback) -> None:
    try:
        log = await ChatLog.get(PydanticObjectId(callback_data.log_id))
        if log:
            log.feedback = FeedbackScore(callback_data.score)
            await log.save()
    except Exception:
        logger.exception("Failed to save feedback for log %s", callback_data.log_id)
    await callback.answer("Дякуємо за відгук!")
    await callback.message.edit_reply_markup(reply_markup=None)


async def main() -> None:
    setup_logging()
    await init_db()

    await bot.set_my_commands([
        types.BotCommand(command="start", description="Почати розмову"),
        types.BotCommand(command="menu", description="Головне меню"),
        types.BotCommand(command="help", description="Що вміє бот"),
        types.BotCommand(command="reset", description="Почати розмову заново"),
    ])

    admin_commands = [
        types.BotCommand(command="stats", description="Статистика за 7 днів"),
        types.BotCommand(command="ban", description="Заблокувати користувача"),
        types.BotCommand(command="unban", description="Розблокувати користувача"),
    ]
    for admin_id in settings.ADMIN_IDS:
        await bot.set_my_commands(
            admin_commands,
            scope=types.BotCommandScopeChat(chat_id=admin_id),
        )

    logger.info("Telegram bot started, polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

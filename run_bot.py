import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram import F

from app.core.database import init_db
from app.services.ai_agent import honda_agent
from app.core.config import settings

bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# Словник для зберігання історії діалогів (тимчасове рішення в пам'яті, потім перенесемо в Mongo)
user_sessions = {}


@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    """Обробка команди /start"""
    welcome_text = (
        f"Вітаю, {message.from_user.full_name}! 👋\n\n"
        f"Я — ШІ-консультант дилерського центру Honda. "
        f"Можу розповісти про комплектації, підказати вартість запчастин або допомогти із записом на сервіс. Чим можу допомогти?"
    )
    await message.answer(welcome_text)
    user_sessions[message.from_user.id] = []


@dp.message(F.text)
async def handle_user_message(message: types.Message):
    """Обробка всіх текстових повідомлень від клієнтів"""
    user_id = message.from_user.id
    user_text = message.text
    if not user_text:
        return

    await bot.send_chat_action(chat_id=user_id, action="typing")

    # Беремо історію діалогу користувача
    history = user_sessions.get(user_id, [])

    try:
        # Запускаємо нашого агента PydanticAI
        result = await honda_agent.run(user_text, message_history=history)

        # Відправляємо відповідь від Gemini
        await message.answer(result.output)

        # Оновлюємо історію
        user_sessions[user_id] = result.all_messages()

    except Exception as e:
        print(f"Помилка ШІ: {e}")
        await message.answer(
            "Перепрошую, виникла технічна заминка. Спробуйте запитати ще раз."
        )


async def main():
    await init_db()
    print("Telegram бот запущений! Очікую повідомлень...")
    # Запускаємо процес поллінгу
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

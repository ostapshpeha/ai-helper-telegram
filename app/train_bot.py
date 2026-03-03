import asyncio

from openai import AsyncOpenAI
from agentlightning import Trainer
from agentlightning.store.mongo import MongoLightningStore
from agentlightning.algorithm import APO
from agentlightning.types import PromptTemplate, NamedResources

from app.services.ai_agent import training_agent_wrapper, INITIAL_SYSTEM_PROMPT
from app.models.ligtning import ChatLog, FeedbackScore
from app.core.config import settings
from app.core.database import init_db


async def main():
    await init_db()  # Fix bug 3 — Beanie must be initialised before any DB queries

    # Load training tasks from negative feedback logs; fall back to hardcoded examples
    negative_logs = await ChatLog.find(
        ChatLog.feedback == FeedbackScore.NEGATIVE
    ).to_list()
    training_tasks = [log.user_message for log in negative_logs] or [
        "Скільки коштує базова Honda HR-V?",
        "Чи треба записуватись на ТО кожні 10 тисяч?",
        "Запропонуй економне авто для міста.",
    ]

    print(f"🚀 Ініціалізація MongoDB Store ({len(training_tasks)} задач)...")
    store = MongoLightningStore(
        mongo_uri=settings.MONGO_DB_URL,
        database_name=settings.MONGO_DB_NAME,
    )

    print("🧠 Налаштування алгоритму APO...")
    openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)  # Fix bug 1 — APO requires AsyncOpenAI as first arg
    algorithm = APO(
        openai_client,
        gradient_model="gpt-4o-mini",
        apply_edit_model="gpt-4o-mini",
    )

    # Fix bug 2 — wrap initial prompt in NamedResources so the framework can deliver it
    initial_resources = NamedResources({
        "prompt_template": PromptTemplate(content=INITIAL_SYSTEM_PROMPT)
    })

    print("⚙️ Запуск Тренера...")
    trainer = Trainer(
        algorithm=algorithm,
        store=store,
        n_runners=2,
        initial_resources=initial_resources,
    )

    await trainer.fit(agent=training_agent_wrapper, train_dataset=training_tasks)
    print("✅ Тренування завершено! Шукай найкращий промпт у логах.")


if __name__ == "__main__":
    asyncio.run(main())

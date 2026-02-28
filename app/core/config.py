from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Honda AI Assistant"
    MONGO_DB_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "honda_db"

    GEMINI_API_KEY: str = ""

    TELEGRAM_BOT_TOKEN: str = ""
    STAFF_CHAT_ID: int = 0
    ADMIN_IDS: list[int] = []

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

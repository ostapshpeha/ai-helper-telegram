from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Honda AI Assistant"
    MONGO_DB_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "honda_db"
    MONGO_DB_PASSWORD: str = ""
    GEMINI_API_KEY: str = ""

    TELEGRAM_BOT_TOKEN: str = ""
    STAFF_CHAT_ID: int = 0
    ADMIN_IDS: list[int] = []
    MINI_APP_URL: str = ""  # Public HTTPS URL where mini_app/ is served, e.g. https://yourdomain.com/mini-app

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

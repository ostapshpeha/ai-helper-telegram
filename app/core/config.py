from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Honda AI Assistant"
    MONGO_DB_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "honda_db"
    MONGO_DB_PASSWORD: str = "password"

    GEMINI_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()

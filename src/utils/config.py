from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # Google API Keys
    GOOGLE_API_KEY: str
    GOOGLE_PROJECT_ID: str
    
    # Google Calendar
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    # Notion
    NOTION_TOKEN: str
    NOTION_DATABASE_ID: str

    # Application Settings
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
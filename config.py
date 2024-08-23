from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    database_url: str
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None

    class Config:
        env_file = ".env"

    def __init__(self, **values):
        super().__init__(**values)

settings = Settings()
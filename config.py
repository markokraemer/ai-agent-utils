import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    database_url: str
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    workspace_dir: str = '/Users/markokraemer/Projects/softgen/automata/workspace'

    class Config:
        env_file = ".env"

    def __init__(self, **values):
        super().__init__(**values)
        os.makedirs(self.workspace_dir, exist_ok=True)

settings = Settings()
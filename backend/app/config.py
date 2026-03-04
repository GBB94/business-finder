import uuid
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./ideascope.db"
    REDIS_URL: str = "redis://redis:6379/0"
    ANTHROPIC_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    DEFAULT_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./ideascope.db"
    REDIS_URL: str = "redis://redis:6379/0"
    ANTHROPIC_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-5-20250929"
    REDDIT_USER_AGENT: str = "IdeaScope/0.1 by u/ideascope"
    DEFAULT_USER_ID: str = "00000000-0000-0000-0000-000000000001"
    ANTHROPIC_ZDR_ENABLED: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


def default_user_id() -> str:
    """Callable default for model user_id columns."""
    return settings.DEFAULT_USER_ID

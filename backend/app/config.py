from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://ideascope:ideascope_dev@localhost:5432/ideascope"
    REDIS_URL: str = "redis://redis:6379/0"
    ANTHROPIC_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-5-20250929"
    REDDIT_USER_AGENT: str = "IdeaScope/0.1 by u/ideascope"
    ANTHROPIC_ZDR_ENABLED: bool = False

    # Auth
    DEFAULT_USER_EMAIL: str = "admin@ideascope.dev"
    DEFAULT_USER_PASSWORD: str = "changeme"
    SESSION_SECRET_KEY: str = "change-me-to-a-random-string"
    SESSION_TTL_HOURS: int = 24

    # Secrets encryption
    SECRETS_MASTER_KEY: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

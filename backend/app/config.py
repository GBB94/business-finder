from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://ideascope:ideascope_dev@localhost:5432/ideascope"
    REDIS_URL: str = "redis://redis:6379/0"
    ANTHROPIC_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-5-20250929"  # default / Sonnet tier
    CLAUDE_MODEL_HAIKU: str = "claude-haiku-4-5-20251001"
    CLAUDE_MODEL_OPUS: str = "claude-opus-4-6"
    REDDIT_USER_AGENT: str = "IdeaScope/0.1 by u/ideascope"
    ANTHROPIC_ZDR_ENABLED: bool = False

    # Auth
    SEED_DEV_USER: bool = False
    DEFAULT_USER_EMAIL: str = ""
    DEFAULT_USER_PASSWORD: str = ""
    SESSION_SECRET_KEY: str = "change-me-to-a-random-string"
    SESSION_TTL_HOURS: int = 24
    COOKIE_SECURE: bool = True
    CSRF_SECRET: str = ""  # HMAC secret for CSRF token signing; falls back to SESSION_SECRET_KEY

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"  # comma-separated allowed origins

    # Email (Resend) — used for CEO morning email
    RESEND_API_KEY: str = ""
    FOUNDER_EMAIL: str = ""
    RESEND_FROM_EMAIL: str = "launchpad@updates.localhost"

    # Per-environment provider credentials (preview uses test/sandbox keys)
    STRIPE_TEST_SECRET_KEY: str = ""
    STRIPE_TEST_PUBLISHABLE_KEY: str = ""
    STRIPE_LIVE_SECRET_KEY: str = ""
    STRIPE_LIVE_PUBLISHABLE_KEY: str = ""
    NEON_API_KEY: str = ""
    GITHUB_TOKEN: str = ""           # GitHub PAT for repo creation and branch management
    GITHUB_ORG: str = ""             # GitHub org or user for new repos (e.g. "GBB94")
    GITHUB_TEMPLATE_REPO: str = ""   # Template repo (e.g. "GBB94/launchpad-template")
    RENDER_API_KEY: str = ""         # Render API key for service management
    RENDER_OWNER_ID: str = ""        # Render owner/team ID for new services
    RESEND_SANDBOX_API_KEY: str = ""  # Resend sandbox key for preview deployments
    RESEND_WEBHOOK_SECRET: str = ""  # Resend webhook signing secret
    STRIPE_WEBHOOK_SECRET: str = ""  # Stripe webhook signing secret (whsec_...)

    # Engineering task isolation
    WORKDIR_BASE: str = "/tmp/launchpad-workdirs"  # base path for ephemeral task workdirs
    BUILDER_UID: int = 0   # 0 = no chown (dev mode); set to unprivileged UID in production
    BUILDER_GID: int = 0   # 0 = no chown (dev mode); set to unprivileged GID in production

    # Error spike detection
    ERROR_SPIKE_WINDOW_MINUTES: int = 60  # sliding window for error counting
    ERROR_SPIKE_THRESHOLD: int = 10       # number of errors to trigger a spike event

    # Secrets encryption
    SECRETS_MASTER_KEY: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

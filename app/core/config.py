from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    CORS_ORIGINS: str = "http://localhost:3000,https://the-campus-frontend-production.up.railway.app"

    # Payment provider placeholder
    PAYMENT_PROVIDER: str = "stripe"
    PAYMENT_SECRET_KEY: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Email
    RESEND_API_KEY: str = ""
    EMAIL_FROM_DOMAIN: str = "thecampus.app"
    FRONTEND_URL: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def cors_allow_credentials(self) -> bool:
        # CORS spec forbids credentials with wildcard origin.
        # Automatically disable credentials when wildcard is detected.
        return "*" not in self.cors_origins_list

    class Config:
        env_file = ".env"


settings = Settings()

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    SUPABASE_URL: str = "https://placeholder-project.supabase.co"
    SUPABASE_SERVICE_KEY: str = "placeholder-service-key"  # service-role key - backend-only, never exposed to frontend

    # JWT
    JWT_SECRET_KEY: str = "sortdesk-production-secure-jwt-key-2026-safe-fallback"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Google OAuth2 (recruiter login)
    GOOGLE_CLIENT_ID: str = "placeholder-google-client-id"
    GOOGLE_CLIENT_SECRET: str = "placeholder-google-client-secret"
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # Gmail integration (separate consent from login - broader scopes, offline access)
    GMAIL_REDIRECT_URI: str = "http://localhost:8000/gmail/callback"
    GMAIL_TOKEN_ENCRYPTION_KEY: str = "dGVzdC1mZXJuZXQta2V5LTEyMzQ1Njc4OWFiY2RlZjA="

    # Outlook integration (Microsoft Graph)
    OUTLOOK_CLIENT_ID: str = ""
    OUTLOOK_CLIENT_SECRET: str = ""
    OUTLOOK_REDIRECT_URI: str = "http://localhost:8000/outlook/callback"

    # Redis (OAuth state storage here today; Celery broker later)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"
    FRONTEND_OAUTH_SUCCESS_PATH: str = "/auth/callback"

    ENVIRONMENT: str = "development"  # development | staging | production


@lru_cache
def get_settings() -> Settings:
    return Settings()

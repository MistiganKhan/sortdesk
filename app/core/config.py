import os
from functools import lru_cache
from typing import Any
from pydantic import field_validator
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

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES", mode="before")
    @classmethod
    def clean_access_token_expire(cls, v: Any) -> int:
        if v is None or v == "" or (isinstance(v, str) and not v.strip()):
            return 60
        try:
            return int(v)
        except (ValueError, TypeError):
            return 60

    @field_validator("REFRESH_TOKEN_EXPIRE_DAYS", mode="before")
    @classmethod
    def clean_refresh_token_expire(cls, v: Any) -> int:
        if v is None or v == "" or (isinstance(v, str) and not v.strip()):
            return 30
        try:
            return int(v)
        except (ValueError, TypeError):
            return 30

    @field_validator("JWT_ALGORITHM", mode="before")
    @classmethod
    def clean_jwt_algorithm(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "HS256"
        return str(v).strip()

    @field_validator("SUPABASE_URL", mode="before")
    @classmethod
    def clean_supabase_url(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "https://placeholder-project.supabase.co"
        return str(v).strip()

    @field_validator("SUPABASE_SERVICE_KEY", mode="before")
    @classmethod
    def clean_supabase_key(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "placeholder-service-key"
        return str(v).strip()

    @field_validator("JWT_SECRET_KEY", mode="before")
    @classmethod
    def clean_jwt_secret(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "sortdesk-production-secure-jwt-key-2026-safe-fallback"
        return str(v).strip()

    @field_validator("GMAIL_TOKEN_ENCRYPTION_KEY", mode="before")
    @classmethod
    def clean_gmail_encryption_key(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "dGVzdC1mZXJuZXQta2V5LTEyMzQ1Njc4OWFiY2RlZjA="
        return str(v).strip()

    @field_validator("FRONTEND_URL", mode="before")
    @classmethod
    def clean_frontend_url(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "http://localhost:3000"
        return str(v).strip()

    @field_validator("GOOGLE_REDIRECT_URI", mode="before")
    @classmethod
    def clean_google_redirect_uri(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "http://localhost:8000/auth/google/callback"
        return str(v).strip()

    @field_validator("GMAIL_REDIRECT_URI", mode="before")
    @classmethod
    def clean_gmail_redirect_uri(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "http://localhost:8000/gmail/callback"
        return str(v).strip()

    @field_validator("OUTLOOK_REDIRECT_URI", mode="before")
    @classmethod
    def clean_outlook_redirect_uri(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "http://localhost:8000/outlook/callback"
        return str(v).strip()

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def clean_redis_url(cls, v: Any) -> str:
        if not v or (isinstance(v, str) and not v.strip()):
            return "redis://localhost:6379/0"
        return str(v).strip()


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except Exception:
        # Extra safety fallback if an unknown environment variable type causes a crash
        for k in ["ACCESS_TOKEN_EXPIRE_MINUTES", "REFRESH_TOKEN_EXPIRE_DAYS"]:
            if k in os.environ and not os.environ[k].strip():
                del os.environ[k]
        return Settings()

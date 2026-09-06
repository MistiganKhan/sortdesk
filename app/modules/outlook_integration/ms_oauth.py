import httpx
from urllib.parse import urlencode

from app.core.config import get_settings

settings = get_settings()

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

OUTLOOK_SCOPES = [
    "offline_access",
    "User.Read",
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
]


def build_outlook_auth_url(state: str) -> str:
    params = {
        "client_id": settings.OUTLOOK_CLIENT_ID,
        "redirect_uri": settings.OUTLOOK_REDIRECT_URI,
        "response_type": "code",
        "response_mode": "query",
        "scope": " ".join(OUTLOOK_SCOPES),
        "state": state,
        "prompt": "consent",
    }
    return f"{MS_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_outlook_tokens(code: str) -> dict:
    """Returns Microsoft's token response: access_token, refresh_token, expires_in, ..."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            MS_TOKEN_URL,
            data={
                "client_id": settings.OUTLOOK_CLIENT_ID,
                "client_secret": settings.OUTLOOK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.OUTLOOK_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_outlook_access_token(refresh_token: str) -> dict:
    """Exchange stored refresh_token for a fresh Microsoft Graph access_token."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            MS_TOKEN_URL,
            data={
                "client_id": settings.OUTLOOK_CLIENT_ID,
                "client_secret": settings.OUTLOOK_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()

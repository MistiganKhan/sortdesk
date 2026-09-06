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


# ---------- Recruiter Authentication / Login via Microsoft Identity ----------

MS_LOGIN_SCOPES = [
    "openid",
    "profile",
    "email",
    "User.Read",
]


def build_ms_login_url(state: str, redirect_uri: str | None = None) -> str:
    """Builds Microsoft authorization URL specifically for signing in recruiters."""
    client_id = settings.OUTLOOK_CLIENT_ID or "00000000-0000-0000-0000-000000000000"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri or settings.MICROSOFT_REDIRECT_URI,
        "response_type": "code",
        "response_mode": "query",
        "scope": " ".join(MS_LOGIN_SCOPES),
        "state": state,
        "prompt": "select_account",
    }
    return f"{MS_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_ms_login_tokens(code: str, redirect_uri: str | None = None) -> dict:
    """Exchanges code for access token using the auth callback redirect URI."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            MS_TOKEN_URL,
            data={
                "client_id": settings.OUTLOOK_CLIENT_ID,
                "client_secret": settings.OUTLOOK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri or settings.MICROSOFT_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_ms_user_info(access_token: str) -> dict:
    """Fetches recruiter profile from Microsoft Graph /me endpoint."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        email = data.get("mail") or data.get("userPrincipalName")
        return {
            "email": email.lower() if email else None,
            "name": data.get("displayName") or "Microsoft User",
            "id": data.get("id"),
        }


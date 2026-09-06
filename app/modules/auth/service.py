from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.core.config import get_settings
from app.modules.auth import repository as repo
from app.modules.auth.google_oauth import exchange_code_for_google_tokens, get_google_user_info

settings = get_settings()


def _issue_token_pair(user: dict, user_agent: str | None, ip_address: str | None) -> dict:
    access_token = create_access_token(user_id=user["id"], email=user["email"])
    raw_refresh, refresh_hash = generate_refresh_token()

    repo.store_refresh_token(
        user_id=user["id"],
        token_hash=refresh_hash,
        expires_at=refresh_token_expiry(),
        user_agent=user_agent,
        ip_address=ip_address,
    )

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def signup_with_email(
    email: str,
    password: str,
    full_name: str | None,
    company_name: str | None,
    user_agent: str | None,
    ip_address: str | None,
) -> dict:
    normalized_email = email.strip().lower()
    existing = repo.get_user_by_email(normalized_email)
    if existing:
        # If user exists with password, check it or inform user
        if existing.get("password_hash") and not verify_password(password, existing["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists. Please log in with your existing password.",
            )
        user = existing
        # Update name/company if provided
        updates = {}
        if full_name and not existing.get("full_name"):
            updates["full_name"] = full_name
        if company_name and not existing.get("company_name"):
            updates["company_name"] = company_name
        if updates:
            user = repo.update_user(user["id"], updates) or user
    else:
        pw_hash = hash_password(password)
        user = repo.create_user(
            email=normalized_email,
            full_name=full_name,
            company_name=company_name,
            password_hash=pw_hash,
        )

    tokens = _issue_token_pair(user, user_agent, ip_address)
    return {"user": user, "tokens": tokens}


def login_with_email(
    email: str,
    password: str,
    user_agent: str | None,
    ip_address: str | None,
) -> dict:
    normalized_email = email.strip().lower()
    user = repo.get_user_by_email(normalized_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No account found with this email. Please sign up to create your recruiter workspace.",
        )

    stored_hash = user.get("password_hash")
    if stored_hash:
        if not verify_password(password, stored_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password. Please verify your credentials and try again.",
            )
    else:
        # Set password for accounts previously created via demo or oauth
        pw_hash = hash_password(password)
        user = repo.update_user(user["id"], {"password_hash": pw_hash}) or user

    tokens = _issue_token_pair(user, user_agent, ip_address)
    return {"user": user, "tokens": tokens}



async def login_with_google(code: str, user_agent: str | None, ip_address: str | None) -> dict:
    google_tokens = await exchange_code_for_google_tokens(code)
    google_access_token = google_tokens.get("access_token")
    if not google_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google token exchange failed")

    userinfo = await get_google_user_info(google_access_token)
    if not userinfo.get("email_verified", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google email is not verified")

    user = repo.get_or_create_user(email=userinfo["email"], full_name=userinfo.get("name"))
    tokens = _issue_token_pair(user, user_agent, ip_address)
    return {"user": user, "tokens": tokens}


def refresh_tokens(raw_refresh_token: str, user_agent: str | None, ip_address: str | None) -> dict:
    token_hash = hash_refresh_token(raw_refresh_token)
    existing = repo.get_refresh_token_by_hash(token_hash)

    if existing is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if existing["revoked_at"] is not None:
        repo.revoke_all_user_tokens(existing["user_id"])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has already been used. All sessions revoked - please log in again.",
        )

    expires_at = datetime.fromisoformat(existing["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = repo.get_user_by_id(existing["user_id"])
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")

    new_tokens = _issue_token_pair(user, user_agent, ip_address)

    new_hash = hash_refresh_token(new_tokens["refresh_token"])
    new_row = repo.get_refresh_token_by_hash(new_hash)
    repo.revoke_refresh_token(existing["id"], replaced_by=new_row["id"] if new_row else None)

    return {"user": user, "tokens": new_tokens}


def logout(raw_refresh_token: str) -> None:
    token_hash = hash_refresh_token(raw_refresh_token)
    existing = repo.get_refresh_token_by_hash(token_hash)
    if existing and existing["revoked_at"] is None:
        repo.revoke_refresh_token(existing["id"])


def login_with_sso_direct(
    provider: str,
    email: str | None,
    full_name: str | None,
    company_name: str | None,
    user_agent: str | None,
    ip_address: str | None,
) -> dict:
    """Provides direct, one-click Single Sign-On (SSO) for Google or Microsoft accounts."""
    prov = provider.strip().lower()
    if prov in ("google", "gmail"):
        target_email = email.strip().lower() if email else "recruiter.google@sortdesk.ai"
        target_name = full_name or "Google Workspace Recruiter"
        target_company = company_name or "Google Workspace Talent"
    elif prov in ("microsoft", "outlook", "office365", "azure"):
        target_email = email.strip().lower() if email else "recruiter.microsoft@sortdesk.ai"
        target_name = full_name or "Microsoft 365 Recruiter"
        target_company = company_name or "Microsoft 365 Talent"
    else:
        target_email = email.strip().lower() if email else f"recruiter.{prov}@sortdesk.ai"
        target_name = full_name or f"{prov.capitalize()} Recruiter"
        target_company = company_name or "SortDesk Agency"

    user = repo.get_or_create_user(
        email=target_email,
        full_name=target_name,
        company_name=target_company,
    )
    tokens = _issue_token_pair(user, user_agent, ip_address)
    return {"user": user, "tokens": tokens}

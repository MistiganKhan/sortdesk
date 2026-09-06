from datetime import datetime, timezone

from fastapi import HTTPException, status
from app.core.config import get_settings
from app.core.rate_limiter import auth_rate_limiter
from app.core.security import (
    create_access_token,
    dummy_verify_password,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    refresh_token_expiry,
    verify_password,
)
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

    # Rate limiting on signup attempts per IP to prevent automated account creation abuse
    if ip_address:
        ip_key = f"signup_ip:{ip_address}"
        allowed_ip, retry_after_ip = auth_rate_limiter.is_allowed(ip_key, max_attempts=15, window_seconds=3600)
        if not allowed_ip:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many account creation requests from this network. Please try again in {retry_after_ip} seconds.",
                headers={"Retry-After": str(retry_after_ip)},
            )
        auth_rate_limiter.record_failure(ip_key, window_seconds=3600)

    existing = repo.get_user_by_email(normalized_email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists. Please sign in.",
        )

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
    ip_key = f"ip:{ip_address}" if ip_address else None
    email_key = f"email:{normalized_email}"

    # 1. Enforce IP-based rate limiting (5 failed attempts per 15 minutes)
    if ip_key:
        allowed_ip, retry_after_ip = auth_rate_limiter.is_allowed(ip_key)
        if not allowed_ip:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts from this network. Please try again in {retry_after_ip} seconds.",
                headers={"Retry-After": str(retry_after_ip)},
            )

    # 2. Enforce account-based rate limiting (5 failed attempts per 15 minutes)
    allowed_email, retry_after_email = auth_rate_limiter.is_allowed(email_key)
    if not allowed_email:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts for this account. Please try again in {retry_after_email} seconds.",
            headers={"Retry-After": str(retry_after_email)},
        )

    # 3. Retrieve user and verify credentials with timing side-channel mitigation
    user = repo.get_user_by_email(normalized_email)
    if not user:
        dummy_verify_password()  # Execute constant-time calculation to eliminate user enumeration
        if ip_key:
            auth_rate_limiter.record_failure(ip_key)
        auth_rate_limiter.record_failure(email_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    stored_hash = user.get("password_hash")
    if not stored_hash or not verify_password(password, stored_hash):
        if ip_key:
            auth_rate_limiter.record_failure(ip_key)
        auth_rate_limiter.record_failure(email_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # 4. Authentication succeeded: Reset failure counters
    if ip_key:
        auth_rate_limiter.reset_failures(ip_key)
    auth_rate_limiter.reset_failures(email_key)

    # 5. Transparently upgrade legacy or lower-iteration password hashes
    if needs_rehash(stored_hash):
        new_hash = hash_password(password)
        user = repo.update_user(user["id"], {"password_hash": new_hash}) or user

    tokens = _issue_token_pair(user, user_agent, ip_address)
    return {"user": user, "tokens": tokens}


async def login_with_google(code: str, user_agent: str | None, ip_address: str | None, redirect_uri: str | None = None) -> dict:
    google_tokens = await exchange_code_for_google_tokens(code, redirect_uri=redirect_uri)
    google_access_token = google_tokens.get("access_token")
    if not google_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google token exchange failed")

    userinfo = await get_google_user_info(google_access_token)
    if not userinfo.get("email_verified", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google email is not verified")

    user = repo.get_or_create_user(email=userinfo["email"], full_name=userinfo.get("name"))
    tokens = _issue_token_pair(user, user_agent, ip_address)
    return {"user": user, "tokens": tokens}


async def login_with_microsoft(code: str, user_agent: str | None, ip_address: str | None, redirect_uri: str | None = None) -> dict:
    from app.modules.outlook_integration.ms_oauth import (
        exchange_code_for_ms_login_tokens,
        get_ms_user_info,
    )
    ms_tokens = await exchange_code_for_ms_login_tokens(code, redirect_uri=redirect_uri)
    access_token = ms_tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Microsoft token exchange failed")

    userinfo = await get_ms_user_info(access_token)
    email = userinfo.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Microsoft account has no valid email address")

    user = repo.get_or_create_user(
        email=email,
        full_name=userinfo.get("name"),
        company_name="Microsoft 365 Recruiter",
    )
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

    # Prevent account takeover of password-protected accounts via unverified direct SSO
    if email:
        target_check = email.strip().lower()
        existing = repo.get_user_by_email(target_check)
        if existing and existing.get("password_hash"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is protected by a password. Please sign in with your email and password, or use verified OAuth.",
            )

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

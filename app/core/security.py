import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT

from app.core.config import get_settings

settings = get_settings()


# ---------- Access token (stateless JWT, short-lived) ----------

def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.PyJWTError:
        return None


# ---------- Refresh token (opaque random string, hashed at rest) ----------
# The raw token is only ever seen by the client. We store SHA-256(raw) so a DB
# leak doesn't hand out usable tokens. This is a hash for lookup speed, not a
# password - no need for bcrypt/salt here since the input already has ~256 bits
# of entropy from secrets.token_urlsafe.

def generate_refresh_token() -> tuple[str, str]:
    """Returns (raw_token_to_send_to_client, hash_to_store_in_db)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


# ---------- Password Hashing (Salted SHA-256 with Constant-Time Comparison) ----------

def hash_password(password: str) -> str:
    """Hashes a password with a 16-byte random hex salt."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verifies a password against a salt$hash string using constant-time comparison."""
    if not password_hash or "$" not in password_hash:
        return False
    salt, hashed = password_hash.split("$", 1)
    test_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(hashed, test_hash)


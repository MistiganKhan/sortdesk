import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import hash_password, verify_password, needs_rehash
from app.core.rate_limiter import auth_rate_limiter
from app.modules.auth import repository as repo

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_test_rate_limits():
    auth_rate_limiter.reset_failures("ip:testclient")
    yield
    auth_rate_limiter.reset_failures("ip:testclient")



def test_pbkdf2_password_hashing():
    """Verify modern PBKDF2-HMAC-SHA256 hashing format and verification."""
    password = "Secur3P@ssword2026!"
    hashed = hash_password(password)
    
    assert hashed.startswith("pbkdf2:100000$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert needs_rehash(hashed) is False


def test_legacy_hash_compatibility_and_auto_migration():
    """Verify legacy salt$hash passwords still verify and are seamlessly upgraded to PBKDF2 on login."""
    import hashlib, secrets
    legacy_password = "LegacyP@ssword123"
    salt = secrets.token_hex(16)
    legacy_hash = f"{salt}${hashlib.sha256((salt + legacy_password).encode()).hexdigest()}"
    
    # Check verification works
    assert verify_password(legacy_password, legacy_hash) is True
    assert verify_password("WrongPass!", legacy_hash) is False
    assert needs_rehash(legacy_hash) is True

    # Register user with legacy hash
    test_email = "legacy.user@example-recruiting.com"
    user = repo.get_or_create_user(email=test_email, full_name="Legacy User")
    repo.update_user(user["id"], {"password_hash": legacy_hash})

    # Log in - should succeed and automatically upgrade hash to PBKDF2
    login_resp = client.post("/auth/login", json={"email": test_email, "password": legacy_password})
    assert login_resp.status_code == 200

    updated_user = repo.get_user_by_id(user["id"])
    assert updated_user["password_hash"].startswith("pbkdf2:100000$")


def test_password_complexity_validation():
    """Verify password policy enforces length and complexity."""
    # Under 8 characters
    resp_short = client.post("/auth/signup", json={
        "email": "short@example.com",
        "password": "Short1"
    })
    assert resp_short.status_code == 422

    # Letters only (no numbers or symbols)
    resp_letters = client.post("/auth/signup", json={
        "email": "letters@example.com",
        "password": "AllLettersOnlyPassword"
    })
    assert resp_letters.status_code == 422

    # Numbers only
    resp_digits = client.post("/auth/signup", json={
        "email": "digits@example.com",
        "password": "123456789012345"
    })
    assert resp_digits.status_code == 422


def test_user_enumeration_defense():
    """Verify failed login returns identical error message regardless of whether email exists."""
    resp_nonexistent = client.post("/auth/login", json={
        "email": "definitely.not.exists.999@randomdomain.xyz",
        "password": "SomePassword123!"
    })
    assert resp_nonexistent.status_code == 401
    assert resp_nonexistent.json()["detail"] == "Invalid email or password."


def test_account_takeover_prevention_on_signup():
    """Verify signup rejects already registered emails and does not overwrite them."""
    email = "existing.recruiter@agency.io"
    client.post("/auth/signup", json={
        "email": email,
        "password": "OriginalPassword1!",
        "full_name": "Original Name"
    })

    # Attempt signup again with different details
    takeover_attempt = client.post("/auth/signup", json={
        "email": email,
        "password": "AttackerPassword2!",
        "full_name": "Attacker"
    })
    assert takeover_attempt.status_code == 400
    assert "already exists" in takeover_attempt.json()["detail"].lower()


def test_brute_force_rate_limiting():
    """Verify that multiple failed login attempts trigger HTTP 429 Too Many Requests."""
    target_email = "bruteforce.target@agency.com"
    # Create target account
    client.post("/auth/signup", json={
        "email": target_email,
        "password": "ValidPassword123!"
    })

    # Reset any prior failures for test IP and this email
    auth_rate_limiter.reset_failures(f"email:{target_email}")
    auth_rate_limiter.reset_failures("ip:testclient")

    # Send 5 failed attempts
    for _ in range(5):
        resp = client.post("/auth/login", json={
            "email": target_email,
            "password": "WrongPasswordAttempt!"
        })
        assert resp.status_code == 401

    # 6th attempt must be locked out with HTTP 429
    locked_resp = client.post("/auth/login", json={
        "email": target_email,
        "password": "WrongPasswordAttempt!"
    })
    assert locked_resp.status_code == 429
    assert "Retry-After" in locked_resp.headers
    assert "Too many failed login attempts" in locked_resp.json()["detail"]

    # Clean up test IP and email so subsequent tests run cleanly
    auth_rate_limiter.reset_failures("ip:testclient")
    auth_rate_limiter.reset_failures(f"email:{target_email}")


def test_sso_direct_account_takeover_protection():
    """Verify direct SSO cannot take over an existing password-protected account."""
    protected_email = "password.protected@agency.com"
    client.post("/auth/signup", json={
        "email": protected_email,
        "password": "StrongSecretPass1!"
    })

    # Attempt to bypass password via unverified direct SSO
    bypass_resp = client.post("/auth/sso", json={
        "provider": "google",
        "email": protected_email
    })
    assert bypass_resp.status_code == 403
    assert "protected by a password" in bypass_resp.json()["detail"]


def test_security_headers_present():
    """Verify OWASP security headers are present on HTTP responses."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

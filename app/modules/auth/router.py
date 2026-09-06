from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.oauth_state import generate_state, verify_state
from app.modules.auth import repository as repo
from app.modules.auth import service
from app.modules.auth.google_oauth import build_google_auth_url
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    SignUpRequest,
    SSORequest,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/signup", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignUpRequest, request: Request):
    """Register a new recruiter account with any email address (no Google/Outlook lock-in)."""
    return service.signup_with_email(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        company_name=body.company_name,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    """Log in with any registered email address and password."""
    return service.login_with_email(
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


@router.post("/sso", response_model=LoginResponse)
async def sso_direct_login(body: SSORequest, request: Request):
    """
    Direct Single Sign-On (SSO) login/signup for Google or Microsoft accounts.
    Provides instant, 1-click workspace authentication.
    """
    return service.login_with_sso_direct(
        provider=body.provider,
        email=body.email,
        full_name=body.full_name,
        company_name=body.company_name,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


@router.get("/google/login")
async def google_login(request: Request):
    if not settings.GOOGLE_CLIENT_ID or settings.GOOGLE_CLIENT_ID.startswith("placeholder"):
        err = "Google OAuth requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to be configured in your environment variables."
        return RedirectResponse(f"/?auth_error={quote(err)}")

    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    if host and "localhost" in host:
        redirect_uri = f"{proto}://{host}/auth/google/callback"
    elif host and "vercel.app" in host:
        redirect_uri = f"https://{host}/auth/google/callback"

    state = generate_state()
    auth_url = build_google_auth_url(state, redirect_uri=redirect_uri)
    return RedirectResponse(auth_url)


@router.get("/microsoft/login")
async def microsoft_login(request: Request):
    if not settings.OUTLOOK_CLIENT_ID or settings.OUTLOOK_CLIENT_ID.startswith("placeholder"):
        err = "Microsoft OAuth requires OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET to be configured in your environment variables."
        return RedirectResponse(f"/?auth_error={quote(err)}")

    from app.modules.outlook_integration.ms_oauth import build_ms_login_url

    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    redirect_uri = settings.MICROSOFT_REDIRECT_URI
    if host and "localhost" in host:
        redirect_uri = f"{proto}://{host}/auth/microsoft/callback"
    elif host and "vercel.app" in host:
        redirect_uri = f"https://{host}/auth/microsoft/callback"

    state = generate_state()
    auth_url = build_ms_login_url(state, redirect_uri=redirect_uri)
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str):
    is_valid, _ = verify_state(state)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    if host and "localhost" in host:
        redirect_uri = f"{proto}://{host}/auth/google/callback"
    elif host and "vercel.app" in host:
        redirect_uri = f"https://{host}/auth/google/callback"

    result = await service.login_with_google(
        code=code,
        redirect_uri=redirect_uri,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    tokens = result["tokens"]
    redirect_url = (
        f"/auth/callback#access_token={tokens['access_token']}&refresh_token={tokens['refresh_token']}&provider=google"
    )
    return RedirectResponse(redirect_url)


@router.get("/microsoft/callback")
async def microsoft_callback(request: Request, code: str, state: str):
    is_valid, _ = verify_state(state)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    redirect_uri = settings.MICROSOFT_REDIRECT_URI
    if host and "localhost" in host:
        redirect_uri = f"{proto}://{host}/auth/microsoft/callback"
    elif host and "vercel.app" in host:
        redirect_uri = f"https://{host}/auth/microsoft/callback"

    result = await service.login_with_microsoft(
        code=code,
        redirect_uri=redirect_uri,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    tokens = result["tokens"]
    redirect_url = (
        f"/auth/callback#access_token={tokens['access_token']}&refresh_token={tokens['refresh_token']}&provider=microsoft"
    )
    return RedirectResponse(redirect_url)



@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, request: Request):
    result = service.refresh_tokens(
        raw_refresh_token=body.refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    return result["tokens"]


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest):
    service.logout(body.refresh_token)
    return None


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    user = repo.get_user_by_id(current_user["id"])
    if not user:
        return {
            "id": current_user["id"],
            "email": current_user["email"],
            "full_name": current_user["email"].split("@")[0].replace(".", " ").title(),
            "company_name": "SortDesk Agency",
        }
    return user


@router.get("/demo-token")
async def get_demo_token():
    """Generates a demo session token for testing SortDesk without external OAuth."""
    from app.core.security import create_access_token
    demo_user_id = "00000000-0000-0000-0000-000000000001"
    demo_email = "demo.recruiter@sortdesk.ai"
    token = create_access_token(demo_user_id, demo_email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": demo_user_id,
            "email": demo_email,
            "full_name": "Demo Recruiter (SortDesk)",
        },
    }

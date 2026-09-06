import os
import sys
from pathlib import Path

# Ensure root directory and app directory are on sys.path in serverless runtimes
_CURRENT_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _CURRENT_DIR.parent
for _path in [str(_ROOT_DIR), str(_CURRENT_DIR)]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.modules.auth.router import router as auth_router
from app.modules.gmail_integration.router import router as gmail_router
from app.modules.emails.router import router as emails_router
from app.modules.drafts.router import router as drafts_router
from app.modules.queue.router import router as queue_router
from app.modules.outlook_integration.router import router as outlook_router
from app.modules.chat.router import router as chat_router
from app.modules.candidates.router import router as candidates_router

settings = get_settings()

app = FastAPI(
    title="SortDesk — AI Recruiter Email Assistant API",
    description="SortDesk: AI-powered Gmail & Outlook agent for HR recruiters",
    version="1.0.0",
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": str(exc)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(gmail_router)
app.include_router(outlook_router)
app.include_router(emails_router)
app.include_router(drafts_router)
app.include_router(queue_router)
app.include_router(chat_router)
app.include_router(candidates_router)

def _read_template(filename: str) -> str:
    possible_paths = [
        Path(__file__).resolve().parent / "templates" / filename,
        Path.cwd() / "app" / "templates" / filename,
        Path("/var/task/app/templates") / filename,
        Path(__file__).resolve().parent.parent / "app" / "templates" / filename,
    ]
    for p in possible_paths:
        try:
            if p.exists():
                return p.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def sortdesk_landing():
    """Serves the SortDesk Product Landing Page."""
    content = _read_template("landing.html") or _read_template("dashboard.html")
    if content:
        return HTMLResponse(content=content)
    return RedirectResponse(url="/docs")


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def sortdesk_dashboard():
    """Serves the SortDesk Recruiter Dashboard."""
    content = _read_template("dashboard.html")
    if content:
        return HTMLResponse(content=content)
    return RedirectResponse(url="/docs")


@app.get("/auth/callback", response_class=HTMLResponse, include_in_schema=False)
async def sortdesk_auth_callback():
    """Client-side OAuth success callback handler that stores tokens and redirects to dashboard."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SortDesk — Authenticating...</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {
      background-color: #1A1A1A;
      color: #FFFFFF;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
    }
    .card {
      background: #242424;
      border: 1px solid #383838;
      border-radius: 16px;
      padding: 32px 40px;
      text-align: center;
      max-width: 380px;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    }
    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid rgba(245, 184, 0, 0.2);
      border-top-color: #F5B800;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin: 0 auto 16px auto;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="card">
    <div class="spinner"></div>
    <h3 style="margin: 0 0 8px 0; font-size: 18px; font-weight: 700;">Connecting your Workspace</h3>
    <p style="margin: 0; font-size: 13px; color: #A0AEC0;">Authenticating with Single Sign-On...</p>
  </div>
  <script>
    try {
      const hash = window.location.hash.substring(1);
      const params = new URLSearchParams(hash);
      const token = params.get('access_token');
      const provider = params.get('provider') || 'OAuth';
      if (token) {
        localStorage.setItem('sortdesk_auth_token', token);
        const name = provider === 'google' ? 'Google Workspace Recruiter' : 'Microsoft 365 Recruiter';
        const email = provider === 'google' ? 'recruiter.google@sortdesk.ai' : 'recruiter.microsoft@sortdesk.ai';
        const company = provider === 'google' ? 'Google Workspace Talent' : 'Microsoft 365 Talent';
        localStorage.setItem('sortdesk_user', JSON.stringify({ email, full_name: name, company_name: company }));
        localStorage.setItem('sortdesk_company_name', company);
      }
    } catch(e) {}
    window.location.href = '/dashboard';
  </script>
</body>
</html>""")


@app.get("/health")
async def health():
    return {"status": "ok", "app": "SortDesk", "version": "1.0.0"}

import os
import sys
import traceback
from pathlib import Path

# Ensure root directory and app directory are on sys.path
ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "app"
for p in [str(ROOT_DIR), str(APP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from app.main import app
except Exception as e:
    _err = traceback.format_exc()
    print("FATAL ERROR IN INDEX.PY IMPORTING APP.MAIN:\n", _err, file=sys.stderr)
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    app = FastAPI(title="SortDesk Diagnostic Fallback")

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    async def _diagnostic_fallback(full_path: str = ""):
        return HTMLResponse(
            f"<html><body style='background:#18181b;color:#f43f5e;font-family:monospace;padding:30px;'>"
            f"<h2>SortDesk Startup Import Error</h2><pre style='background:#27272a;color:#fecdd3;padding:20px;border-radius:8px;'>{_err}</pre></body></html>",
            status_code=200
        )

__all__ = ["app"]

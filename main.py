import os
import sys
from pathlib import Path

# Ensure root directory and app directory are on Python path
ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "app"
for p in [str(ROOT_DIR), str(APP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import asyncio
import traceback

# Ensure event loop is active for ASGI in serverless environments
try:
    asyncio.get_running_loop()
except RuntimeError:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

try:
    from app.main import app
except Exception as e:
    _err = traceback.format_exc()
    print("FATAL ERROR IMPORTING APP.MAIN:\n", _err, file=sys.stderr)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

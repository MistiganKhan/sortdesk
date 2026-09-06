import os
import sys
import traceback
from pathlib import Path

# Add project root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from app.main import app
except Exception as e:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    tb = traceback.format_exc()
    app = FastAPI(title="SortDesk Diagnostics")

    @app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def catch_all(path_name: str = ""):
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:30px;background:#0f172a;color:#f1f5f9;'>"
            f"<h2 style='color:#ef4444;'>SortDesk Startup Diagnostic</h2>"
            f"<p>An exception occurred while importing the application on Vercel:</p>"
            f"<pre style='background:#1e293b;color:#fca5a5;padding:16px;border-radius:8px;overflow:auto;'>{tb}</pre>"
            f"</body></html>",
            status_code=500
        )

__all__ = ["app"]

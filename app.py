import os
import sys
import asyncio
from pathlib import Path

# Ensure root directory and app directory are on sys.path
ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "app"
for p in [str(ROOT_DIR), str(APP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Ensure event loop is active for ASGI in serverless environments
try:
    asyncio.get_running_loop()
except RuntimeError:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

from app.main import app

__all__ = ["app"]

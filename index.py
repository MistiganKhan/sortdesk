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
    from app.main import app as _inner_app
    _import_err = None
except Exception as e:
    _inner_app = None
    _import_err = traceback.format_exc()
    print("IMPORT ERROR IN INDEX.PY:", _import_err, file=sys.stderr)


class RobustASGIApp:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if _import_err:
            if scope.get("type") == "http":
                body = (
                    f"<html><body style='background:#111;color:#ff5555;font-family:monospace;padding:24px;'>"
                    f"<h2>SortDesk Import Error</h2>"
                    f"<pre>{_import_err}</pre>"
                    f"</body></html>"
                ).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"text/html; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": body,
                })
            return

        if scope.get("type") == "http" and scope.get("path") == "/_ping":
            body = b'{"status":"pong","message":"SortDesk serverless runner is live"}'
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
            return

        try:
            await self.inner(scope, receive, send)
        except Exception as exc:
            err = traceback.format_exc()
            print("CRITICAL ASGI RUNTIME ERROR:\n", err, file=sys.stderr)
            if scope.get("type") == "http":
                body = (
                    f"<html><body style='background:#111;color:#ff5555;font-family:monospace;padding:24px;'>"
                    f"<h2>SortDesk ASGI Runtime Error</h2>"
                    f"<pre>{err}</pre>"
                    f"</body></html>"
                ).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"text/html; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": body,
                })
            else:
                raise


app = RobustASGIApp(_inner_app)
__all__ = ["app"]

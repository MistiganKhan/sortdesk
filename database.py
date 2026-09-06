import os
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from app.core.database_adapter import get_local_db_adapter

db_url = SUPABASE_URL or ""
db_key = SUPABASE_SERVICE_KEY or ""

_supabase_client = None

def _is_placeholder(url: str, key: str) -> bool:
    if not url or not key:
        return True
    url_lower = url.lower()
    return "placeholder" in url_lower or "your_supabase" in url_lower or not url.startswith("http")

if not _is_placeholder(db_url, db_key):
    try:
        from supabase import create_client
        _supabase_client = create_client(db_url, db_key)
    except Exception:
        _supabase_client = None

def get_db():
    if _supabase_client is not None:
        return _supabase_client
    return get_local_db_adapter()

supabase = get_db()
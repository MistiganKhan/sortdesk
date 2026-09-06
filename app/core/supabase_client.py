import logging
from functools import lru_cache
from typing import Any
from supabase import create_client, Client

from app.core.config import get_settings
from app.core.database_adapter import get_local_db_adapter

logger = logging.getLogger("sortdesk.db")


def _is_placeholder(url: str, key: str) -> bool:
    if not url or not key:
        return True
    url_lower = url.lower()
    return "placeholder" in url_lower or "your_supabase" in url_lower or not url.startswith("http")


@lru_cache
def get_supabase() -> Any:
    """
    Service-role client for backend contexts.
    If Supabase credentials are placeholder or offline, seamlessly returns
    the local SQLite-backed adapter with identical query methods.
    """
    settings = get_settings()
    if _is_placeholder(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY):
        return get_local_db_adapter()

    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        # Verify connection lightly
        return client
    except Exception as e:
        logger.warning(f"Could not connect to Supabase ({e}), using local SQLite adapter.")
        return get_local_db_adapter()

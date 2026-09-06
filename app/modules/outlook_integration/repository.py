from app.core.supabase_client import get_supabase


def get_connection_by_user_and_address(user_id: str, outlook_address: str) -> dict | None:
    db = get_supabase()
    res = (
        db.table("outlook_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("outlook_address", outlook_address)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_connection_by_id(connection_id: str) -> dict | None:
    db = get_supabase()
    res = db.table("outlook_connections").select("*").eq("id", connection_id).limit(1).execute()
    return res.data[0] if res.data else None


def list_connections_for_user(user_id: str) -> list[dict]:
    db = get_supabase()
    res = db.table("outlook_connections").select("*").eq("user_id", user_id).execute()
    return res.data


def create_connection(user_id: str, outlook_address: str, encrypted_refresh_token: str) -> dict:
    db = get_supabase()
    res = db.table("outlook_connections").insert({
        "user_id": user_id,
        "outlook_address": outlook_address,
        "refresh_token": encrypted_refresh_token,
        "is_active": True,
    }).execute()
    return res.data[0]


def reactivate_connection(connection_id: str, encrypted_refresh_token: str) -> dict:
    """Reconnecting an existing mailbox refreshes its token and reactivates it."""
    db = get_supabase()
    res = (
        db.table("outlook_connections")
        .update({"refresh_token": encrypted_refresh_token, "is_active": True})
        .eq("id", connection_id)
        .execute()
    )
    return res.data[0]


def set_active(connection_id: str, is_active: bool) -> None:
    db = get_supabase()
    db.table("outlook_connections").update({"is_active": is_active}).eq("id", connection_id).execute()

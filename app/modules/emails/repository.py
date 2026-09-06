from postgrest.exceptions import APIError
from app.core.supabase_client import get_supabase


def insert_email_if_new(user_id: str, parsed: dict) -> dict | None:
    db = get_supabase()
    try:
        res = db.table("emails").insert({
            "user_id": user_id,
            **parsed,
        }).execute()
        return res.data[0] if res.data else None
    except APIError as e:
        if "duplicate key value" in str(e).lower() or "23505" in str(e):
            return None
        raise


def list_emails_for_user(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    db = get_supabase()
    res = (
        db.table("emails")
        .select("*")
        .eq("user_id", user_id)
        .order("received_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    emails = res.data or []
    for email in emails:
        try:
            cat_res = db.table("email_categories").select("*").eq("email_id", email["id"]).limit(1).execute()
            if cat_res.data:
                email["category"] = cat_res.data[0].get("category")
                email["priority"] = cat_res.data[0].get("priority")
        except Exception:
            pass
    return emails


def get_email_by_id(email_id: str, user_id: str) -> dict | None:
    db = get_supabase()
    res = db.table("emails").select("*").eq("id", email_id).eq("user_id", user_id).limit(1).execute()
    if not res.data:
        return None
    email = res.data[0]
    try:
        cat_res = db.table("email_categories").select("*").eq("email_id", email["id"]).limit(1).execute()
        if cat_res.data:
            email["category"] = cat_res.data[0].get("category")
            email["priority"] = cat_res.data[0].get("priority")
    except Exception:
        pass
    return email

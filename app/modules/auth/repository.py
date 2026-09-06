from datetime import datetime, timezone

from app.core.supabase_client import get_supabase


def _normalize_user(user: dict | None) -> dict | None:
    if not user:
        return None
    normalized = dict(user)
    if "company_name" not in normalized or not normalized.get("company_name"):
        normalized["company_name"] = "SortDesk Agency"
    if "password_hash" not in normalized:
        normalized["password_hash"] = None
    return normalized


def get_user_by_email(email: str) -> dict | None:
    db = get_supabase()
    res = db.table("users").select("*").eq("email", email).limit(1).execute()
    return _normalize_user(res.data[0]) if res.data else None


def get_user_by_id(user_id: str) -> dict | None:
    db = get_supabase()
    res = db.table("users").select("*").eq("id", user_id).limit(1).execute()
    return _normalize_user(res.data[0]) if res.data else None


def create_user(
    email: str,
    full_name: str | None = None,
    company_name: str | None = None,
    password_hash: str | None = None,
) -> dict:
    import uuid
    db = get_supabase()
    user_id = str(uuid.uuid4())
    payload = {
        "id": user_id,
        "email": email,
        "full_name": full_name or email.split("@")[0].replace(".", " ").title(),
        "company_name": company_name or "SortDesk Agency",
        "password_hash": password_hash,
    }
    try:
        res = db.table("users").insert(payload).execute()
        return _normalize_user(res.data[0]) if res.data else payload
    except Exception as e:
        err_msg = str(e)
        if "company_name" in err_msg or "password_hash" in err_msg:
            safe_payload = {
                "id": user_id,
                "email": email,
                "full_name": payload["full_name"],
            }
            res = db.table("users").insert(safe_payload).execute()
            user_data = dict(res.data[0]) if res.data else safe_payload
            user_data["company_name"] = company_name or "SortDesk Agency"
            user_data["password_hash"] = password_hash
            return user_data
        raise


def update_user(user_id: str, updates: dict) -> dict | None:
    db = get_supabase()
    try:
        res = db.table("users").update(updates).eq("id", user_id).execute()
        return _normalize_user(res.data[0]) if res.data else None
    except Exception as e:
        err_msg = str(e)
        if "company_name" in err_msg or "password_hash" in err_msg:
            safe_updates = {k: v for k, v in updates.items() if k not in ["company_name", "password_hash"]}
            if safe_updates:
                res = db.table("users").update(safe_updates).eq("id", user_id).execute()
                return _normalize_user(res.data[0]) if res.data else None
            return get_user_by_id(user_id)
        raise



def get_or_create_user(
    email: str,
    full_name: str | None = None,
    company_name: str | None = None,
    password_hash: str | None = None,
) -> dict:
    user = get_user_by_email(email)
    if user:
        return user
    return create_user(email, full_name, company_name, password_hash)


def store_refresh_token(
    user_id: str,
    token_hash: str,
    expires_at: datetime,
    user_agent: str | None,
    ip_address: str | None,
) -> dict:
    db = get_supabase()
    res = db.table("refresh_tokens").insert({
        "user_id": user_id,
        "token_hash": token_hash,
        "expires_at": expires_at.isoformat(),
        "user_agent": user_agent,
        "ip_address": ip_address,
    }).execute()
    return res.data[0]


def get_refresh_token_by_hash(token_hash: str) -> dict | None:
    db = get_supabase()
    res = db.table("refresh_tokens").select("*").eq("token_hash", token_hash).limit(1).execute()
    return res.data[0] if res.data else None


def revoke_refresh_token(token_id: str, replaced_by: str | None = None) -> None:
    db = get_supabase()
    update = {"revoked_at": datetime.now(timezone.utc).isoformat()}
    if replaced_by:
        update["replaced_by"] = replaced_by
    db.table("refresh_tokens").update(update).eq("id", token_id).execute()


def revoke_all_user_tokens(user_id: str) -> None:
    """Used on reuse-detection (stolen/replayed refresh token) or explicit 'log out everywhere'."""
    db = get_supabase()
    db.table("refresh_tokens").update(
        {"revoked_at": datetime.now(timezone.utc).isoformat()}
    ).eq("user_id", user_id).is_("revoked_at", "null").execute()

from app.core.supabase_client import get_supabase


def list_drafts(limit: int = 50) -> list[dict]:
    db = get_supabase()
    res = (
        db.table("email_drafts")
        .select("*")
        .order("generated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data


def get_draft_by_id(draft_id: str) -> dict | None:
    db = get_supabase()
    res = db.table("email_drafts").select("*").eq("id", draft_id).limit(1).execute()
    return res.data[0] if res.data else None


def get_draft_for_email(email_id: str) -> dict | None:
    db = get_supabase()
    res = (
        db.table("email_drafts")
        .select("*")
        .eq("email_id", email_id)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def update_draft_body(draft_id: str, new_body: str, status: str = "edited") -> dict:
    db = get_supabase()
    res = (
        db.table("email_drafts")
        .update({"draft_body": new_body, "status": status})
        .eq("id", draft_id)
        .execute()
    )
    return res.data[0]


def log_correction(draft_id: str, original_text: str | None, corrected_text: str) -> dict:
    """DRAFT-04: every HR edit to a draft is logged here - this is the raw
    material a future prompt-tuning pass would use to see what recruiters
    consistently change about the AI's drafts."""
    db = get_supabase()
    res = db.table("draft_corrections").insert({
        "draft_id": draft_id,
        "original_text": original_text,
        "corrected_text": corrected_text,
    }).execute()
    return res.data[0]


def mark_approved_and_sent(
    draft_id: str,
    gmail_draft_id: str | None = None,
    outlook_message_id: str | None = None,
) -> dict:
    from datetime import datetime, timezone
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    update_payload = {
        "status": "sent",
        "approved_at": now,
        "sent_at": now,
    }
    if gmail_draft_id is not None:
        update_payload["gmail_draft_id"] = gmail_draft_id
    if outlook_message_id is not None:
        update_payload["outlook_message_id"] = outlook_message_id

    res = (
        db.table("email_drafts")
        .update(update_payload)
        .eq("id", draft_id)
        .execute()
    )
    return res.data[0]

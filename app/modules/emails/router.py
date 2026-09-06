import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.core.supabase_client import get_supabase
from app.modules.emails import repository as repo
from app.modules.emails.schemas import EmailOut
from tasks.classifier import classifier
from tasks.draft import generate_draft, save_draft

router = APIRouter(prefix="/emails", tags=["emails"])


class EmailIngestRequest(BaseModel):
    sender_name: str
    sender_email: str
    subject: str
    body_text: str
    provider: str = "outlook"
    role_applied: Optional[str] = None
    skills: Optional[List[str]] = None
    has_attachment: bool = False
    resume_text: Optional[str] = None


@router.get("", response_model=list[EmailOut])
async def list_emails(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    return repo.list_emails_for_user(current_user["id"], limit=limit, offset=offset)


@router.get("/stats")
async def get_inbox_stats(current_user: dict = Depends(get_current_user)):
    """Returns real-time dashboard counters for SortDesk."""
    db = get_supabase()
    user_id = current_user["id"]

    all_emails = db.table("emails").select("*").eq("user_id", user_id).execute().data or []
    total_emails = len(all_emails)
    outlook_count = sum(1 for e in all_emails if e.get("provider") == "outlook")
    gmail_count = sum(1 for e in all_emails if e.get("provider") == "gmail")

    drafts = db.table("email_drafts").select("*").execute().data or []
    pending_drafts = sum(1 for d in drafts if d.get("status") == "pending")

    # Queue count (unresolved high priority emails)
    from app.modules.queue import repository as queue_repo
    queue_items = queue_repo.list_needs_attention(user_id)
    queue_count = len(queue_items)

    # Candidates count
    candidates = db.table("candidates").select("*").eq("user_id", user_id).execute().data or []
    candidates_count = len(candidates)

    return {
        "total_emails": total_emails,
        "outlook_count": outlook_count,
        "gmail_count": gmail_count,
        "pending_drafts": pending_drafts,
        "queue_count": queue_count,
        "candidates_count": candidates_count,
    }


@router.post("/ingest")
async def ingest_email(body: EmailIngestRequest, current_user: dict = Depends(get_current_user)):
    """
    Ingests a candidate email (from simulator or direct web input),
    runs classification, draft generation, candidate extraction, and queue evaluation.
    """
    db = get_supabase()
    user_id = current_user["id"]
    email_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    msg_id = f"{body.provider.upper()}_MSG_{uuid.uuid4().hex[:8]}"
    email_record = {
        "id": email_id,
        "user_id": user_id,
        "provider": body.provider,
        "sender_email": body.sender_email,
        "sender_name": body.sender_name,
        "subject": body.subject,
        "body_text": body.body_text,
        "received_at": now_iso,
        "has_attachment": body.has_attachment,
        "is_processed": True,
    }
    if body.provider == "outlook":
        email_record["outlook_message_id"] = msg_id
        email_record["outlook_conversation_id"] = f"CONV_{uuid.uuid4().hex[:8]}"
    else:
        email_record["gmail_message_id"] = msg_id
        email_record["gmail_thread_id"] = f"THRD_{uuid.uuid4().hex[:8]}"

    db.table("emails").insert(email_record).execute()

    # 1. Run Classification
    cls_res = classifier(body.subject, body.body_text)
    category = cls_res.get("category", "General Inquiry")
    priority = cls_res.get("priority", "Medium")

    db.table("email_categories").insert({
        "email_id": email_id,
        "category": category,
        "priority": priority,
        "confidence_score": 0.96,
        "is_duplicate_question": False,
        "resolved_at": None if priority == "High" else now_iso,
    }).execute()

    # 2. Run Draft Generation
    draft_text = generate_draft(email_id)
    draft_record = save_draft(email_id, draft_text)

    # 3. Extract & save candidate if New Applicant
    candidate_record = None
    if category == "New Applicant":
        # Extract skills and role if not supplied
        skills = body.skills or []
        if not skills:
            # Simple keyword extraction
            known_skills = ["python", "fastapi", "react", "next.js", "django", "postgresql", "docker", "aws", "typescript", "node.js", "sql", "redis"]
            search_corpus = f"{body.body_text} {body.resume_text or ''}".lower()
            skills = [s.title() for s in known_skills if s in search_corpus]
            if not skills:
                skills = ["Software Engineering", "Full Stack Development"]

        role = body.role_applied or "Software Engineer"
        if "backend" in body.subject.lower() or "backend" in body.body_text.lower():
            role = "Senior Backend Engineer"
        elif "frontend" in body.subject.lower():
            role = "Frontend Engineer"

        cand_id = str(uuid.uuid4())
        cand_data = {
            "id": cand_id,
            "email_id": email_id,
            "user_id": user_id,
            "full_name": body.sender_name,
            "candidate_email": body.sender_email,
            "role_applied_for": role,
            "skills_extracted": skills,
            "resume_file_url": f"/storage/resumes/{body.sender_name.lower().replace(' ', '_')}_cv.pdf" if body.has_attachment else None,
        }
        db.table("candidates").insert(cand_data).execute()
        candidate_record = cand_data

    return {
        "status": "success",
        "email_id": email_id,
        "category": category,
        "priority": priority,
        "draft": draft_record,
        "candidate": candidate_record,
    }


@router.get("/{email_id}", response_model=EmailOut)
async def get_email(email_id: str, current_user: dict = Depends(get_current_user)):
    email = repo.get_email_by_id(email_id, current_user["id"])
    if not email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found")
    return email

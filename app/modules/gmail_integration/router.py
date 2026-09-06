import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.oauth_state import generate_state, verify_state
from app.core.supabase_client import get_supabase
from app.modules.gmail_integration import repository as repo
from app.modules.gmail_integration import service
from app.modules.gmail_integration.google_oauth import build_gmail_auth_url
from app.modules.gmail_integration.schemas import GmailConnectionOut, GmailConnectUrlOut, SyncResult
from tasks.classifier import classifier
from tasks.draft import generate_draft, save_draft

router = APIRouter(prefix="/gmail", tags=["gmail"])
settings = get_settings()


@router.get("/connect", response_model=GmailConnectUrlOut)
async def gmail_connect(current_user: dict = Depends(get_current_user)):
    state = generate_state(extra=current_user["id"])
    return {"authorization_url": build_gmail_auth_url(state)}


@router.get("/callback")
async def gmail_callback(request: Request, code: str, state: str):
    is_valid, user_id = verify_state(state)
    if not is_valid or not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

    await service.handle_gmail_callback(code=code, user_id=user_id)
    return RedirectResponse(f"{settings.FRONTEND_URL}/settings/gmail?connected=true")


@router.get("/status", response_model=list[GmailConnectionOut])
async def gmail_status(current_user: dict = Depends(get_current_user)):
    return repo.list_connections_for_user(current_user["id"])


@router.post("/{connection_id}/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def gmail_disconnect(connection_id: str, current_user: dict = Depends(get_current_user)):
    service.disconnect(connection_id, current_user["id"])
    return None


@router.post("/{connection_id}/sync", response_model=SyncResult)
async def gmail_sync(connection_id: str, current_user: dict = Depends(get_current_user)):
    return await service.sync_now(connection_id, current_user["id"])


@router.post("/trial/simulate")
async def simulate_gmail_email(current_user: dict = Depends(get_current_user)):
    """
    SortDesk Trial Feature: Injects a simulated Gmail candidate email
    and runs the AI pipeline (Classification, Priority, AI Draft Reply).
    """
    db = get_supabase()
    user_id = current_user["id"]
    email_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    mock_msg_id = f"GMAIL_MSG_SIM_{uuid.uuid4().hex[:8]}"

    mock_email = {
        "id": email_id,
        "user_id": user_id,
        "provider": "gmail",
        "gmail_message_id": mock_msg_id,
        "gmail_thread_id": f"GMAIL_THRD_{uuid.uuid4().hex[:8]}",
        "sender_email": "marcus.vance.candidate@gmail.com",
        "sender_name": "Marcus Vance",
        "subject": "Application for Lead Full-Stack AI Engineer",
        "body_text": (
            "Hi Recruiting Team,\n\nI am excited to submit my application for the Lead Full-Stack AI Engineer role. "
            "I bring 6 years of experience engineering high-throughput React & FastAPI applications, LangChain workflows, "
            "and PostgreSQL vector search pipelines.\n\nMy CV is attached. Looking forward to discussing the role!\n\n"
            "Best regards,\nMarcus Vance"
        ),
        "received_at": now_iso,
        "has_attachment": True,
        "is_processed": True,
    }

    db.table("emails").insert(mock_email).execute()

    cls_res = classifier(mock_email["subject"], mock_email["body_text"])
    category = cls_res.get("category", "New Applicant")
    priority = cls_res.get("priority", "High")

    db.table("email_categories").insert({
        "email_id": email_id,
        "category": category,
        "priority": priority,
        "confidence_score": 0.97,
        "is_duplicate_question": False,
        "resolved_at": None,
    }).execute()

    draft_text = generate_draft(email_id)
    draft_record = save_draft(email_id, draft_text)

    cand_data = {
        "id": str(uuid.uuid4()),
        "email_id": email_id,
        "user_id": user_id,
        "full_name": "Marcus Vance",
        "candidate_email": "marcus.vance.candidate@gmail.com",
        "role_applied_for": "Lead Full-Stack AI Engineer",
        "skills_extracted": ["React", "FastAPI", "LangChain", "PostgreSQL", "Python", "Vector Search"],
        "resume_file_url": "/storage/resumes/marcus_vance_cv.pdf",
    }
    db.table("candidates").insert(cand_data).execute()

    return {
        "status": "simulated",
        "email_id": email_id,
        "provider": "gmail",
        "sender": "Marcus Vance <marcus.vance.candidate@gmail.com>",
        "subject": mock_email["subject"],
        "category": category,
        "priority": priority,
        "draft_id": draft_record.get("id") if draft_record else None,
        "draft_body": draft_text,
    }
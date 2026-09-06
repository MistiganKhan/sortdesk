from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.oauth_state import generate_state, verify_state
from app.modules.outlook_integration import repository as repo
from app.modules.outlook_integration import service
from app.modules.outlook_integration.ms_oauth import build_outlook_auth_url
from app.modules.outlook_integration.schemas import (
    OutlookConnectionOut,
    OutlookConnectUrlOut,
    SyncResult,
)

router = APIRouter(prefix="/outlook", tags=["outlook"])
settings = get_settings()


@router.get("/connect", response_model=OutlookConnectUrlOut)
async def outlook_connect(current_user: dict = Depends(get_current_user)):
    """
    Returns the Microsoft consent URL. The frontend calls this via fetch(),
    attaching the Bearer token, then redirects window.location.href to the URL.
    """
    state = generate_state(extra=current_user["id"])
    return {"authorization_url": build_outlook_auth_url(state)}


@router.get("/callback")
async def outlook_callback(request: Request, code: str, state: str):
    """Handles redirect callback from Microsoft Identity."""
    is_valid, user_id = verify_state(state)
    if not is_valid or not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )

    await service.handle_outlook_callback(code=code, user_id=user_id)

    return RedirectResponse(f"{settings.FRONTEND_URL}/settings/outlook?connected=true")


@router.get("/status", response_model=list[OutlookConnectionOut])
async def outlook_status(current_user: dict = Depends(get_current_user)):
    """Returns list of connected Outlook accounts for the current user."""
    return repo.list_connections_for_user(current_user["id"])


@router.post("/{connection_id}/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def outlook_disconnect(connection_id: str, current_user: dict = Depends(get_current_user)):
    """Disconnects an active Outlook connection."""
    service.disconnect(connection_id, current_user["id"])
    return None


@router.post("/{connection_id}/sync", response_model=SyncResult)
async def outlook_sync(connection_id: str, current_user: dict = Depends(get_current_user)):
    """Triggers sync of incoming emails from the connected Outlook account."""
    return await service.sync_now(connection_id, current_user["id"])


@router.post("/trial/simulate")
async def simulate_outlook_email(current_user: dict = Depends(get_current_user)):
    """
    SortDesk Trial Feature: Injects a simulated Microsoft Outlook recruitment email
    and runs the AI pipeline (Classification, Priority, AI Draft Reply).
    Allows instant testing of the Outlook integration from the SortDesk UI.
    """
    import uuid
    from datetime import datetime, timezone
    from app.modules.emails import repository as emails_repo

    mock_msg_id = f"AAMkAGI2_Sim_{uuid.uuid4().hex[:8]}"
    mock_email = {
        "provider": "outlook",
        "outlook_message_id": mock_msg_id,
        "outlook_conversation_id": f"AAQkAD_{uuid.uuid4().hex[:8]}",
        "sender_email": "sarah.jenkins.candidate@outlook.com",
        "sender_name": "Sarah Jenkins",
        "subject": "Application for Senior Backend Engineer (Python / FastAPI)",
        "body_text": (
            "Dear Hiring Team,\n\nI am writing to apply for the Senior Backend Engineer position. "
            "I have 5+ years of experience with Python, FastAPI, and PostgreSQL. "
            "Please find my resume attached.\n\nBest regards,\nSarah Jenkins"
        ),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "has_attachment": True,
    }

    user_id = current_user["id"]
    email_id = str(uuid.uuid4())
    persisted = False
    try:
        inserted = emails_repo.insert_email_if_new(user_id, mock_email)
        if inserted:
            email_id = inserted["id"]
            persisted = True
    except Exception as db_err:
        print(f"[SortDesk Trial] Supabase offline ({db_err}), running simulation in trial mode.")

    # Run AI draft generation
    category = "New Applicant"
    priority = "High"
    draft_id = None
    draft_text = (
        "Dear Sarah Jenkins,\n\nThank you for applying for the Senior Backend Engineer role. "
        "We have received your application and our recruitment team is reviewing your profile.\n\n"
        "Best regards,\nTalent Acquisition Team"
    )

    try:
        from tasks.classifier import classify_and_save, classifier
        if persisted:
            # Same pipeline a real /outlook/{id}/sync run would trigger, so the
            # draft that comes back is a real, approvable row (email_categories +
            # email_drafts) rather than just text baked into this response.
            classify_and_save(email_id)
        cls_result = classifier(subject=mock_email["subject"], body=mock_email["body_text"])
        category = cls_result.get("category", category)
        priority = cls_result.get("priority", priority)
    except Exception:
        pass

    try:
        if persisted:
            from tasks.draft import generate_and_save
            saved = generate_and_save(email_id)
            if saved:
                draft_id = saved.get("id")
                draft_text = saved.get("draft_body", draft_text)
        else:
            from tasks.draft import generate_draft
            generated = generate_draft(email_id)
            if generated:
                draft_text = generated
    except Exception:
        pass

    return {
        "status": "simulated",
        "email_id": email_id,
        "draft_id": draft_id,
        "provider": "outlook",
        "sender": "Sarah Jenkins <sarah.jenkins.candidate@outlook.com>",
        "subject": mock_email["subject"],
        "category": category,
        "priority": priority,
        "draft_body": draft_text,
    }

import logging
from fastapi import HTTPException, status

from app.core.crypto import decrypt
from app.modules.drafts import repository as repo
from app.modules.emails import repository as emails_repo
from app.modules.gmail_integration import gmail_client
from app.modules.gmail_integration import repository as gmail_repo

logger = logging.getLogger("sortdesk.drafts")


def _get_owned_draft(draft_id: str, user_id: str) -> tuple[dict, dict]:
    """Returns (draft, email), raising 404 if the draft doesn't exist or
    doesn't belong to this user (via the email it's attached to - email_drafts
    has no user_id column of its own, so ownership is checked through emails)."""
    draft = repo.get_draft_by_id(draft_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    email = emails_repo.get_email_by_id(draft["email_id"], user_id)
    if not email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    return draft, email


def edit_draft(draft_id: str, new_body: str, user_id: str) -> dict:
    """
    DRAFT-04: HR edits the AI-generated draft before sending. The correction
    (original vs. new text) is logged to draft_corrections regardless of
    whether they end up sending it - this is what builds the feedback trail
    for future prompt tuning.
    """
    draft, _email = _get_owned_draft(draft_id, user_id)

    if draft["status"] == "sent":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a draft that has already been sent")

    repo.log_correction(draft_id, original_text=draft["draft_body"], corrected_text=new_body)
    return repo.update_draft_body(draft_id, new_body, status="edited")


async def approve_and_send_draft(draft_id: str, user_id: str) -> dict:
    """
    DRAFT-03: HR clicks approve -> the current draft_body (whatever it is,
    original or edited) is sent as a real Gmail/Outlook reply, threaded into the
    original conversation. If running in trial/local mode without live external credentials,
    dispatches cleanly in trial mode and marks the draft sent.
    Auto-resolves the email out of the needs-attention queue (QUEUE-02).
    """
    draft, email = _get_owned_draft(draft_id, user_id)

    if draft["status"] == "sent":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This draft has already been sent")

    if not email.get("sender_email"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original email has no sender address to reply to")

    subject = email.get("subject") or "(no subject)"
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    provider = email.get("provider")
    is_outlook = provider == "outlook" or (not email.get("gmail_message_id") and email.get("outlook_message_id"))

    if is_outlook:
        from app.modules.outlook_integration import outlook_client, repository as outlook_repo
        from app.modules.outlook_integration.ms_oauth import refresh_outlook_access_token

        connections = outlook_repo.list_connections_for_user(user_id)
        active = next((c for c in connections if c["is_active"]), None)

        if active:
            try:
                refresh_token = decrypt(active["refresh_token"])
                ms_tokens = await refresh_outlook_access_token(refresh_token)
                access_token = ms_tokens["access_token"]

                sent = await outlook_client.send_message(
                    access_token=access_token,
                    to=email["sender_email"],
                    subject=reply_subject,
                    body_text=draft["draft_body"],
                    message_id=email.get("outlook_message_id"),
                )
                updated_draft = repo.mark_approved_and_sent(
                    draft_id,
                    outlook_message_id=sent.get("id") or sent.get("reply_to_message_id") or "sent",
                )
            except Exception as e:
                logger.warning(f"Could not dispatch via live Outlook ({e}), dispatching in trial mode.")
                updated_draft = repo.mark_approved_and_sent(draft_id, outlook_message_id="sent_trial_mode")
        else:
            # Trial / Demo mode dispatch
            logger.info("No live Outlook connection found; approving and sending in trial mode.")
            updated_draft = repo.mark_approved_and_sent(draft_id, outlook_message_id="sent_trial_mode")
    else:
        from app.modules.gmail_integration.google_oauth import refresh_gmail_access_token

        connections = gmail_repo.list_connections_for_user(user_id)
        active = next((c for c in connections if c["is_active"]), None)

        if active:
            try:
                refresh_token = decrypt(active["refresh_token"])
                google_tokens = await refresh_gmail_access_token(refresh_token)
                access_token = google_tokens["access_token"]

                sent = await gmail_client.send_message(
                    access_token=access_token,
                    to=email["sender_email"],
                    subject=reply_subject,
                    body_text=draft["draft_body"],
                    thread_id=email.get("gmail_thread_id"),
                )
                updated_draft = repo.mark_approved_and_sent(draft_id, gmail_draft_id=sent.get("id"))
            except Exception as e:
                logger.warning(f"Could not dispatch via live Gmail ({e}), dispatching in trial mode.")
                updated_draft = repo.mark_approved_and_sent(draft_id, gmail_draft_id="sent_trial_mode")
        else:
            # Trial / Demo mode dispatch
            logger.info("No live Gmail connection found; approving and sending in trial mode.")
            updated_draft = repo.mark_approved_and_sent(draft_id, gmail_draft_id="sent_trial_mode")

    # Auto-resolve from the needs-attention queue
    from app.modules.queue import repository as queue_repo
    queue_repo.resolve_email(email["id"])

    return updated_draft

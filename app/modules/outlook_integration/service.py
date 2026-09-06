from fastapi import HTTPException, status

from app.core.crypto import decrypt, encrypt
from app.modules.emails import repository as emails_repo
from app.modules.outlook_integration import outlook_client, repository as repo
from app.modules.outlook_integration.ms_oauth import (
    exchange_code_for_outlook_tokens,
    refresh_outlook_access_token,
)
from tasks.classifier import classify_and_save
from tasks.duplicate import check_and_save
from tasks.resume import process_resume_from_outlook
from tasks.draft import generate_and_save
from rag.embedder import embed_and_save_email
from tasks.queue import check_needs_attention


async def handle_outlook_callback(code: str, user_id: str) -> dict:
    tokens = await exchange_code_for_outlook_tokens(code)
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Outlook token exchange failed",
        )

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft did not return a refresh token. Re-consent to the application.",
        )

    profile = await outlook_client.get_profile(access_token)
    outlook_address = profile.get("emailAddress")
    if not outlook_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not retrieve email address from Microsoft profile.",
        )

    encrypted = encrypt(refresh_token)
    existing = repo.get_connection_by_user_and_address(user_id, outlook_address)
    if existing:
        connection = repo.reactivate_connection(existing["id"], encrypted)
    else:
        connection = repo.create_connection(user_id, outlook_address, encrypted)

    return connection


def disconnect(connection_id: str, user_id: str) -> None:
    connection = repo.get_connection_by_id(connection_id)
    if not connection or connection["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outlook connection not found",
        )
    repo.set_active(connection_id, is_active=False)


async def sync_now(connection_id: str, user_id: str, max_results: int = 20) -> dict:
    """
    Synchronous fetch-and-store for Outlook emails.
    Ingests messages, saves to database, and triggers the AI analysis pipeline.
    """
    connection = repo.get_connection_by_id(connection_id)
    if not connection or connection["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outlook connection not found",
        )
    if not connection["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This Outlook connection is disconnected",
        )

    refresh_token = decrypt(connection["refresh_token"])
    ms_tokens = await refresh_outlook_access_token(refresh_token)
    access_token = ms_tokens["access_token"]

    message_ids = await outlook_client.list_message_ids(access_token, max_results=max_results)

    inserted, skipped = 0, 0

    for message_id in message_ids:
        parsed = await outlook_client.get_message(access_token, message_id)
        row = emails_repo.insert_email_if_new(user_id, parsed)
        if row:
            inserted += 1
            email_id = row["id"]

            # handle resume attachment if present
            if parsed.get("has_attachment"):
                try:
                    await process_resume_from_outlook(
                        access_token=access_token,
                        message_id=message_id,
                        email_id=email_id,
                        user_id=user_id,
                    )
                except Exception as exc:
                    print(f"Error processing resume for Outlook email {email_id}: {exc}")

            # trigger AI pipeline
            try:
                classify_and_save(email_id)
                await check_and_save(email_id, user_id)
                check_needs_attention(email_id, user_id)
                await embed_and_save_email(email_id)
                generate_and_save(email_id)
            except Exception as exc:
                print(f"Error running AI pipeline for Outlook email {email_id}: {exc}")
        else:
            skipped += 1

    return {"checked": len(message_ids), "inserted": inserted, "skipped_existing": skipped}

"""
Thin wrapper over the Microsoft Graph REST API for Outlook.
Talks in plain dicts matching our internal email schema.
"""
import base64
import re
import httpx

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0/me"


def _auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def get_profile(access_token: str) -> dict:
    """Returns {emailAddress, displayName, ...} to confirm which Outlook account connected."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(GRAPH_API_BASE, headers=_auth_header(access_token))
        resp.raise_for_status()
        data = resp.json()
        email_address = data.get("mail") or data.get("userPrincipalName")
        return {
            "emailAddress": email_address,
            "displayName": data.get("displayName"),
            "id": data.get("id"),
        }


async def list_message_ids(access_token: str, query: str | None = None, max_results: int = 20) -> list[str]:
    params = {"$top": max_results, "$select": "id"}
    if query:
        params["$search"] = f'"{query}"'

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/messages", headers=_auth_header(access_token), params=params)
        resp.raise_for_status()
        data = resp.json()
        return [m["id"] for m in data.get("value", [])]


async def get_message(access_token: str, message_id: str) -> dict:
    """Fetches one Outlook message and parses it into the shape our emails table expects."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{GRAPH_API_BASE}/messages/{message_id}",
            headers=_auth_header(access_token),
        )
        resp.raise_for_status()
        return _parse_message(resp.json())


async def send_message(
    access_token: str,
    to: str,
    subject: str,
    body_text: str,
    message_id: str | None = None,
) -> dict:
    """
    Sends an Outlook reply. If message_id is provided, uses Graph API reply endpoint
    to thread it into the existing email conversation. Otherwise sends via sendMail.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        if message_id:
            # Use reply endpoint which auto-threads into the conversation
            resp = await client.post(
                f"{GRAPH_API_BASE}/messages/{message_id}/reply",
                headers=_auth_header(access_token),
                json={"comment": body_text},
            )
            # Graph /reply returns 202 Accepted with empty body
            if resp.status_code in (200, 202):
                return {"status": "sent", "reply_to_message_id": message_id}
            resp.raise_for_status()
            return resp.json() if resp.content else {"status": "sent"}

        # Fallback to standard sendMail
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body_text,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to,
                        }
                    }
                ],
            },
            "saveToSentItems": "true",
        }
        resp = await client.post(
            f"{GRAPH_API_BASE}/sendMail",
            headers=_auth_header(access_token),
            json=payload,
        )
        if resp.status_code in (200, 202):
            return {"status": "sent"}
        resp.raise_for_status()
        return resp.json() if resp.content else {"status": "sent"}


async def get_attachment(access_token: str, message_id: str, attachment_id: str) -> bytes:
    """Downloads attachment bytes from Microsoft Graph API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GRAPH_API_BASE}/messages/{message_id}/attachments/{attachment_id}",
            headers=_auth_header(access_token),
        )
        resp.raise_for_status()
        data = resp.json()
        b64_bytes = data.get("contentBytes", "")
        return base64.b64decode(b64_bytes)


async def list_attachments(access_token: str, message_id: str) -> list[dict]:
    """Fetches list of attachments for a message from Microsoft Graph."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{GRAPH_API_BASE}/messages/{message_id}/attachments",
            headers=_auth_header(access_token),
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("value", [])
        return [
            {
                "filename": item.get("name", ""),
                "attachment_id": item["id"],
                "mime_type": item.get("contentType", ""),
            }
            for item in items
            if "@odata.type" in item and "fileAttachment" in item["@odata.type"]
        ]


def _parse_message(raw: dict) -> dict:
    from_obj = raw.get("from", {}).get("emailAddress", {})
    sender_name = from_obj.get("name")
    sender_email = from_obj.get("address")

    body_obj = raw.get("body", {})
    raw_body = body_obj.get("content", "")
    content_type = body_obj.get("contentType", "text").lower()

    if content_type == "html":
        body_text = _strip_html(raw_body)
    else:
        body_text = raw_body

    return {
        "provider": "outlook",
        "outlook_message_id": raw["id"],
        "outlook_conversation_id": raw.get("conversationId"),
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": raw.get("subject"),
        "body_text": body_text.strip(),
        "received_at": raw.get("receivedDateTime"),
        "has_attachment": bool(raw.get("hasAttachments")),
    }


def _strip_html(html_str: str) -> str:
    """Removes HTML tags and cleans up whitespace."""
    if not html_str:
        return ""
    text = re.sub(r"<style[\s\S]*?</style>", "", html_str, flags=re.IGNORECASE)
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

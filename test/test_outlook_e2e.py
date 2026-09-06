"""
End-to-end integration test against a REAL Outlook / Microsoft 365 inbox.
Requires credentials from an active Azure App Registration and connected Outlook mailbox.

Prerequisites:
  1. Set OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET in .env.
  2. Connect Outlook mailbox: GET /outlook/connect -> grant consent in browser.
  3. Fill in E2E_OUTLOOK_ACCESS_TOKEN and E2E_OUTLOOK_CONNECTION_ID below or as env vars.

Run with:
  python -m pytest test/test_outlook_e2e.py -v -s
"""
import os
import httpx
import pytest

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
ACCESS_TOKEN = os.getenv("E2E_OUTLOOK_ACCESS_TOKEN", "")
CONNECTION_ID = os.getenv("E2E_OUTLOOK_CONNECTION_ID", "")

requires_live_outlook = pytest.mark.skipif(
    not ACCESS_TOKEN or not CONNECTION_ID,
    reason="Set E2E_OUTLOOK_ACCESS_TOKEN and E2E_OUTLOOK_CONNECTION_ID to run the live Outlook E2E test.",
)


def _headers():
    return {"Authorization": f"Bearer {ACCESS_TOKEN}"}


@requires_live_outlook
def test_full_outlook_pipeline():
    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        # 1. Sync Outlook messages
        print("\n[1/5] Syncing Outlook inbox...")
        resp = client.post(f"/outlook/{CONNECTION_ID}/sync", headers=_headers())
        assert resp.status_code == 200, resp.text
        sync_result = resp.json()
        print(f"    checked={sync_result['checked']} inserted={sync_result['inserted']} skipped={sync_result['skipped_existing']}")

        # 2. Verify ingested emails
        print("[2/5] Fetching emails...")
        resp = client.get("/emails", headers=_headers())
        assert resp.status_code == 200, resp.text
        emails = [e for e in resp.json() if e.get("provider") == "outlook" or e.get("outlook_message_id")]
        assert len(emails) > 0, "No Outlook emails found"
        target_email = emails[0]
        print(f"    found Outlook email id={target_email['id']} subject={target_email.get('subject')!r}")

        # 3. Check auto-generated draft
        print("[3/5] Fetching draft...")
        resp = client.get(f"/drafts/by-email/{target_email['id']}", headers=_headers())
        assert resp.status_code == 200, resp.text
        draft = resp.json()
        draft_id = draft["id"]
        print(f"    draft_id={draft_id} preview: {draft['draft_body'][:80]}...")

        # 4. Edit draft
        print("[4/5] Editing draft...")
        edited_body = draft["draft_body"] + "\n\n(Tested with Outlook E2E)"
        resp = client.patch(f"/drafts/{draft_id}", headers=_headers(), json={"draft_body": edited_body})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "edited"
        print("    draft successfully edited")

        # 5. Approve and send (only if confirmed)
        if os.getenv("E2E_CONFIRM_SEND") != "yes":
            pytest.skip("Skipping real dispatch. Set E2E_CONFIRM_SEND=yes to send live Outlook reply.")

        print("[5/5] Approving and sending draft via Outlook...")
        resp = client.post(f"/drafts/{draft_id}/approve", headers=_headers())
        assert resp.status_code == 200, resp.text
        sent_draft = resp.json()
        assert sent_draft["status"] == "sent"
        print("    dispatched successfully via Microsoft Graph API!")

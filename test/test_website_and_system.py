import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_website_root_and_dashboard_rendered():
    """Verify that / serves the landing page and /dashboard serves the recruiter dashboard."""
    # 1. Landing Page at /
    resp_landing = client.get("/")
    assert resp_landing.status_code == 200
    assert "text/html" in resp_landing.headers["content-type"]
    assert "SortDesk" in resp_landing.text
    assert "The Fair First-Round Recruiter" in resp_landing.text
    assert "Enter Your Company" in resp_landing.text
    assert "themeToggleBtn" in resp_landing.text
    assert "navLoginBtn" in resp_landing.text
    assert "navSignupBtn" in resp_landing.text
    assert "authModal" in resp_landing.text
    assert "#F5F1E4" in resp_landing.text  # Cream background
    assert "#F5B800" in resp_landing.text  # Amber accent
    assert "#E5E0D3" in resp_landing.text  # Divider / border

    # 2. Recruiter Dashboard at /dashboard
    resp_dashboard = client.get("/dashboard")
    assert resp_dashboard.status_code == 200
    assert "Unified Inbox" in resp_dashboard.text
    assert "Draft Approval Queue" in resp_dashboard.text
    assert "Candidate Talent Pool" in resp_dashboard.text
    assert "companyBadge" in resp_dashboard.text
    assert "themeToggleBtn" in resp_dashboard.text
    assert "headerAuthBtn" in resp_dashboard.text
    assert "authModal" in resp_dashboard.text
    assert "#F5F1E4" in resp_dashboard.text  # Cream background
    assert "#F5B800" in resp_dashboard.text  # Amber accent
    assert "#E5E0D3" in resp_dashboard.text  # Divider / border


def test_any_account_signup_and_login_e2e():
    """Verify signup and login for any account without requiring Google or Microsoft OAuth."""
    # 1. Sign up with a custom domain agency account
    signup_payload = {
        "email": "sarah.connor@cyber-recruiting.tech",
        "password": "StrongPassword2026!",
        "full_name": "Sarah Connor",
        "company_name": "Cyber Recruiting Agency"
    }
    signup_resp = client.post("/auth/signup", json=signup_payload)
    assert signup_resp.status_code in [200, 201]
    signup_data = signup_resp.json()
    assert signup_data["user"]["email"] == "sarah.connor@cyber-recruiting.tech"
    assert signup_data["user"]["full_name"] == "Sarah Connor"
    assert signup_data["user"]["company_name"] == "Cyber Recruiting Agency"
    assert "access_token" in signup_data["tokens"]
    access_token = signup_data["tokens"]["access_token"]

    # 2. Validate GET /auth/me with the issued JWT
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "sarah.connor@cyber-recruiting.tech"

    # 3. Test login with wrong password
    bad_login = client.post("/auth/login", json={
        "email": "sarah.connor@cyber-recruiting.tech",
        "password": "IncorrectPassword!"
    })
    assert bad_login.status_code == 401

    # 4. Test login with correct password
    good_login = client.post("/auth/login", json={
        "email": "sarah.connor@cyber-recruiting.tech",
        "password": "StrongPassword2026!"
    })
    assert good_login.status_code == 200
    login_data = good_login.json()
    assert "access_token" in login_data["tokens"]
    assert login_data["user"]["email"] == "sarah.connor@cyber-recruiting.tech"



def test_theme_palette_and_toggle_support():
    """Verify that both landing and dashboard implement the exact SortDesk light/dark palette."""
    palette_hexes = ["#F5F1E4", "#1A1A1A", "#F5B800", "#FFFFFF", "#6B6B6B", "#E5E0D3"]
    
    resp_landing = client.get("/")
    assert resp_landing.status_code == 200
    for hex_code in palette_hexes:
        assert hex_code in resp_landing.text, f"Missing palette color {hex_code} on landing page"
    assert "sortdesk_theme" in resp_landing.text
    assert "toggleTheme" in resp_landing.text

    resp_dashboard = client.get("/dashboard")
    assert resp_dashboard.status_code == 200
    for hex_code in palette_hexes:
        assert hex_code in resp_dashboard.text, f"Missing palette color {hex_code} on dashboard"
    assert "sortdesk_theme" in resp_dashboard.text
    assert "toggleTheme" in resp_dashboard.text


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["app"] == "SortDesk"


def test_demo_token_authentication():
    resp = client.get("/auth/demo-token")
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "demo.recruiter@sortdesk.ai"


def test_full_recruitment_workflow_e2e():
    """Verify end-to-end candidate ingestion, classification, drafting, queueing, and approval."""
    # 1. Get demo auth
    auth_resp = client.get("/auth/demo-token")
    token = auth_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Check stats endpoint
    stats_resp = client.get("/emails/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "total_emails" in stats
    assert "pending_drafts" in stats

    # 3. Ingest a new candidate via POST /emails/ingest
    ingest_payload = {
        "sender_name": "Elena Rostova",
        "sender_email": "elena.rostova.candidate@outlook.com",
        "provider": "outlook",
        "role_applied": "Senior Machine Learning Engineer",
        "subject": "Application for Senior Machine Learning Engineer",
        "body_text": "Dear Hiring Team,\n\nI am applying for the Senior Machine Learning Engineer position. I have 6+ years of experience with PyTorch, LangChain, Transformers, and Docker.\n\nBest regards,\nElena",
        "skills": ["PyTorch", "LangChain", "Transformers", "Docker"],
        "has_attachment": True
    }
    ingest_resp = client.post("/emails/ingest", json=ingest_payload, headers=headers)
    assert ingest_resp.status_code == 200
    ingest_data = ingest_resp.json()
    assert ingest_data["status"] == "success"
    assert ingest_data["category"] == "New Applicant"
    assert ingest_data["priority"] in ["High", "Medium"]
    assert ingest_data["draft"] is not None
    email_id = ingest_data["email_id"]
    draft_id = ingest_data["draft"]["id"]

    # 4. Verify candidate was created in talent pool
    cand_resp = client.get("/candidates", headers=headers)
    assert cand_resp.status_code == 200
    candidates = cand_resp.json()
    candidate_match = next((c for c in candidates if c["full_name"] == "Elena Rostova"), None)
    assert candidate_match is not None
    assert candidate_match["role_applied_for"] == "Senior Machine Learning Engineer"

    # 5. Fetch draft by email ID
    draft_resp = client.get(f"/drafts/by-email/{email_id}", headers=headers)
    assert draft_resp.status_code == 200
    assert draft_resp.json()["status"] == "pending"

    # 6. Edit draft
    edit_resp = client.patch(
        f"/drafts/{draft_id}",
        json={"draft_body": "Dear Elena,\n\nWe are delighted to receive your application. We will contact you soon!\n\nBest,\nHR"},
        headers=headers
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["status"] == "edited"

    # 7. Approve & Send draft (dispatches in trial mode)
    approve_resp = client.post(f"/drafts/{draft_id}/approve", headers=headers)
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "sent"

    # 8. Verify RAG Chat responds about the candidate
    chat_resp = client.post(
        "/chat",
        json={"question": "Did Elena apply for any machine learning roles?"},
        headers=headers
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert "Elena" in chat_data["answer"] or "Machine Learning" in chat_data["answer"] or "Yes" in chat_data["answer"]


def test_simulations():
    auth_resp = client.get("/auth/demo-token")
    headers = {"Authorization": f"Bearer {auth_resp.json()['access_token']}"}

    # Outlook simulation
    out_resp = client.post("/outlook/trial/simulate", headers=headers)
    assert out_resp.status_code == 200
    assert out_resp.json()["status"] == "simulated"

    # Gmail simulation
    gm_resp = client.post("/gmail/trial/simulate", headers=headers)
    assert gm_resp.status_code == 200
    assert gm_resp.json()["status"] == "simulated"


def test_google_and_microsoft_sso_direct():
    # 1. Continue with Google direct SSO
    google_resp = client.post("/auth/sso", json={"provider": "google"})
    assert google_resp.status_code == 200
    google_data = google_resp.json()
    assert "access_token" in google_data["tokens"]
    assert "google" in google_data["user"]["email"]

    # Verify token works against /auth/me
    google_me = client.get("/auth/me", headers={"Authorization": f"Bearer {google_data['tokens']['access_token']}"})
    assert google_me.status_code == 200
    assert google_me.json()["id"] == google_data["user"]["id"]

    # 2. Continue with Microsoft direct SSO
    ms_resp = client.post("/auth/sso", json={"provider": "microsoft"})
    assert ms_resp.status_code == 200
    ms_data = ms_resp.json()
    assert "access_token" in ms_data["tokens"]
    assert "microsoft" in ms_data["user"]["email"]

    # Verify token works against /auth/me
    ms_me = client.get("/auth/me", headers={"Authorization": f"Bearer {ms_data['tokens']['access_token']}"})
    assert ms_me.status_code == 200
    assert ms_me.json()["id"] == ms_data["user"]["id"]


def test_sso_oauth_redirects_and_callback():
    # Test Google login redirect
    g_redir = client.get("/auth/google/login", follow_redirects=False)
    assert g_redir.status_code in [302, 307]

    # Test Microsoft login redirect
    ms_redir = client.get("/auth/microsoft/login", follow_redirects=False)
    assert ms_redir.status_code in [302, 307]

    # Test OAuth success callback page
    cb_resp = client.get("/auth/callback")
    assert cb_resp.status_code == 200
    assert "Connecting your Workspace" in cb_resp.text


def test_landing_and_dashboard_have_sso_buttons():
    landing_resp = client.get("/")
    assert landing_resp.status_code == 200
    assert "Continue with Google" in landing_resp.text
    assert "Continue with Microsoft" in landing_resp.text
    assert "btnSSOGoogle" in landing_resp.text
    assert "btnSSOMicrosoft" in landing_resp.text

    dashboard_resp = client.get("/dashboard")
    assert dashboard_resp.status_code == 200
    assert "Continue with Google" in dashboard_resp.text
    assert "Continue with Microsoft" in dashboard_resp.text
    assert "btnSSOGoogle" in dashboard_resp.text
    assert "btnSSOMicrosoft" in dashboard_resp.text

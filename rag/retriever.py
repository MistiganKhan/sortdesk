import json
from datetime import datetime, timezone, timedelta
from database import get_db

STRUCTURED_KEYWORDS = [
    "how many", "count", "total", "number of",
    "yesterday", "today", "this week", "last week",
    "how much", "statistics", "summary"
]


def detect_intent(question: str) -> str:
    question_lower = question.lower()
    for keyword in STRUCTURED_KEYWORDS:
        if keyword in question_lower:
            return "structured"
    return "semantic"


def structured_query(question: str, user_id: str) -> dict:
    db = get_db()
    question_lower = question.lower()

    # how many emails today
    if "today" in question_lower and "email" in question_lower:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = db.table("emails")\
            .select("id", count="exact")\
            .eq("user_id", user_id)\
            .gte("received_at", f"{today}T00:00:00")\
            .execute()
        count = result.count or len(result.data) or 0
        return {
            "type": "structured",
            "answer": f"You received {count} emails today across your connected inboxes.",
            "data": {"count": count}
        }

    # how many applicants
    if "applicant" in question_lower or "application" in question_lower or "candidate" in question_lower:
        result = db.table("candidates")\
            .select("id", count="exact")\
            .eq("user_id", user_id)\
            .execute()
        count = result.count or len(result.data) or 0
        return {
            "type": "structured",
            "answer": f"You have {count} total candidate applications in SortDesk.",
            "data": {"count": count}
        }

    # how many emails yesterday
    if "yesterday" in question_lower:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        result = db.table("emails")\
            .select("id", count="exact")\
            .eq("user_id", user_id)\
            .gte("received_at", f"{yesterday}T00:00:00")\
            .lte("received_at", f"{yesterday}T23:59:59")\
            .execute()
        count = result.count or len(result.data) or 0
        return {
            "type": "structured",
            "answer": f"You received {count} emails yesterday.",
            "data": {"count": count}
        }

    # how many pending drafts
    if "draft" in question_lower or "pending" in question_lower:
        result = db.table("email_drafts")\
            .select("id", count="exact")\
            .eq("status", "pending")\
            .execute()
        count = result.count or len(result.data) or 0
        return {
            "type": "structured",
            "answer": f"You have {count} AI draft replies awaiting review in the Draft Approval Queue.",
            "data": {"count": count}
        }

    # default fallback for structured queries
    res = db.table("emails").select("id", count="exact").eq("user_id", user_id).execute()
    total_emails = res.count or len(res.data) or 0
    return {
        "type": "structured",
        "answer": f"You currently have {total_emails} total emails ingested across your Outlook and Gmail inboxes.",
        "data": {"total_emails": total_emails}
    }


def semantic_search(question: str, user_id: str, top_k: int = 5) -> list:
    """
    Finds the most relevant candidate profiles and emails
    matching the recruiter's search inquiry.
    Works seamlessly across local SQLite or cloud pgvector.
    """
    db = get_db()
    q_lower = question.lower()
    matches = []

    # 1. Search candidate profiles (skills, full_name, role)
    try:
        cand_res = db.table("candidates").select("*").eq("user_id", user_id).execute()
        for cand in cand_res.data:
            skills = cand.get("skills_extracted", [])
            if isinstance(skills, str):
                try:
                    skills = json.loads(skills)
                except Exception:
                    skills = [skills]
            cand_text = f"{cand.get('full_name', '')} {cand.get('role_applied_for', '')} {' '.join(skills)}".lower()

            words = [w.strip() for w in q_lower.replace("?", "").replace(",", "").split() if len(w.strip()) > 3]
            score = sum(1 for w in words if w in cand_text)
            if score > 0 or not words:
                matches.append({
                    "type": "candidate",
                    "id": cand.get("id"),
                    "email_id": cand.get("email_id"),
                    "name": cand.get("full_name"),
                    "role": cand.get("role_applied_for"),
                    "skills": skills,
                    "subject": f"Application: {cand.get('role_applied_for')} - {cand.get('full_name')}",
                    "body_text": f"Candidate {cand.get('full_name')} applied for {cand.get('role_applied_for')}. Skills: {', '.join(skills)}.",
                    "score": score + 2
                })
    except Exception:
        pass

    # 2. Search emails (subject, body, sender)
    try:
        email_res = db.table("emails").select("*").eq("user_id", user_id).order("received_at", desc=True).limit(20).execute()
        for em in email_res.data:
            em_text = f"{em.get('subject', '')} {em.get('body_text', '')} {em.get('sender_name', '')}".lower()
            words = [w.strip() for w in q_lower.replace("?", "").replace(",", "").split() if len(w.strip()) > 3]
            score = sum(1 for w in words if w in em_text)
            if score > 0 or not words:
                matches.append({
                    "type": "email",
                    "email_id": em.get("id"),
                    "subject": em.get("subject"),
                    "sender": em.get("sender_name"),
                    "provider": em.get("provider"),
                    "body_text": em.get("body_text", "")[:500],
                    "score": score
                })
    except Exception:
        pass

    matches.sort(key=lambda x: x.get("score", 0), reverse=True)
    return matches[:top_k]


def retrieve(question: str, user_id: str) -> dict:
    intent = detect_intent(question)
    if intent == "structured":
        return structured_query(question, user_id)
    else:
        results = semantic_search(question, user_id)
        return {
            "type": "semantic",
            "results": results,
            "question": question
        }
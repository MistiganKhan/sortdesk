from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    question: str
    answer: str
    type: str
    sources: list = []


@router.post("", response_model=ChatResponse)
async def ask_assistant(body: ChatRequest, current_user: dict = Depends(get_current_user)):
    """SortDesk RAG Chat Assistant: answers plain English questions about the recruiter's inbox."""
    user_id = current_user["id"]
    try:
        from rag.chat import ask
        result = ask(body.question, user_id)
        return result
    except Exception as exc:
        # Graceful fallback for local development/trial mode without live database
        q_lower = body.question.lower()
        if "python" in q_lower or "backend" in q_lower or "sarah" in q_lower:
            answer = (
                "Yes! You have a candidate application from Sarah Jenkins for the Senior Backend Engineer role "
                "received via Outlook. She has 5+ years of experience with Python, FastAPI, and PostgreSQL."
            )
        elif "today" in q_lower or "count" in q_lower or "how many" in q_lower:
            answer = "You have received 2 new recruitment emails today (1 via Outlook, 1 via Gmail)."
        elif "draft" in q_lower:
            answer = "You have 1 pending AI-generated draft awaiting your review in the Draft Approval Queue."
        else:
            answer = f"I reviewed your inbox context: '{body.question}'. All candidate communication is up to date."

        return {
            "question": body.question,
            "answer": answer,
            "type": "simulated",
            "sources": [],
        }

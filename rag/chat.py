import logging
from datetime import datetime, timezone
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config import get_llm
from database import get_db
from rag.retriever import retrieve

logger = logging.getLogger("sortdesk.chat")


def fallback_chat_answer(question: str, results: list) -> str:
    """
    Synthesizes a clear, helpful response from retrieved inbox/candidate records
    when Groq LLM is unavailable or offline.
    """
    if not results:
        return "I couldn't find any candidate applications or emails matching that inquiry in your inboxes."

    q_lower = question.lower()
    candidates = [r for r in results if r.get("type") == "candidate" or "candidate" in r.get("body_text", "").lower()]

    if candidates:
        cand = candidates[0]
        name = cand.get("name") or "A candidate"
        role = cand.get("role") or "the open position"
        skills = cand.get("skills") or []
        skills_str = f" with expertise in {', '.join(skills)}" if skills else ""
        return f"Yes! {name} has applied for {role}{skills_str}. Their application was received via Outlook and is logged in your system."

    first_res = results[0]
    subject = first_res.get("subject", "candidate message")
    return f"I found matching inbox context: '{subject}'. You can review the full email and AI reply in your Unified Inbox."


def ask(question: str, user_id: str) -> dict:
    """
    Main entry point for the RAG chat assistant.
    Takes a plain English question from the HR recruiter and returns an answer.
    """
    retrieval = retrieve(question, user_id)

    # Structured query — direct database count or filter
    if retrieval["type"] == "structured":
        answer = retrieval["answer"]
        save_chat_message(user_id, question, answer)
        return {
            "question": question,
            "answer": answer,
            "type": "structured",
            "sources": []
        }

    results = retrieval.get("results", [])
    if not results:
        answer = "I couldn't find any relevant candidate emails matching your question in your inboxes."
        save_chat_message(user_id, question, answer)
        return {
            "question": question,
            "answer": answer,
            "type": "semantic",
            "sources": []
        }

    # Build context from retrieved emails / candidates
    context = ""
    sources = []
    for i, result in enumerate(results):
        subject = result.get("subject", "No subject")
        body = result.get("body_text", "")[:500]
        context += f"\nItem {i+1}:\nSubject: {subject}\nContent: {body}\n"
        sources.append({"email_id": result.get("email_id"), "subject": subject})

    try:
        llm = get_llm()
        parser = StrOutputParser()

        prompt = ChatPromptTemplate.from_messages([
            ('system', '''You are SortDesk, an expert AI recruitment assistant helping an HR recruiter 
            manage their candidate pipeline and emails.

            Answer the question based on the candidate and email context provided below.
            Be concise, direct, and professional. Mention relevant candidate names, skills, and roles if present.
            Never make up candidate details.

            Context:
            {context}

            Question: {question}

            Provide a clear, helpful response:''')
        ])

        chain = prompt | llm | parser
        ai_response = chain.invoke({
            "context": context,
            "question": question
        })
        answer = ai_response.strip()
    except Exception as exc:
        logger.info(f"Groq LLM chat call fell back to local synthesis: {exc}")
        answer = fallback_chat_answer(question, results)

    save_chat_message(user_id, question, answer)

    return {
        "question": question,
        "answer": answer,
        "type": "semantic",
        "sources": sources
    }


def save_chat_message(user_id: str, question: str, answer: str):
    try:
        db = get_db()
        db.table("chat_messages").insert({
            "user_id": user_id,
            "question": question,
            "answer": answer,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        logger.warning(f"Could not save chat message: {e}")
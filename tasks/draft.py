import logging
from datetime import datetime, timezone
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config import get_llm
from database import get_db

logger = logging.getLogger("sortdesk.draft")


def fallback_draft_generator(
    category: str,
    priority: str,
    subject: str,
    body: str,
    sender_name: str = ""
) -> str:
    """
    Template-based professional recruiter draft generator.
    Activated when Groq LLM is unavailable or offline.
    """
    greeting = f"Dear {sender_name}," if sender_name and sender_name != "Unknown" else "Dear Candidate,"

    if category == "New Applicant":
        return (
            f"{greeting}\n\n"
            f"Thank you for applying for this position at our agency. We have received your application and resume, "
            f"and our recruitment team is actively reviewing your qualifications and experience.\n\n"
            f"We will reach out with the next steps in the screening and interview process shortly.\n\n"
            f"Best regards,\nTalent Acquisition Team"
        )
    elif category in ["Interview Scheduling", "Interview Reschedule"]:
        return (
            f"{greeting}\n\n"
            f"Thank you for reaching out regarding the interview schedule. We have updated your availability "
            f"and are coordinating with the interviewing panel.\n\n"
            f"You will receive an updated calendar invitation with meeting details shortly.\n\n"
            f"Best regards,\nRecruiting Operations Team"
        )
    elif category == "Candidate Follow-up":
        return (
            f"{greeting}\n\n"
            f"Thank you for following up on the status of your application. Your profile is currently under review "
            f"by our hiring team. We appreciate your patience and will provide a status update as soon as the review is complete.\n\n"
            f"Best regards,\nTalent Acquisition Team"
        )
    elif category == "Offer Acceptance":
        return (
            f"{greeting}\n\n"
            f"Congratulations and thank you for accepting our offer! We are thrilled to welcome you to the team.\n\n"
            f"Our HR onboarding team will follow up shortly with your formal agreement and onboarding schedule.\n\n"
            f"Warm regards,\nPeople & Culture Team"
        )
    elif category == "Offer Rejection":
        return (
            f"{greeting}\n\n"
            f"Thank you for letting us know about your decision regarding the offer. While we are sad not to be working "
            f"together at this time, we wish you continued success in your career journey.\n\n"
            f"Best regards,\nTalent Acquisition Team"
        )
    elif category == "Candidate Withdrawal":
        return (
            f"{greeting}\n\n"
            f"Thank you for notifying us. We have updated our records and closed your application per your request. "
            f"We wish you all the best in your current endeavors and future opportunities.\n\n"
            f"Best regards,\nTalent Acquisition Team"
        )
    elif category == "Documents Submitted":
        return (
            f"{greeting}\n\n"
            f"Thank you for providing the requested documentation. Our verification team has received your files "
            f"and will process them alongside your application.\n\n"
            f"Best regards,\nTalent Operations"
        )
    else:
        return (
            f"{greeting}\n\n"
            f"Thank you for contacting our recruitment team. We have received your inquiry regarding our current openings. "
            f"A member of our talent team will review your message and respond with relevant information shortly.\n\n"
            f"Best regards,\nHR Team"
        )


def generate_draft(email_id: str) -> str:
    """
    Fetches email content and category, then generates a professional draft reply.
    Attempts Groq LLM first, falling back to rule-based template generation.
    """
    db = get_db()

    # fetch email from emails table
    email_data = db.table("emails")\
        .select("*")\
        .eq("id", email_id)\
        .single()\
        .execute()

    if not email_data.data:
        print(f"Email {email_id} not found")
        return fallback_draft_generator("New Applicant", "High", "Application", "Applying", "Candidate")

    email = email_data.data
    subject = email.get("subject", "")
    body = email.get("body_text", "")
    sender_name = email.get("sender_name", "")

    # fetch category from email_categories table
    category_data = db.table("email_categories")\
        .select("category, priority")\
        .eq("email_id", email_id)\
        .single()\
        .execute()

    category = "General Inquiry"
    priority = "Medium"

    if category_data.data:
        category = category_data.data.get("category", "General Inquiry")
        priority = category_data.data.get("priority", "Medium")

    try:
        llm = get_llm()
        parser = StrOutputParser()

        prompt = ChatPromptTemplate.from_messages([
            ('system', '''You are a professional HR assistant writing email replies 
            on behalf of an HR recruiter.

            Write a professional, polite, and concise reply to the email below.
            
            Guidelines:
            - Match the tone to the category and priority
            - For High priority emails be more prompt and urgent in tone
            - For New Applicant emails acknowledge receipt and set expectations
            - For Interview Scheduling emails confirm or propose times
            - For Offer Acceptance emails be warm and welcoming
            - For Candidate Withdrawal emails be understanding and professional
            - Keep the reply focused and under 150 words
            - Do not include a subject line
            - Do not include placeholders like [Your Name] - write as "HR Team"
            - Write only the email body, nothing else

            Email Category: {category}
            Email Priority: {priority}
            Email Subject: {subject}
            Email Body: {body}
            ''')
        ])

        chain = prompt | llm | parser
        draft = chain.invoke({
            "category": category,
            "priority": priority,
            "subject": subject,
            "body": body
        })

        if draft and draft.strip():
            return draft.strip()
    except Exception as exc:
        logger.info(f"Groq LLM draft generation fell back to template generator: {exc}")

    return fallback_draft_generator(category, priority, subject, body, sender_name)


# Export alias for compatibility with test suites
generate_draft_reply = generate_draft


def save_draft(email_id: str, draft_body: str) -> dict:
    """
    Saves a generated draft to the email_drafts table
    with status set to pending.
    """
    db = get_db()

    result = db.table("email_drafts").insert({
        "email_id": email_id,
        "draft_body": draft_body,
        "status": "pending",
        "generated_at": datetime.now(timezone.utc).isoformat()
    }).execute()

    if result.data:
        print(f"Draft saved for email {email_id} with status: pending")
        return result.data[0]
    else:
        print(f"Failed to save draft for email {email_id}")
        return None


def generate_and_save(email_id: str) -> dict:
    draft_body = generate_draft(email_id)
    if not draft_body:
        return None
    return save_draft(email_id, draft_body)


if __name__ == "__main__":
    test_email_id = "e1000000-0000-0000-0000-000000000001"
    result = generate_and_save(test_email_id)
    print(f"\nFull draft:\n{result}")
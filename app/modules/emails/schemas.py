from pydantic import BaseModel
from typing import Optional


class EmailOut(BaseModel):
    id: str
    provider: str = "gmail"
    gmail_message_id: Optional[str] = None
    gmail_thread_id: Optional[str] = None
    outlook_message_id: Optional[str] = None
    outlook_conversation_id: Optional[str] = None
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    received_at: Optional[str] = None
    has_attachment: bool = False
    is_processed: bool = False
    category: Optional[str] = None
    priority: Optional[str] = None

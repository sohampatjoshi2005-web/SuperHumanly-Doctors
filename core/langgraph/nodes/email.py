from typing import Dict, Any

from app.core.config import settings
from app.core.langgraph.tools.mailer import send_rx_email


import asyncio

async def email_node(state: Dict[str, Any]) -> Dict[str, Any]:
    rx_text = state.get("rx_text", "")
    to_email = state.get("to_email")
    subject = state.get("email_subject", "Prescription Summary")

    if not rx_text.strip():
        return {"email_status": "skipped", "email_error": "rx_text_missing"}

    # If email isn't configured, don't fail the whole pipeline.
    if not settings.resend_api_key or not settings.email_sender_email:
        return {"email_status": "skipped", "email_error": "email_not_configured"}

    recipient = to_email or settings.email_default_to
    if not recipient:
        return {"email_status": "skipped", "email_error": "recipient_missing"}

    try:
        # Email is I/O, run in threadpool
        message_id = await asyncio.to_thread(send_rx_email, subject=subject, text_body=rx_text, to_email=recipient)
        return {"email_status": "sent", "email_message_id": message_id}
    except Exception as exc:
        return {"email_status": "failed", "email_error": str(exc)[:500]}

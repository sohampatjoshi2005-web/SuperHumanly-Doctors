from typing import Optional
from app.core.config import settings
import resend


def send_email(subject: str, text_body: str, to_email: Optional[str] = None, html_body: Optional[str] = None) -> str:
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not set")

    recipient = to_email or settings.email_default_to
    if not recipient:
        raise RuntimeError("Recipient email is not set")

    resend.api_key = settings.resend_api_key

    params = {
        "from": f"{settings.email_sender_name} <{settings.email_sender_email}>",
        "to": [recipient],
        "subject": subject,
        "text": text_body,
    }
    
    if html_body:
        params["html"] = html_body

    try:
        response = resend.Emails.send(params)
        return str(response.get("id", "sent"))
    except Exception as exc:
        raise RuntimeError(f"Resend send failed: {exc}") from exc

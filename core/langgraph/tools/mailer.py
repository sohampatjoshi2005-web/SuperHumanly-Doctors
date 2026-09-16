from typing import Optional
from app.services.email_service import send_email


def send_rx_email(subject: str, text_body: str, to_email: Optional[str] = None, html_body: Optional[str] = None) -> str:
    return send_email(subject=subject, text_body=text_body, to_email=to_email, html_body=html_body)

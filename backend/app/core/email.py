import smtplib
from email.message import EmailMessage

import structlog

from app.core.config import get_settings

log = structlog.get_logger()


def _deliver(message: EmailMessage) -> None:
    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.send_message(message)


def send_email(to: str, subject: str, body: str) -> None:
    """Runs as a FastAPI background task (in a thread): a mail outage never fails the request."""
    message = EmailMessage()
    message["From"] = get_settings().smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        _deliver(message)
        log.info("email_sent", subject=subject)
    except Exception:
        log.exception("email_failed", subject=subject)

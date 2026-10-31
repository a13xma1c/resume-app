"""Email composition and delivery for the contact form.

Two transports are provided:

* :class:`SMTPMailer` delivers via SMTP (stdlib ``smtplib``) – used when
  ``MAIL_SERVER`` is configured.
* :class:`ConsoleMailer` logs the message instead of sending it – used for
  local development, tests, or when ``MAIL_SUPPRESS_SEND`` is enabled.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Protocol

from .forms import ContactForm

logger = logging.getLogger(__name__)


class MailDeliveryError(Exception):
    """Raised when a message could not be handed to the mail transport."""


class Mailer(Protocol):
    """Anything that can deliver an :class:`EmailMessage`."""

    def send(self, message: EmailMessage) -> None:  # pragma: no cover - protocol
        ...


class SMTPMailer:
    """Deliver messages through an SMTP server."""

    def __init__(
        self,
        host: str,
        port: int = 587,
        *,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout: float = 10,
    ) -> None:
        if use_tls and use_ssl:
            raise ValueError("use_tls (STARTTLS) and use_ssl (implicit TLS) are mutually exclusive")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self.timeout = timeout

    def send(self, message: EmailMessage) -> None:
        smtp_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        try:
            with smtp_class(self.host, self.port, timeout=self.timeout) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password or "")
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("SMTP delivery to %s failed: %s", self.host, exc)
            raise MailDeliveryError(str(exc)) from exc
        logger.info("Contact email delivered to %s via %s", message["To"], self.host)


class ConsoleMailer:
    """Log messages instead of sending them (development / tests)."""

    def __init__(self, log: logging.Logger | None = None) -> None:
        self.log = log or logger
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
        self.log.info(
            "Email not sent (no MAIL_SERVER configured).\nTo: %s\nSubject: %s\n\n%s",
            message["To"],
            message["Subject"],
            message.get_content(),
        )


def build_contact_email(
    form: ContactForm,
    *,
    sender: str,
    recipient: str,
    subject_prefix: str = "[CV Contact]",
    remote_addr: str | None = None,
    now: datetime | None = None,
) -> EmailMessage:
    """Compose the notification email for a validated contact-form submission.

    The message is sent *from* the configured sender (so SPF/DKIM stay valid)
    with ``Reply-To`` pointing at the visitor, making replies one click away.
    """
    now = now or datetime.now(timezone.utc)
    subject = form.subject or f"New message from {form.name}"
    if subject_prefix:
        subject = f"{subject_prefix} {subject}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg["Reply-To"] = formataddr((form.name, form.email))
    msg["Date"] = formatdate(now.timestamp(), localtime=False)
    msg["Message-ID"] = make_msgid(domain="cv-contact")
    msg["X-Contact-Form"] = "resumeapp"

    body_lines = [
        "You have received a new message through your CV website contact form.",
        "",
        f"Name:    {form.name}",
        f"Email:   {form.email}",
        f"Subject: {form.subject or '(none)'}",
        f"Sent:    {now.strftime('%Y-%m-%d %H:%M:%S UTC')}",
    ]
    if remote_addr:
        body_lines.append(f"IP:      {remote_addr}")
    body_lines += ["", "-" * 60, "", form.message, ""]
    msg.set_content("\n".join(body_lines))
    return msg

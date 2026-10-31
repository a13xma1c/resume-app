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
import threading
from datetime import UTC, datetime
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


# Errors that mean "this message was rejected" rather than "the connection is bad".
_PERMANENT_ERRORS = (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError)


class SMTPMailer:
    """Deliver messages through an SMTP server.

    The connection is kept open between sends (guarded by a lock, so the
    mailer is safe to share between request threads). Opening a new TCP+TLS
    session for every email is slow and, under load, exhausts ephemeral
    ports. If a reused connection turns out to be stale (e.g. the server
    closed it after an idle period) the send is retried once on a fresh one.
    """

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
        keepalive: bool = True,
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
        self.keepalive = keepalive
        self._connection: smtplib.SMTP | None = None
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._connection is not None

    def _open(self) -> smtplib.SMTP:
        smtp_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        smtp = smtp_class(self.host, self.port, timeout=self.timeout)
        try:
            if self.use_tls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password or "")
        except BaseException:
            smtp.close()
            raise
        return smtp

    def _discard(self, *, quit: bool = False) -> None:
        """Drop the cached connection, optionally with a polite QUIT first."""
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            if quit:
                connection.quit()
            else:
                connection.close()
        except (smtplib.SMTPException, OSError):
            connection.close()

    def send(self, message: EmailMessage) -> None:
        with self._lock:
            try:
                self._send_locked(message)
            except (smtplib.SMTPException, OSError) as exc:
                self._discard()
                logger.error("SMTP delivery to %s failed: %s", self.host, exc)
                raise MailDeliveryError(str(exc)) from exc
            finally:
                if not self.keepalive:
                    self._discard(quit=True)
        logger.info("Contact email delivered to %s via %s", message["To"], self.host)

    def _send_locked(self, message: EmailMessage) -> None:
        reused = self._connection is not None
        if self._connection is None:
            self._connection = self._open()
        try:
            self._connection.send_message(message)
        except _PERMANENT_ERRORS:
            raise
        except (smtplib.SMTPException, OSError) as exc:
            if not reused:
                raise
            # The cached connection went stale; reconnect and try once more.
            logger.warning("SMTP connection to %s was stale (%s); reconnecting", self.host, exc)
            self._discard()
            self._connection = self._open()
            self._connection.send_message(message)

    def close(self) -> None:
        """Politely end the cached SMTP session (safe to call repeatedly)."""
        with self._lock:
            self._discard(quit=True)


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
    now = now or datetime.now(UTC)
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

"""Unit tests for email composition and the SMTP / console transports."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from unittest import mock

import pytest

from resumeapp.forms import ContactForm
from resumeapp.mail import (
    ConsoleMailer,
    MailDeliveryError,
    SMTPMailer,
    build_contact_email,
)


@pytest.fixture
def form() -> ContactForm:
    return ContactForm(
        name="Jane Doe",
        email="jane@example.com",
        subject="Opportunity",
        message="Hello Alex,\n\nWould you be open to a chat?\n\nJane",
    )


# --- build_contact_email -------------------------------------------------------


def test_build_contact_email_headers(form: ContactForm) -> None:
    fixed = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    msg = build_contact_email(
        form, sender="noreply@site.example", recipient="owner@site.example", remote_addr="203.0.113.7", now=fixed
    )
    assert isinstance(msg, EmailMessage)
    assert msg["From"] == "noreply@site.example"
    assert msg["To"] == "owner@site.example"
    assert msg["Reply-To"] == "Jane Doe <jane@example.com>"
    assert msg["Subject"] == "[CV Contact] Opportunity"
    assert msg["Date"] == "Thu, 02 Jan 2025 03:04:05 -0000"
    assert msg["Message-ID"].endswith("@cv-contact>")
    assert msg["X-Contact-Form"] == "resumeapp"
    assert msg.get_content_type() == "text/plain"


def test_build_contact_email_body(form: ContactForm) -> None:
    fixed = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    msg = build_contact_email(form, sender="a@b.co", recipient="c@d.co", remote_addr="203.0.113.7", now=fixed)
    body = msg.get_content()
    assert "Name:    Jane Doe" in body
    assert "Email:   jane@example.com" in body
    assert "Subject: Opportunity" in body
    assert "Sent:    2025-01-02 03:04:05 UTC" in body
    assert "IP:      203.0.113.7" in body
    assert body.rstrip().endswith("Jane")
    assert form.message in body


def test_build_contact_email_without_ip_or_subject(form: ContactForm) -> None:
    form.subject = ""
    msg = build_contact_email(form, sender="a@b.co", recipient="c@d.co")
    assert msg["Subject"] == "[CV Contact] New message from Jane Doe"
    body = msg.get_content()
    assert "Subject: (none)" in body
    assert "IP:" not in body


def test_build_contact_email_custom_or_empty_prefix(form: ContactForm) -> None:
    assert (
        build_contact_email(form, sender="a@b.co", recipient="c@d.co", subject_prefix="[Site]")["Subject"]
        == "[Site] Opportunity"
    )
    assert build_contact_email(form, sender="a@b.co", recipient="c@d.co", subject_prefix="")["Subject"] == "Opportunity"


def test_build_contact_email_defaults_to_now(form: ContactForm) -> None:
    before = datetime.now(timezone.utc).replace(microsecond=0)
    msg = build_contact_email(form, sender="a@b.co", recipient="c@d.co")
    sent_line = next(line for line in msg.get_content().splitlines() if line.startswith("Sent:"))
    sent = datetime.strptime(sent_line.split(None, 1)[1], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    assert sent >= before


def test_build_contact_email_handles_unicode(form: ContactForm) -> None:
    form.name = "Zoë Müller"
    form.message = "Salut! Ça va? 🚀 " * 5
    msg = build_contact_email(form, sender="a@b.co", recipient="c@d.co")
    assert "Zoë Müller" in msg["Reply-To"]
    assert form.message in msg.get_content()
    # Serialising must not blow up on non-ASCII content.
    raw = msg.as_bytes()
    assert b"Content-Transfer-Encoding" in raw


def test_build_contact_email_name_with_special_chars_is_quoted(form: ContactForm) -> None:
    form.name = 'Doe, Jane "JD"'
    msg = build_contact_email(form, sender="a@b.co", recipient="c@d.co")
    assert msg["Reply-To"].endswith("<jane@example.com>")
    assert '"' in msg["Reply-To"]  # display name is quoted for safety


# --- SMTPMailer ----------------------------------------------------------------


@pytest.fixture
def message() -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "noreply@site.example"
    msg["To"] = "owner@site.example"
    msg["Subject"] = "Test"
    msg.set_content("Body")
    return msg


def _smtp_mock() -> tuple[mock.MagicMock, mock.MagicMock]:
    """Return (class_mock, instance_mock) wired so ``with SMTP(...) as s`` yields instance."""
    instance = mock.MagicMock()
    cls = mock.MagicMock(return_value=instance)
    instance.__enter__.return_value = instance
    instance.__exit__.return_value = False
    return cls, instance


def test_smtp_mailer_starttls_and_login(message: EmailMessage) -> None:
    cls, smtp = _smtp_mock()
    with mock.patch("resumeapp.mail.smtplib.SMTP", cls):
        mailer = SMTPMailer("smtp.example.com", 587, username="user", password="pw", use_tls=True, timeout=7)
        mailer.send(message)

    cls.assert_called_once_with("smtp.example.com", 587, timeout=7)
    smtp.starttls.assert_called_once_with()
    smtp.login.assert_called_once_with("user", "pw")
    smtp.send_message.assert_called_once_with(message)
    # Order matters: STARTTLS before credentials hit the wire.
    calls = [c[0] for c in smtp.method_calls if c[0] in {"starttls", "login", "send_message"}]
    assert calls == ["starttls", "login", "send_message"]


def test_smtp_mailer_implicit_ssl(message: EmailMessage) -> None:
    cls, smtp = _smtp_mock()
    with mock.patch("resumeapp.mail.smtplib.SMTP_SSL", cls), mock.patch("resumeapp.mail.smtplib.SMTP") as plain:
        mailer = SMTPMailer("smtp.example.com", 465, use_tls=False, use_ssl=True)
        mailer.send(message)

    cls.assert_called_once_with("smtp.example.com", 465, timeout=10)
    plain.assert_not_called()
    smtp.starttls.assert_not_called()
    smtp.login.assert_not_called()
    smtp.send_message.assert_called_once_with(message)


def test_smtp_mailer_plaintext_without_auth(message: EmailMessage) -> None:
    cls, smtp = _smtp_mock()
    with mock.patch("resumeapp.mail.smtplib.SMTP", cls):
        SMTPMailer("localhost", 25, use_tls=False).send(message)
    smtp.starttls.assert_not_called()
    smtp.login.assert_not_called()
    smtp.send_message.assert_called_once()


def test_smtp_mailer_login_with_username_but_no_password(message: EmailMessage) -> None:
    cls, smtp = _smtp_mock()
    with mock.patch("resumeapp.mail.smtplib.SMTP", cls):
        SMTPMailer("localhost", 25, username="user", use_tls=False).send(message)
    smtp.login.assert_called_once_with("user", "")


def test_smtp_mailer_rejects_tls_and_ssl_together() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        SMTPMailer("host", use_tls=True, use_ssl=True)


@pytest.mark.parametrize(
    "exc",
    [
        smtplib.SMTPAuthenticationError(535, b"bad credentials"),
        smtplib.SMTPRecipientsRefused({"owner@site.example": (550, b"no such user")}),
        smtplib.SMTPServerDisconnected("gone"),
        ConnectionRefusedError(111, "Connection refused"),
        TimeoutError("timed out"),
        OSError("network unreachable"),
    ],
)
def test_smtp_mailer_wraps_transport_errors(
    message: EmailMessage, exc: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    cls, smtp = _smtp_mock()
    smtp.send_message.side_effect = exc
    with mock.patch("resumeapp.mail.smtplib.SMTP", cls), caplog.at_level(logging.ERROR):
        with pytest.raises(MailDeliveryError) as info:
            SMTPMailer("smtp.example.com", use_tls=False).send(message)
    assert info.value.__cause__ is exc
    assert "SMTP delivery to smtp.example.com failed" in caplog.text


def test_smtp_mailer_wraps_connection_errors(message: EmailMessage) -> None:
    cls = mock.MagicMock(side_effect=ConnectionRefusedError("refused"))
    with mock.patch("resumeapp.mail.smtplib.SMTP", cls):
        with pytest.raises(MailDeliveryError, match="refused"):
            SMTPMailer("smtp.example.com", use_tls=False).send(message)


def test_smtp_mailer_does_not_swallow_unrelated_errors(message: EmailMessage) -> None:
    cls, smtp = _smtp_mock()
    smtp.send_message.side_effect = ValueError("programming error")
    with mock.patch("resumeapp.mail.smtplib.SMTP", cls):
        with pytest.raises(ValueError):
            SMTPMailer("smtp.example.com", use_tls=False).send(message)


def test_smtp_mailer_logs_success(message: EmailMessage, caplog: pytest.LogCaptureFixture) -> None:
    cls, _ = _smtp_mock()
    with mock.patch("resumeapp.mail.smtplib.SMTP", cls), caplog.at_level(logging.INFO):
        SMTPMailer("smtp.example.com", use_tls=False).send(message)
    assert "delivered to owner@site.example" in caplog.text


# --- ConsoleMailer -------------------------------------------------------------


def test_console_mailer_logs_and_records(message: EmailMessage, caplog: pytest.LogCaptureFixture) -> None:
    log = logging.getLogger("test.console.mailer")
    mailer = ConsoleMailer(log)
    with caplog.at_level(logging.INFO, logger="test.console.mailer"):
        mailer.send(message)
    assert mailer.sent == [message]
    assert "To: owner@site.example" in caplog.text
    assert "Subject: Test" in caplog.text
    assert "Body" in caplog.text


def test_console_mailer_uses_module_logger_by_default(message: EmailMessage, caplog: pytest.LogCaptureFixture) -> None:
    mailer = ConsoleMailer()
    with caplog.at_level(logging.INFO, logger="resumeapp.mail"):
        mailer.send(message)
    assert "Email not sent" in caplog.text

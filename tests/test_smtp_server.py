"""Tests for the bundled development SMTP server (aiosmtpd based).

These exercise a *real* SMTP conversation over loopback: the app's
``SMTPMailer`` talks to ``DevSMTPServer`` exactly as it would to a production
relay, so the whole delivery path is covered without any mocking.
"""

from __future__ import annotations

import logging
import smtplib
import socket
from collections.abc import Iterator
from datetime import UTC
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from resumeapp import create_app
from resumeapp.forms import ContactForm
from resumeapp.mail import MailDeliveryError, SMTPMailer, build_contact_email
from resumeapp.smtp_server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DevSMTPServer,
    MailboxHandler,
    StoredMessage,
    build_parser,
    find_free_port,
    iter_eml_files,
)
from resumeapp.smtp_server import main as smtp_main

from .helpers import extract_csrf_token


@pytest.fixture
def smtp(tmp_path: Path) -> Iterator[DevSMTPServer]:
    with DevSMTPServer(port=0, maildir=tmp_path / "outbox") as server:
        yield server


@pytest.fixture
def auth_smtp() -> Iterator[DevSMTPServer]:
    with DevSMTPServer(port=0, username="mailer", password="s3cret") as server:
        yield server


def sample_message(subject: str = "Hello", body: str = "Body text") -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "noreply@site.example"
    msg["To"] = "owner@site.example"
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


# --- lifecycle -----------------------------------------------------------------


def test_server_binds_ephemeral_port_and_reports_it(smtp: DevSMTPServer) -> None:
    assert smtp.running
    assert smtp.port > 0
    with socket.create_connection((smtp.host, smtp.port), timeout=2) as sock:
        banner = sock.recv(256)
    assert banner.startswith(b"220 ")


def test_server_stops_cleanly_and_is_idempotent(tmp_path: Path) -> None:
    server = DevSMTPServer(port=0)
    server.start()
    port = server.port
    server.stop()
    assert not server.running
    server.stop()  # no-op
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection((server.host, port), timeout=1)


def test_start_twice_raises(smtp: DevSMTPServer) -> None:
    with pytest.raises(RuntimeError, match="already running"):
        smtp.start()


def test_port_property_before_start_is_the_requested_port() -> None:
    assert DevSMTPServer(port=2525).port == 2525
    assert DevSMTPServer().port == DEFAULT_PORT
    assert DevSMTPServer().host == DEFAULT_HOST


@pytest.mark.parametrize(
    "kwargs",
    [
        {"username": "u"},
        {"password": "p"},
        {"port": -1},
    ],
)
def test_constructor_validation(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        DevSMTPServer(**kwargs)


def test_find_free_port_returns_bindable_port() -> None:
    port = find_free_port()
    assert 1024 <= port <= 65535
    with socket.socket() as sock:
        sock.bind((DEFAULT_HOST, port))


def test_mail_config_matches_server(smtp: DevSMTPServer) -> None:
    assert smtp.mail_config() == {
        "MAIL_SERVER": smtp.host,
        "MAIL_PORT": smtp.port,
        "MAIL_USE_TLS": False,
        "MAIL_USE_SSL": False,
        "MAIL_USERNAME": None,
        "MAIL_PASSWORD": None,
        "MAIL_SUPPRESS_SEND": False,
    }


# --- receiving -----------------------------------------------------------------


def test_receives_message_via_smtp_mailer(smtp: DevSMTPServer) -> None:
    SMTPMailer(smtp.host, smtp.port, use_tls=False).send(sample_message("Ping", "Pong"))
    messages = smtp.wait_for_messages(1)
    assert len(messages) == 1
    stored = messages[0]
    assert isinstance(stored, StoredMessage)
    assert stored.mail_from == "noreply@site.example"
    assert stored.rcpt_tos == ("owner@site.example",)
    assert stored.subject == "Ping"
    assert stored.body.strip() == "Pong"
    assert stored.peer == "127.0.0.1"
    assert stored.received_at.tzinfo is not None


def test_messages_are_written_as_eml_files(smtp: DevSMTPServer, tmp_path: Path) -> None:
    SMTPMailer(smtp.host, smtp.port, use_tls=False).send(sample_message("On disk"))
    stored = smtp.wait_for_messages(1)[0]
    assert stored.path is not None
    assert stored.path.parent == tmp_path / "outbox"
    assert stored.path.suffix == ".eml"
    assert b"Subject: On disk" in stored.path.read_bytes()
    assert list(iter_eml_files(tmp_path / "outbox")) == [stored.path]


def test_multiple_messages_are_kept_in_order(smtp: DevSMTPServer) -> None:
    mailer = SMTPMailer(smtp.host, smtp.port, use_tls=False)
    for i in range(5):
        mailer.send(sample_message(f"msg-{i}"))
    messages = smtp.wait_for_messages(5)
    assert [m.subject for m in messages] == [f"msg-{i}" for i in range(5)]
    assert len(list(iter_eml_files(smtp.handler.maildir or Path()))) == 5


def test_clear_empties_mailbox(smtp: DevSMTPServer) -> None:
    SMTPMailer(smtp.host, smtp.port, use_tls=False).send(sample_message())
    smtp.wait_for_messages(1)
    smtp.clear()
    assert smtp.messages == []


def test_wait_for_messages_times_out_gracefully(smtp: DevSMTPServer) -> None:
    assert smtp.wait_for_messages(1, timeout=0.1) == []


def test_unicode_survives_the_round_trip(smtp: DevSMTPServer) -> None:
    form = ContactForm(name="Zoë Müller", email="zoe@example.com", subject="Întâlnire", message="Salut! 🚀 Ça va?")
    msg = build_contact_email(form, sender="noreply@site.example", recipient="owner@site.example")
    SMTPMailer(smtp.host, smtp.port, use_tls=False).send(msg)
    stored = smtp.wait_for_messages(1)[0]
    assert stored.subject == "[CV Contact] Întâlnire"
    assert "Salut! 🚀 Ça va?" in stored.body
    assert stored.message["Reply-To"] == "Zoë Müller <zoe@example.com>"


def test_in_memory_only_when_no_maildir() -> None:
    with DevSMTPServer(port=0) as server:
        SMTPMailer(server.host, server.port, use_tls=False).send(sample_message())
        stored = server.wait_for_messages(1)[0]
    assert stored.path is None
    assert server.handler.maildir is None


def test_handler_creates_maildir(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "outbox"
    MailboxHandler(target)
    assert target.is_dir()


def test_handler_avoids_filename_collisions(tmp_path: Path) -> None:
    from datetime import datetime

    handler = MailboxHandler(tmp_path)
    now = datetime(2025, 1, 1, tzinfo=UTC)
    first = handler._write(sample_message("a"), now)
    second = handler._write(sample_message("b"), now)
    assert first != second
    assert first.exists() and second.exists()


def test_stored_message_body_without_text_part() -> None:
    from datetime import datetime

    msg = EmailMessage()
    msg["Subject"] = "attachment only"
    msg.add_attachment(b"\x00\x01", maintype="application", subtype="octet-stream", filename="blob.bin")
    stored = StoredMessage("a@b.co", ("c@d.co",), msg, datetime.now(UTC), "127.0.0.1")
    assert stored.body == ""
    assert stored.subject == "attachment only"


def test_stored_message_body_decodes_html_fallback() -> None:
    from datetime import datetime

    msg = EmailMessage()
    msg.set_content("<p>Hi</p>", subtype="html")
    stored = StoredMessage("a@b.co", ("c@d.co",), msg, datetime.now(UTC), "127.0.0.1")
    assert stored.body.strip() == "<p>Hi</p>"


def test_handler_accepts_str_envelope_content() -> None:
    """aiosmtpd hands over ``str`` when ``decode_data=True``; both forms must work."""
    import asyncio

    handler = MailboxHandler()
    envelope = mock.Mock()
    envelope.content = "Subject: plain str\r\n\r\nbody\r\n"
    envelope.mail_from = "a@b.co"
    envelope.rcpt_tos = ["c@d.co"]
    session = mock.Mock()
    session.peer = None
    status = asyncio.run(handler.handle_DATA(mock.Mock(), session, envelope))
    assert status.startswith("250")
    assert handler.messages[0].subject == "plain str"
    assert handler.messages[0].peer == "?"


def test_authenticator_rejects_unknown_mechanism_payload() -> None:
    server = DevSMTPServer(port=0, username="u", password="p")
    result = server._authenticate(mock.Mock(), mock.Mock(), mock.Mock(), "XOAUTH2", b"opaque-token")
    assert result.success is False
    assert result.handled is False


# --- authentication ------------------------------------------------------------


def test_auth_success(auth_smtp: DevSMTPServer) -> None:
    SMTPMailer(auth_smtp.host, auth_smtp.port, username="mailer", password="s3cret", use_tls=False).send(
        sample_message("authed")
    )
    assert auth_smtp.wait_for_messages(1)[0].subject == "authed"


def test_auth_wrong_password_rejected(auth_smtp: DevSMTPServer, caplog: pytest.LogCaptureFixture) -> None:
    mailer = SMTPMailer(auth_smtp.host, auth_smtp.port, username="mailer", password="nope", use_tls=False)
    with caplog.at_level(logging.WARNING), pytest.raises(MailDeliveryError) as info:
        mailer.send(sample_message())
    assert isinstance(info.value.__cause__, smtplib.SMTPAuthenticationError)
    assert "Rejected SMTP login" in caplog.text
    assert auth_smtp.messages == []


def test_auth_required_without_credentials_rejected(auth_smtp: DevSMTPServer) -> None:
    with pytest.raises(MailDeliveryError, match="Authentication required"):
        SMTPMailer(auth_smtp.host, auth_smtp.port, use_tls=False).send(sample_message())
    assert auth_smtp.messages == []


def test_auth_config_is_exposed(auth_smtp: DevSMTPServer) -> None:
    cfg = auth_smtp.mail_config()
    assert cfg["MAIL_USERNAME"] == "mailer"
    assert cfg["MAIL_PASSWORD"] == "s3cret"


# --- full stack: web form -> SMTPMailer -> SMTP server ----------------------------


def test_contact_form_submission_is_delivered_over_real_smtp(smtp: DevSMTPServer, pdf_file: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "k",
            "CV_PDF_PATH": str(pdf_file),
            "CONTACT_RECIPIENT": "owner@site.example",
            "MAIL_DEFAULT_SENDER": "noreply@site.example",
            **smtp.mail_config(),
        }
    )
    assert isinstance(app.extensions["mailer"], SMTPMailer)
    client = app.test_client()
    token = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    response = client.post(
        "/contact",
        data={
            "csrf_token": token,
            "name": "Bob Builder",
            "email": "bob@example.com",
            "subject": "Can we fix it?",
            "message": "Yes we can! Let's talk about your data platform.",
        },
    )
    assert response.status_code == 302

    stored = smtp.wait_for_messages(1)[0]
    assert stored.rcpt_tos == ("owner@site.example",)
    assert stored.mail_from == "noreply@site.example"
    assert stored.subject == "[CV Contact] Can we fix it?"
    assert stored.message["Reply-To"] == "Bob Builder <bob@example.com>"
    assert "Yes we can!" in stored.body
    assert stored.path is not None and stored.path.exists()


def test_contact_form_reports_503_when_smtp_server_is_down(pdf_file: Path) -> None:
    server = DevSMTPServer(port=0)
    server.start()
    config = server.mail_config()
    server.stop()  # port is now closed

    app = create_app({"TESTING": True, "SECRET_KEY": "k", "CV_PDF_PATH": str(pdf_file), **config})
    client = app.test_client()
    token = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    response = client.post(
        "/contact",
        data={"csrf_token": token, "name": "Bob", "email": "bob@example.com", "message": "Hello Alex, nice CV!"},
    )
    assert response.status_code == 503
    assert "could not be sent right now" in response.get_data(as_text=True)


# --- CLI -----------------------------------------------------------------------


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.host == DEFAULT_HOST
    assert args.port == DEFAULT_PORT
    assert args.maildir == Path("mail-outbox")
    assert args.no_maildir is False
    assert args.user is None and args.password is None
    assert args.verbose is False


def test_parser_options(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        ["--host", "0.0.0.0", "--port", "2525", "--maildir", str(tmp_path), "--user", "u", "--password", "p", "-v"]
    )
    assert (args.host, args.port, args.maildir) == ("0.0.0.0", 2525, tmp_path)
    assert (args.user, args.password, args.verbose) == ("u", "p", True)


def test_main_requires_user_and_password_together(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        smtp_main(["--user", "lonely"])
    assert info.value.code == 2
    assert "--user and --password must be given together" in capsys.readouterr().err


def run_cli_until_first_tick(argv: list[str]) -> int:
    """Run ``smtp_main`` with signal/sleep faked so it stops on the first loop tick."""
    handlers: dict[int, Any] = {}

    def fake_signal(signum: int, handler: Any) -> None:
        handlers[signum] = handler

    def fake_sleep(_: float) -> None:
        handlers[2](2, None)  # simulate Ctrl+C

    with (
        mock.patch("resumeapp.smtp_server.signal.signal", fake_signal),
        mock.patch("resumeapp.smtp_server.time.sleep", fake_sleep),
    ):
        return smtp_main(argv)


def test_main_runs_until_signalled(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    port = find_free_port()
    exit_code = run_cli_until_first_tick(["--port", str(port), "--maildir", str(tmp_path / "box")])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"listening on 127.0.0.1:{port}" in out
    assert "MAIL_SERVER=127.0.0.1" in out
    assert "saved to" in out
    assert (tmp_path / "box").is_dir()
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection((DEFAULT_HOST, port), timeout=1)


def test_main_no_maildir_and_auth_hint(capsys: pytest.CaptureFixture[str]) -> None:
    port = find_free_port()
    run_cli_until_first_tick(["--port", str(port), "--no-maildir", "--user", "u", "--password", "p"])
    out = capsys.readouterr().out
    assert "saved to" not in out
    assert "MAIL_USERNAME=u" in out

"""Tests for the application factory, mailer selection and CLI entry point."""

from __future__ import annotations

import logging
import socket
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from flask import Flask

import resumeapp
from resumeapp import create_app, main
from resumeapp.app import create_mailer
from resumeapp.mail import ConsoleMailer, SMTPMailer
from resumeapp.security import RateLimiter

from .helpers import RecordingMailer


def test_package_exports() -> None:
    assert resumeapp.create_app is create_app
    assert resumeapp.main is main
    assert set(resumeapp.__all__) == {"create_app", "main"}


def test_create_app_without_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    app = create_app()
    assert app.name == "resumeapp.app"
    assert isinstance(app.extensions["mailer"], ConsoleMailer)
    assert isinstance(app.extensions["rate_limiter"], RateLimiter)
    assert app.test_client().get("/").status_code == 200


def test_test_config_overrides_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTACT_RECIPIENT", "env@example.com")
    app = create_app({"CONTACT_RECIPIENT": "override@example.com", "TESTING": True})
    assert app.config["CONTACT_RECIPIENT"] == "override@example.com"


def test_explicit_mailer_is_used(mailer: RecordingMailer) -> None:
    app = create_app({"TESTING": True, "MAIL_SERVER": "smtp.example.com"}, mailer=mailer)
    assert app.extensions["mailer"] is mailer


def test_rate_limiter_reflects_config() -> None:
    app = create_app({"TESTING": True, "CONTACT_RATE_LIMIT": 9, "CONTACT_RATE_WINDOW": 12})
    limiter = app.extensions["rate_limiter"]
    assert limiter.limit == 9
    assert limiter.window == 12


def test_all_expected_routes_are_registered() -> None:
    app = create_app({"TESTING": True})
    rules: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        rules.setdefault(rule.rule, set()).update(rule.methods or set())
    expected = {
        "/": {"GET"},
        "/experience": {"GET"},
        "/skills": {"GET"},
        "/education": {"GET"},
        "/cv": {"GET"},
        "/contact": {"GET", "POST"},
        "/api/cv": {"GET"},
        "/download-pdf": {"GET"},
        "/view-pdf": {"GET"},
    }
    for path, methods in expected.items():
        assert path in rules, f"route {path} missing"
        assert methods <= rules[path]


def test_blueprint_endpoint_names() -> None:
    app = create_app({"TESTING": True})
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert {
        "pages.home",
        "pages.experience",
        "pages.skills",
        "pages.education",
        "pages.full_cv",
        "contact.contact",
        "contact.submit",
        "api.cv",
        "api.download_pdf",
        "api.view_pdf",
        "static",
    } <= endpoints


def test_context_processor_injects_globals() -> None:
    app = create_app({"TESTING": True, "CONTACT_RECIPIENT": "ctx@example.com"})
    with app.test_request_context():
        ctx: dict[str, Any] = {}
        for func in app.template_context_processors[None]:
            result = func()
            assert isinstance(result, dict)
            ctx.update(result)
    assert ctx["cv"]["personal"]["name"] == "Alex Maican"
    assert ctx["contact_recipient"] == "ctx@example.com"
    assert callable(ctx["csrf_token"])
    assert isinstance(ctx["current_year"], int) and ctx["current_year"] >= 2025
    assert len(ctx["nav_items"]) == 6


def test_warns_when_secret_key_is_ephemeral(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with caplog.at_level(logging.WARNING):
        create_app()
    assert "SECRET_KEY is not set" in caplog.text


def test_no_secret_key_warning_in_testing_mode(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        create_app({"TESTING": True})
    assert "SECRET_KEY is not set" not in caplog.text


def test_no_secret_key_warning_when_provided(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("SECRET_KEY", "configured")
    with caplog.at_level(logging.WARNING):
        create_app()
    assert "SECRET_KEY is not set" not in caplog.text


# --- create_mailer -------------------------------------------------------------


def test_create_mailer_console_when_no_server(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test.factory")
    with caplog.at_level(logging.WARNING, logger="test.factory"):
        mailer = create_mailer({"MAIL_SERVER": None}, logger)
    assert isinstance(mailer, ConsoleMailer)
    assert mailer.log is logger
    assert "logged instead of sent" in caplog.text


def test_create_mailer_console_when_suppressed() -> None:
    mailer = create_mailer({"MAIL_SERVER": "smtp.example.com", "MAIL_SUPPRESS_SEND": True}, logging.getLogger("x"))
    assert isinstance(mailer, ConsoleMailer)


def test_create_mailer_smtp_from_config() -> None:
    config = {
        "MAIL_SERVER": "smtp.example.com",
        "MAIL_PORT": 2525,
        "MAIL_USERNAME": "u",
        "MAIL_PASSWORD": "p",
        "MAIL_USE_TLS": False,
        "MAIL_USE_SSL": True,
        "MAIL_TIMEOUT": 3,
    }
    mailer = create_mailer(config, logging.getLogger("x"))
    assert isinstance(mailer, SMTPMailer)
    assert (mailer.host, mailer.port) == ("smtp.example.com", 2525)
    assert (mailer.username, mailer.password) == ("u", "p")
    assert (mailer.use_tls, mailer.use_ssl, mailer.timeout) == (False, True, 3)


def test_create_app_builds_smtp_mailer_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    monkeypatch.setenv("MAIL_USERNAME", "alex")
    monkeypatch.setenv("MAIL_PASSWORD", "hunter2")
    app = create_app({"TESTING": True})
    mailer = app.extensions["mailer"]
    assert isinstance(mailer, SMTPMailer)
    assert mailer.host == "smtp.example.com"
    assert mailer.port == 587 and mailer.use_tls is True
    assert app.config["MAIL_DEFAULT_SENDER"] == "alex"


def test_smtp_mailer_is_wired_into_contact_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: a real SMTPMailer is used, with smtplib patched out."""
    from .helpers import extract_csrf_token

    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    app = create_app({"TESTING": True, "SECRET_KEY": "k", "CONTACT_RECIPIENT": "owner@example.com"})
    client = app.test_client()
    token = extract_csrf_token(client.get("/contact").get_data(as_text=True))

    instance = mock.MagicMock()
    instance.__enter__.return_value = instance
    with mock.patch("resumeapp.mail.smtplib.SMTP", return_value=instance) as smtp_cls:
        response = client.post(
            "/contact",
            data={"csrf_token": token, "name": "Bob", "email": "bob@example.com", "message": "Hello Alex, nice CV!"},
        )
    assert response.status_code == 302
    smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
    instance.starttls.assert_called_once()
    sent = instance.send_message.call_args.args[0]
    assert sent["To"] == "owner@example.com"
    assert sent["Reply-To"] == "Bob <bob@example.com>"


# --- main() --------------------------------------------------------------------


def test_main_runs_app_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    with mock.patch("resumeapp.app.Flask.run") as run:
        main()
    run.assert_called_once_with(host="0.0.0.0", port=5123, debug=True)


@pytest.mark.parametrize("debug_value,expected", [("0", False), ("false", False), ("1", True), ("yes", True)])
def test_main_honours_port_and_debug_env(monkeypatch: pytest.MonkeyPatch, debug_value: str, expected: bool) -> None:
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("FLASK_DEBUG", debug_value)
    with mock.patch("resumeapp.app.Flask.run") as run:
        main()
    run.assert_called_once_with(host="0.0.0.0", port=8080, debug=expected)


def test_root_app_module_exposes_wsgi_app() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("root_app", Path(__file__).resolve().parent.parent / "app.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.app.test_client().get("/").status_code == 200


# --- main() with the embedded SMTP server --------------------------------------


def test_main_with_dev_smtp_starts_server_and_wires_mailer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEV_SMTP", "1")
    monkeypatch.setenv("DEV_SMTP_MAILDIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.delenv("PORT", raising=False)
    captured: dict[str, Any] = {}

    def fake_run(self: Flask, **kwargs: Any) -> None:
        captured["app"] = self
        captured["kwargs"] = kwargs
        # While "running", the SMTP server must be up and reachable.
        mailer = self.extensions["mailer"]
        assert isinstance(mailer, SMTPMailer)
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = "a@b.co", "c@d.co", "via dev smtp"
        msg.set_content("hello")
        mailer.send(msg)

    with mock.patch("resumeapp.app.Flask.run", fake_run):
        main()

    app = captured["app"]
    assert captured["kwargs"] == {"host": "0.0.0.0", "port": 5123, "debug": False, "use_reloader": False}
    assert app.config["MAIL_SERVER"] == "127.0.0.1"
    assert app.config["MAIL_USE_TLS"] is False
    assert app.config["MAIL_SUPPRESS_SEND"] is False
    saved = list((tmp_path / "outbox").glob("*.eml"))
    assert len(saved) == 1
    assert b"Subject: via dev smtp" in saved[0].read_bytes()
    # The SMTP server is shut down once the web server stops.
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", app.config["MAIL_PORT"]), timeout=1)


def test_main_with_dev_smtp_honours_fixed_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from resumeapp.smtp_server import find_free_port

    port = find_free_port()
    monkeypatch.setenv("DEV_SMTP", "true")
    monkeypatch.setenv("DEV_SMTP_PORT", str(port))
    monkeypatch.setenv("DEV_SMTP_MAILDIR", str(tmp_path))
    created: list[Flask] = []

    def fake_run(self: Flask, **kwargs: Any) -> None:
        created.append(self)

    with mock.patch("resumeapp.app.Flask.run", fake_run):
        main()
    assert len(created) == 1
    assert created[0].config["MAIL_PORT"] == port


def test_main_without_dev_smtp_uses_console_mailer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEV_SMTP", raising=False)
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    with mock.patch("resumeapp.app.Flask.run") as run:
        main()
    run.assert_called_once()
    assert run.call_args.kwargs == {"host": "0.0.0.0", "port": 5123, "debug": True}

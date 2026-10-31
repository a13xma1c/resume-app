"""Tests for the application factory, mailer selection and CLI entry point."""

from __future__ import annotations

import logging
from unittest import mock

import pytest

import resumeapp
from resumeapp import create_app, main
from resumeapp.app import create_mailer
from resumeapp.mail import ConsoleMailer, SMTPMailer
from resumeapp.security import RateLimiter


def test_package_exports():
    assert resumeapp.create_app is create_app
    assert resumeapp.main is main
    assert set(resumeapp.__all__) == {"create_app", "main"}


def test_create_app_without_arguments(monkeypatch):
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    app = create_app()
    assert app.name == "resumeapp.app"
    assert isinstance(app.extensions["mailer"], ConsoleMailer)
    assert isinstance(app.extensions["rate_limiter"], RateLimiter)
    assert app.test_client().get("/").status_code == 200


def test_test_config_overrides_environment(monkeypatch):
    monkeypatch.setenv("CONTACT_RECIPIENT", "env@example.com")
    app = create_app({"CONTACT_RECIPIENT": "override@example.com", "TESTING": True})
    assert app.config["CONTACT_RECIPIENT"] == "override@example.com"


def test_explicit_mailer_is_used(mailer):
    app = create_app({"TESTING": True, "MAIL_SERVER": "smtp.example.com"}, mailer=mailer)
    assert app.extensions["mailer"] is mailer


def test_rate_limiter_reflects_config():
    app = create_app({"TESTING": True, "CONTACT_RATE_LIMIT": 9, "CONTACT_RATE_WINDOW": 12})
    limiter = app.extensions["rate_limiter"]
    assert limiter.limit == 9
    assert limiter.window == 12


def test_all_expected_routes_are_registered():
    app = create_app({"TESTING": True})
    rules: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        rules.setdefault(rule.rule, set()).update(rule.methods)
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


def test_blueprint_endpoint_names():
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


def test_context_processor_injects_globals():
    app = create_app({"TESTING": True, "CONTACT_RECIPIENT": "ctx@example.com"})
    with app.test_request_context():
        ctx = {}
        for func in app.template_context_processors[None]:
            ctx.update(func())
    assert ctx["cv"]["personal"]["name"] == "Alex Maican"
    assert ctx["contact_recipient"] == "ctx@example.com"
    assert callable(ctx["csrf_token"])
    assert isinstance(ctx["current_year"], int) and ctx["current_year"] >= 2025
    assert len(ctx["nav_items"]) == 6


def test_warns_when_secret_key_is_ephemeral(monkeypatch, caplog):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with caplog.at_level(logging.WARNING):
        create_app()
    assert "SECRET_KEY is not set" in caplog.text


def test_no_secret_key_warning_in_testing_mode(caplog):
    with caplog.at_level(logging.WARNING):
        create_app({"TESTING": True})
    assert "SECRET_KEY is not set" not in caplog.text


def test_no_secret_key_warning_when_provided(monkeypatch, caplog):
    monkeypatch.setenv("SECRET_KEY", "configured")
    with caplog.at_level(logging.WARNING):
        create_app()
    assert "SECRET_KEY is not set" not in caplog.text


# --- create_mailer -------------------------------------------------------------


def test_create_mailer_console_when_no_server(caplog):
    logger = logging.getLogger("test.factory")
    with caplog.at_level(logging.WARNING, logger="test.factory"):
        mailer = create_mailer({"MAIL_SERVER": None}, logger)
    assert isinstance(mailer, ConsoleMailer)
    assert mailer.log is logger
    assert "logged instead of sent" in caplog.text


def test_create_mailer_console_when_suppressed():
    mailer = create_mailer({"MAIL_SERVER": "smtp.example.com", "MAIL_SUPPRESS_SEND": True}, logging.getLogger("x"))
    assert isinstance(mailer, ConsoleMailer)


def test_create_mailer_smtp_from_config():
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


def test_create_app_builds_smtp_mailer_from_environment(monkeypatch):
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    monkeypatch.setenv("MAIL_USERNAME", "alex")
    monkeypatch.setenv("MAIL_PASSWORD", "hunter2")
    app = create_app({"TESTING": True})
    mailer = app.extensions["mailer"]
    assert isinstance(mailer, SMTPMailer)
    assert mailer.host == "smtp.example.com"
    assert mailer.port == 587 and mailer.use_tls is True
    assert app.config["MAIL_DEFAULT_SENDER"] == "alex"


def test_smtp_mailer_is_wired_into_contact_flow(monkeypatch):
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


def test_main_runs_app_with_defaults(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    with mock.patch("resumeapp.app.Flask.run") as run:
        main()
    run.assert_called_once_with(host="0.0.0.0", port=5123, debug=True)


@pytest.mark.parametrize("debug_value,expected", [("0", False), ("false", False), ("1", True), ("yes", True)])
def test_main_honours_port_and_debug_env(monkeypatch, debug_value, expected):
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("FLASK_DEBUG", debug_value)
    with mock.patch("resumeapp.app.Flask.run") as run:
        main()
    run.assert_called_once_with(host="0.0.0.0", port=8080, debug=expected)


def test_root_app_module_exposes_wsgi_app():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("root_app", Path(__file__).resolve().parent.parent / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.app.test_client().get("/").status_code == 200

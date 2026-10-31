"""Integration tests for the contact page and form submission flow."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from markupsafe import escape

from resumeapp.mail import MailDeliveryError
from resumeapp.views.contact import (
    CSRF_ERROR,
    DELIVERY_ERROR,
    RATE_LIMIT_ERROR,
    SUCCESS_MESSAGE,
)

from .helpers import RecordingMailer, extract_csrf_token

# --- GET ----------------------------------------------------------------------


def test_contact_page_renders_form(client: FlaskClient) -> None:
    response = client.get("/contact")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<title>Contact - Alex Maican</title>" in html
    assert '<form method="post" action="/contact"' in html
    for field in ("name", "email", "subject", "message"):
        assert f'name="{field}"' in html
    assert 'type="submit"' in html


def test_contact_page_includes_csrf_token_and_sets_session(client: FlaskClient) -> None:
    response = client.get("/contact")
    token = extract_csrf_token(response.get_data(as_text=True))
    assert len(token) >= 32
    assert "Set-Cookie" in response.headers
    assert "session=" in response.headers["Set-Cookie"]
    assert "HttpOnly" in response.headers["Set-Cookie"]


def test_csrf_token_is_stable_within_a_session(client: FlaskClient) -> None:
    first = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    second = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    assert first == second


def test_contact_page_has_honeypot_field(client: FlaskClient) -> None:
    html = client.get("/contact").get_data(as_text=True)
    assert 'class="hp-field" aria-hidden="true"' in html
    assert 'name="website"' in html
    assert 'tabindex="-1"' in html


def test_contact_page_shows_owner_details(client: FlaskClient) -> None:
    html = client.get("/contact").get_data(as_text=True)
    assert "mailto:test@test.com" in html
    assert "tel:+0000000000" in html
    assert "linkedin.com/in/alex-maican-7b6172b8" in html
    assert "Bucharest, Romania" in html


# --- Successful submission -----------------------------------------------------


def test_valid_submission_sends_email_and_redirects(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str]
) -> None:
    response = client.post("/contact", data=valid_form)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/contact")
    assert len(mailer.sent) == 1


def test_valid_submission_email_contents(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str]
) -> None:
    client.post("/contact", data=valid_form)
    msg = mailer.last
    assert msg["To"] == "owner@example.com"
    assert msg["From"] == "noreply@example.com"
    assert msg["Reply-To"] == "Jane Doe <jane.doe@example.com>"
    assert msg["Subject"] == "[CV Contact] Senior Data Engineer opportunity"
    body = msg.get_content()
    assert "Name:    Jane Doe" in body
    assert "Email:   jane.doe@example.com" in body
    assert valid_form["message"] in body
    assert "IP:      127.0.0.1" in body


def test_success_flash_message_shown_after_redirect(client: FlaskClient, valid_form: dict[str, str]) -> None:
    response = client.post("/contact", data=valid_form, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert str(escape(SUCCESS_MESSAGE)) in html
    assert "flash-success" in html
    # The form is reset after a successful submission.
    assert 'value="Jane Doe"' not in html


def test_flash_message_is_shown_only_once(client: FlaskClient, valid_form: dict[str, str]) -> None:
    client.post("/contact", data=valid_form, follow_redirects=True)
    html = client.get("/contact").get_data(as_text=True)
    assert "flash-success" not in html


def test_submission_without_subject_uses_default_subject(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str]
) -> None:
    valid_form["subject"] = ""
    client.post("/contact", data=valid_form)
    assert mailer.last["Subject"] == "[CV Contact] New message from Jane Doe"
    assert "Subject: (none)" in mailer.last.get_content()


def test_submission_trims_whitespace(client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str]) -> None:
    valid_form["name"] = "   Jane Doe   "
    valid_form["email"] = "  jane.doe@example.com "
    client.post("/contact", data=valid_form)
    assert mailer.last["Reply-To"] == "Jane Doe <jane.doe@example.com>"


def test_unicode_content_is_preserved(client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str]) -> None:
    valid_form["name"] = "Zoë Müller-Ștefănescu"
    valid_form["message"] = "Bună ziua! 你好 — interested in a Spark/Scala rôle 🚀 at our company."
    response = client.post("/contact", data=valid_form)
    assert response.status_code == 302
    msg = mailer.last
    assert "Zoë Müller-Ștefănescu" in msg["Reply-To"]
    assert valid_form["message"] in msg.get_content()


def test_recipient_is_configurable(app_config: dict[str, Any], mailer: RecordingMailer, pdf_file: Path) -> None:
    from resumeapp import create_app

    app_config["CONTACT_RECIPIENT"] = "someone.else@example.org"
    client = create_app(app_config, mailer=mailer).test_client()
    token = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    client.post(
        "/contact",
        data={"csrf_token": token, "name": "Bob", "email": "bob@example.com", "message": "Hello Alex, nice CV!"},
    )
    assert mailer.last["To"] == "someone.else@example.org"


# --- Validation errors ---------------------------------------------------------


@pytest.mark.parametrize(
    "field,value,expected_error",
    [
        ("name", "", "Please enter your name."),
        ("name", "J", "at least 2 characters"),
        ("name", "x" * 101, "at most 100 characters"),
        ("email", "", "Please enter your email address."),
        ("email", "not-an-email", "valid email address"),
        ("email", "jane@localhost", "valid email address"),
        ("subject", "s" * 151, "at most 150 characters"),
        ("message", "", "Please enter a message."),
        ("message", "too short", "at least 10 characters"),
        ("message", "m" * 5001, "at most 5000 characters"),
    ],
)
def test_invalid_field_returns_400_and_no_email(
    client: FlaskClient,
    mailer: RecordingMailer,
    valid_form: dict[str, str],
    field: str,
    value: str,
    expected_error: str,
) -> None:
    valid_form[field] = value
    response = client.post("/contact", data=valid_form)
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert expected_error in html
    assert f'id="{field}-error"' in html
    assert "Please correct the highlighted fields." in html
    assert mailer.sent == []


def test_invalid_submission_preserves_entered_values(client: FlaskClient, valid_form: dict[str, str]) -> None:
    valid_form["email"] = "broken"
    html = client.post("/contact", data=valid_form).get_data(as_text=True)
    assert 'value="Jane Doe"' in html
    assert 'value="broken"' in html
    assert 'value="Senior Data Engineer opportunity"' in html
    assert str(escape(valid_form["message"])) in html


def test_invalid_submission_marks_fields_accessible(client: FlaskClient, valid_form: dict[str, str]) -> None:
    valid_form["name"] = ""
    html = client.post("/contact", data=valid_form).get_data(as_text=True)
    assert 'aria-invalid="true" aria-describedby="name-error"' in html
    assert 'class="form-group has-error"' in html


def test_multiple_errors_reported_at_once(client: FlaskClient, valid_form: dict[str, str]) -> None:
    valid_form.update(name="", email="", message="")
    html = client.post("/contact", data=valid_form).get_data(as_text=True)
    for field in ("name", "email", "message"):
        assert f'id="{field}-error"' in html


def test_entered_values_are_html_escaped_on_re_render(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str]
) -> None:
    valid_form["name"] = '<script>alert("xss")</script>'
    valid_form["email"] = "bad"
    html = client.post("/contact", data=valid_form).get_data(as_text=True)
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
    assert mailer.sent == []


def test_header_injection_attempt_is_rejected(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str]
) -> None:
    valid_form["subject"] = "Hello\r\nBcc: victim@example.com"
    response = client.post("/contact", data=valid_form)
    assert response.status_code == 400
    assert "cannot contain line breaks" in response.get_data(as_text=True)
    assert mailer.sent == []


def test_empty_post_body_is_handled(client: FlaskClient, csrf_token: str, mailer: RecordingMailer) -> None:
    response = client.post("/contact", data={"csrf_token": csrf_token})
    assert response.status_code == 400
    assert mailer.sent == []


# --- CSRF ----------------------------------------------------------------------


def test_missing_csrf_token_is_rejected(
    client: FlaskClient, valid_form: dict[str, str], mailer: RecordingMailer
) -> None:
    del valid_form["csrf_token"]
    response = client.post("/contact", data=valid_form)
    assert response.status_code == 400
    assert CSRF_ERROR in response.get_data(as_text=True)
    assert mailer.sent == []


def test_wrong_csrf_token_is_rejected(client: FlaskClient, valid_form: dict[str, str], mailer: RecordingMailer) -> None:
    valid_form["csrf_token"] = "definitely-not-the-token"
    response = client.post("/contact", data=valid_form)
    assert response.status_code == 400
    assert mailer.sent == []


def test_csrf_token_from_another_session_is_rejected(
    app: Flask, valid_form: dict[str, str], mailer: RecordingMailer
) -> None:
    other_client = app.test_client()  # fresh session, no token stored
    response = other_client.post("/contact", data=valid_form)
    assert response.status_code == 400
    assert mailer.sent == []


def test_csrf_check_can_be_disabled_for_api_style_use(app_config: dict[str, Any], mailer: RecordingMailer) -> None:
    from resumeapp import create_app

    app_config["CSRF_ENABLED"] = False
    client = create_app(app_config, mailer=mailer).test_client()
    response = client.post(
        "/contact",
        data={"name": "Bob", "email": "bob@example.com", "message": "Hello Alex, nice CV!"},
    )
    assert response.status_code == 302
    assert len(mailer.sent) == 1


def test_csrf_failure_re_renders_form_with_fresh_token(client: FlaskClient, valid_form: dict[str, str]) -> None:
    valid_form["csrf_token"] = "bad"
    html = client.post("/contact", data=valid_form).get_data(as_text=True)
    assert extract_csrf_token(html)  # user can simply resubmit
    assert 'value="Jane Doe"' in html


# --- Honeypot ------------------------------------------------------------------


def test_honeypot_filled_pretends_success_but_sends_nothing(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    valid_form["website"] = "http://spam.example"
    with caplog.at_level(logging.INFO):
        response = client.post("/contact", data=valid_form, follow_redirects=True)
    assert response.status_code == 200
    assert "flash-success" in response.get_data(as_text=True)
    assert mailer.sent == []
    assert "honeypot" in caplog.text.lower()


def test_honeypot_does_not_consume_rate_limit(
    client: FlaskClient, app: Flask, mailer: RecordingMailer, valid_form: dict[str, str]
) -> None:
    limiter = app.extensions["rate_limiter"]
    valid_form["website"] = "spam"
    for _ in range(5):
        client.post("/contact", data=valid_form)
    assert limiter.remaining("127.0.0.1") == app.config["CONTACT_RATE_LIMIT"]


# --- Rate limiting -------------------------------------------------------------


def test_rate_limit_blocks_excess_submissions(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str], app: Flask
) -> None:
    limit = app.config["CONTACT_RATE_LIMIT"]
    for _ in range(limit):
        assert client.post("/contact", data=valid_form).status_code == 302
    response = client.post("/contact", data=valid_form)
    assert response.status_code == 429
    assert str(escape(RATE_LIMIT_ERROR)) in response.get_data(as_text=True)
    assert len(mailer.sent) == limit


def test_rate_limit_is_per_client_address(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str], app: Flask
) -> None:
    limit = app.config["CONTACT_RATE_LIMIT"]
    for _ in range(limit):
        client.post("/contact", data=valid_form)
    assert client.post("/contact", data=valid_form).status_code == 429
    # A different IP with its own session is unaffected.
    response = client.post("/contact", data=valid_form, environ_overrides={"REMOTE_ADDR": "10.0.0.9"})
    assert response.status_code == 302


def test_invalid_submissions_do_not_count_against_rate_limit(
    client: FlaskClient, app: Flask, valid_form: dict[str, str]
) -> None:
    limiter = app.extensions["rate_limiter"]
    bad = dict(valid_form, email="nope")
    for _ in range(10):
        client.post("/contact", data=bad)
    assert limiter.remaining("127.0.0.1") == app.config["CONTACT_RATE_LIMIT"]


def test_rate_limit_can_be_disabled(app_config: dict[str, Any], mailer: RecordingMailer) -> None:
    from resumeapp import create_app

    app_config["CONTACT_RATE_LIMIT"] = 0
    client = create_app(app_config, mailer=mailer).test_client()
    token = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    data = {"csrf_token": token, "name": "Bob", "email": "bob@example.com", "message": "Hello Alex, nice CV!"}
    for _ in range(20):
        assert client.post("/contact", data=data).status_code == 302
    assert len(mailer.sent) == 20


# --- Delivery failures ---------------------------------------------------------


def test_mail_delivery_failure_returns_503_with_friendly_message(
    client: FlaskClient, mailer: RecordingMailer, valid_form: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    mailer.fail_with = MailDeliveryError("connection refused")
    with caplog.at_level(logging.ERROR):
        response = client.post("/contact", data=valid_form)
    assert response.status_code == 503
    html = response.get_data(as_text=True)
    assert DELIVERY_ERROR in html
    assert 'value="Jane Doe"' in html  # user keeps their input
    assert "Failed to deliver contact form email" in caplog.text


def test_unexpected_mailer_exception_propagates_as_500(
    app: Flask, mailer: RecordingMailer, valid_form: dict[str, str]
) -> None:
    """Non-delivery errors are bugs and should surface (Flask turns them into 500)."""
    mailer.fail_with = RuntimeError("boom")
    app.testing = False  # let Flask convert the exception into a 500 response
    client = app.test_client()
    token = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    valid_form["csrf_token"] = token
    response = client.post("/contact", data=valid_form)
    assert response.status_code == 500
    assert 'class="error-code">500<' in response.get_data(as_text=True)


# --- Method handling -----------------------------------------------------------


def test_contact_rejects_unsupported_methods(client: FlaskClient) -> None:
    assert client.put("/contact").status_code == 405
    assert client.delete("/contact").status_code == 405


def test_oversized_payload_is_rejected(client: FlaskClient, csrf_token: str, mailer: RecordingMailer) -> None:
    data = {"csrf_token": csrf_token, "name": "Bob", "email": "bob@example.com", "message": "x" * 200_000}
    response = client.post("/contact", data=data)
    assert response.status_code == 413
    assert mailer.sent == []

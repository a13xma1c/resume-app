"""Tests for environment-driven configuration."""

from __future__ import annotations

import pytest

from resumeapp.config import DEFAULT_PDF_PATH, load_config, parse_bool, parse_int
from resumeapp.cv_data import CV_DATA


# --- parsers -------------------------------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on", "On"])
def test_parse_bool_truthy(value):
    assert parse_bool(value) is True


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", ""])
def test_parse_bool_falsy(value):
    assert parse_bool(value, default=True) is False


def test_parse_bool_none_uses_default():
    assert parse_bool(None) is False
    assert parse_bool(None, default=True) is True


def test_parse_bool_passthrough_and_invalid():
    assert parse_bool(True) is True
    assert parse_bool(False) is False
    with pytest.raises(ValueError, match="Invalid boolean"):
        parse_bool("maybe")


def test_parse_int():
    assert parse_int(None, 7) == 7
    assert parse_int("", 7) == 7
    assert parse_int(" 42 ", 7) == 42
    assert parse_int(5, 7) == 5
    with pytest.raises(ValueError, match="Invalid integer"):
        parse_int("abc", 7)
    with pytest.raises(ValueError, match="below the minimum"):
        parse_int("-1", 7, minimum=0)
    assert parse_int("0", 7, minimum=0) == 0


# --- load_config ---------------------------------------------------------------


def test_defaults_when_environment_is_empty():
    cfg = load_config({})
    assert cfg["SECRET_KEY"] and cfg["SECRET_KEY_IS_EPHEMERAL"] is True
    assert cfg["CV_PDF_PATH"] == str(DEFAULT_PDF_PATH)
    assert cfg["CONTACT_RECIPIENT"] == CV_DATA["personal"]["email"]
    assert cfg["CONTACT_SUBJECT_PREFIX"] == "[CV Contact]"
    assert cfg["CONTACT_RATE_LIMIT"] == 5
    assert cfg["CONTACT_RATE_WINDOW"] == 3600
    assert cfg["CSRF_ENABLED"] is True
    assert cfg["MAIL_SERVER"] is None
    assert cfg["MAIL_PORT"] == 587
    assert cfg["MAIL_USE_TLS"] is True
    assert cfg["MAIL_USE_SSL"] is False
    assert cfg["MAIL_USERNAME"] is None
    assert cfg["MAIL_PASSWORD"] is None
    assert cfg["MAIL_DEFAULT_SENDER"] == "no-reply@localhost"
    assert cfg["MAIL_SUPPRESS_SEND"] is False
    assert cfg["MAIL_TIMEOUT"] == 10
    assert cfg["SESSION_COOKIE_HTTPONLY"] is True
    assert cfg["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert cfg["MAX_CONTENT_LENGTH"] == 64 * 1024


def test_ephemeral_secret_keys_differ_between_loads():
    assert load_config({})["SECRET_KEY"] != load_config({})["SECRET_KEY"]


def test_full_environment_is_honoured():
    env = {
        "SECRET_KEY": "s3cret",
        "CV_PDF_PATH": "/tmp/cv.pdf",
        "CONTACT_RECIPIENT": "me@example.com",
        "CONTACT_SUBJECT_PREFIX": "[Hire me]",
        "CONTACT_RATE_LIMIT": "10",
        "CONTACT_RATE_WINDOW": "120",
        "CSRF_ENABLED": "false",
        "MAIL_SERVER": "smtp.example.com",
        "MAIL_PORT": "2525",
        "MAIL_USERNAME": "smtp-user",
        "MAIL_PASSWORD": "smtp-pass",
        "MAIL_USE_TLS": "false",
        "MAIL_DEFAULT_SENDER": "cv@example.com",
        "MAIL_SUPPRESS_SEND": "1",
        "MAIL_TIMEOUT": "30",
    }
    cfg = load_config(env)
    assert cfg["SECRET_KEY"] == "s3cret"
    assert cfg["SECRET_KEY_IS_EPHEMERAL"] is False
    assert cfg["CV_PDF_PATH"] == "/tmp/cv.pdf"
    assert cfg["CONTACT_RECIPIENT"] == "me@example.com"
    assert cfg["CONTACT_SUBJECT_PREFIX"] == "[Hire me]"
    assert cfg["CONTACT_RATE_LIMIT"] == 10
    assert cfg["CONTACT_RATE_WINDOW"] == 120
    assert cfg["CSRF_ENABLED"] is False
    assert cfg["MAIL_SERVER"] == "smtp.example.com"
    assert cfg["MAIL_PORT"] == 2525
    assert cfg["MAIL_USERNAME"] == "smtp-user"
    assert cfg["MAIL_PASSWORD"] == "smtp-pass"
    assert cfg["MAIL_USE_TLS"] is False
    assert cfg["MAIL_DEFAULT_SENDER"] == "cv@example.com"
    assert cfg["MAIL_SUPPRESS_SEND"] is True
    assert cfg["MAIL_TIMEOUT"] == 30


def test_ssl_implies_port_465_and_disables_starttls():
    cfg = load_config({"MAIL_USE_SSL": "true"})
    assert cfg["MAIL_USE_SSL"] is True
    assert cfg["MAIL_USE_TLS"] is False
    assert cfg["MAIL_PORT"] == 465


def test_explicit_port_wins_over_ssl_default():
    cfg = load_config({"MAIL_USE_SSL": "true", "MAIL_PORT": "8465"})
    assert cfg["MAIL_PORT"] == 8465


def test_default_sender_falls_back_to_username():
    cfg = load_config({"MAIL_USERNAME": "alex@example.com"})
    assert cfg["MAIL_DEFAULT_SENDER"] == "alex@example.com"


def test_empty_strings_are_treated_as_unset():
    cfg = load_config({"MAIL_SERVER": "", "MAIL_USERNAME": "", "SECRET_KEY": "", "CONTACT_RECIPIENT": ""})
    assert cfg["MAIL_SERVER"] is None
    assert cfg["MAIL_USERNAME"] is None
    assert cfg["SECRET_KEY_IS_EPHEMERAL"] is True
    assert cfg["CONTACT_RECIPIENT"] == CV_DATA["personal"]["email"]


def test_empty_subject_prefix_is_allowed():
    assert load_config({"CONTACT_SUBJECT_PREFIX": ""})["CONTACT_SUBJECT_PREFIX"] == ""


@pytest.mark.parametrize(
    "env",
    [
        {"CONTACT_RATE_LIMIT": "-1"},
        {"CONTACT_RATE_WINDOW": "0"},
        {"MAIL_PORT": "not-a-port"},
        {"MAIL_USE_TLS": "sometimes"},
        {"MAIL_TIMEOUT": "0"},
    ],
)
def test_invalid_values_raise(env):
    with pytest.raises(ValueError):
        load_config(env)


def test_load_config_reads_os_environ_by_default(monkeypatch):
    monkeypatch.setenv("CONTACT_RECIPIENT", "env@example.com")
    assert load_config()["CONTACT_RECIPIENT"] == "env@example.com"

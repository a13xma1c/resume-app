"""Application configuration loaded from environment variables.

All settings have sensible defaults so the app runs out of the box. Email
delivery is only enabled when ``MAIL_SERVER`` is set; otherwise contact-form
messages are logged instead of sent.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .cv_data import CV_DATA

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PDF_PATH = BASE_DIR / "Alex Maican - CV.pdf"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off", ""}


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    """Parse a boolean-ish environment variable value."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def parse_int(value: str | int | None, default: int, *, minimum: int | None = None) -> int:
    """Parse an integer environment variable value, enforcing an optional minimum."""
    if value is None or value == "":
        result = default
    elif isinstance(value, int):
        result = value
    else:
        try:
            result = int(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid integer value: {value!r}") from exc
    if minimum is not None and result < minimum:
        raise ValueError(f"Value {result} is below the minimum of {minimum}")
    return result


def load_config(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build the Flask config mapping from ``env`` (defaults to ``os.environ``)."""
    if env is None:
        env = os.environ

    secret_key = env.get("SECRET_KEY") or secrets.token_urlsafe(32)
    mail_username = env.get("MAIL_USERNAME") or None
    mail_use_ssl = parse_bool(env.get("MAIL_USE_SSL"), default=False)
    mail_use_tls = parse_bool(env.get("MAIL_USE_TLS"), default=not mail_use_ssl)

    return {
        "SECRET_KEY": secret_key,
        "SECRET_KEY_IS_EPHEMERAL": not env.get("SECRET_KEY"),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "MAX_CONTENT_LENGTH": 64 * 1024,  # contact form payloads are small
        # --- CV assets -------------------------------------------------------
        "CV_PDF_PATH": env.get("CV_PDF_PATH") or str(DEFAULT_PDF_PATH),
        # --- Contact form ----------------------------------------------------
        "CONTACT_RECIPIENT": env.get("CONTACT_RECIPIENT") or CV_DATA["personal"]["email"],
        "CONTACT_SUBJECT_PREFIX": env.get("CONTACT_SUBJECT_PREFIX", "[CV Contact]"),
        "CONTACT_RATE_LIMIT": parse_int(env.get("CONTACT_RATE_LIMIT"), 5, minimum=0),
        "CONTACT_RATE_WINDOW": parse_int(env.get("CONTACT_RATE_WINDOW"), 3600, minimum=1),
        "CSRF_ENABLED": parse_bool(env.get("CSRF_ENABLED"), default=True),
        # --- Mail transport --------------------------------------------------
        "MAIL_SERVER": env.get("MAIL_SERVER") or None,
        "MAIL_PORT": parse_int(env.get("MAIL_PORT"), 465 if mail_use_ssl else 587, minimum=1),
        "MAIL_USERNAME": mail_username,
        "MAIL_PASSWORD": env.get("MAIL_PASSWORD") or None,
        "MAIL_USE_TLS": mail_use_tls,
        "MAIL_USE_SSL": mail_use_ssl,
        "MAIL_TIMEOUT": parse_int(env.get("MAIL_TIMEOUT"), 10, minimum=1),
        "MAIL_DEFAULT_SENDER": env.get("MAIL_DEFAULT_SENDER") or mail_username or "no-reply@localhost",
        "MAIL_SUPPRESS_SEND": parse_bool(env.get("MAIL_SUPPRESS_SEND"), default=False),
    }

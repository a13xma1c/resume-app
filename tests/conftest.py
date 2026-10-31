"""Shared pytest fixtures for the resume app test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from resumeapp import create_app

from .helpers import RecordingMailer, extract_csrf_token


@pytest.fixture
def mailer() -> RecordingMailer:
    return RecordingMailer()


@pytest.fixture
def pdf_file(tmp_path: Path) -> Path:
    """A minimal (but real) PDF file to serve in download/view tests."""
    path = tmp_path / "cv.pdf"
    path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
    return path


@pytest.fixture
def app_config(pdf_file: Path) -> dict:
    return {
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "CV_PDF_PATH": str(pdf_file),
        "CONTACT_RECIPIENT": "owner@example.com",
        "MAIL_DEFAULT_SENDER": "noreply@example.com",
        "CONTACT_RATE_LIMIT": 3,
        "CONTACT_RATE_WINDOW": 60,
    }


@pytest.fixture
def app(app_config: dict, mailer: RecordingMailer) -> Flask:
    return create_app(app_config, mailer=mailer)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def csrf_token(client: FlaskClient) -> str:
    """Load the contact page (establishing a session) and return its CSRF token."""
    response = client.get("/contact")
    assert response.status_code == 200
    return extract_csrf_token(response.get_data(as_text=True))


@pytest.fixture
def valid_form(csrf_token: str) -> dict[str, str]:
    return {
        "csrf_token": csrf_token,
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "subject": "Senior Data Engineer opportunity",
        "message": "Hi Alex, I'd love to talk to you about a role on our data platform team.",
        "website": "",
    }


__all__ = ["extract_csrf_token"]

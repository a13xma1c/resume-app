"""Fixtures for Playwright end-to-end tests.

A real Flask server and a real SMTP server are started once per session, so
the browser drives the complete stack: HTML → form POST → SMTPMailer → SMTP.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from resumeapp import create_app
from resumeapp.smtp_server import DevSMTPServer

from ..live_server import LiveServer


@pytest.fixture(scope="session")
def e2e_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("pdf") / "cv.pdf"
    path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
    return path


@pytest.fixture(scope="session")
def smtp_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[DevSMTPServer]:
    with DevSMTPServer(port=0, maildir=tmp_path_factory.mktemp("outbox")) as server:
        yield server


@pytest.fixture(scope="session")
def live_server(smtp_server: DevSMTPServer, e2e_pdf: Path) -> Iterator[LiveServer]:
    app = create_app(
        {
            "SECRET_KEY": "e2e-secret",
            "CV_PDF_PATH": str(e2e_pdf),
            "CONTACT_RECIPIENT": "owner@example.com",
            "MAIL_DEFAULT_SENDER": "noreply@example.com",
            "CONTACT_RATE_LIMIT": 0,
            **smtp_server.mail_config(),
        }
    )
    with LiveServer(app) as server:
        yield server


@pytest.fixture(scope="session")
def base_url(live_server: LiveServer) -> str:
    """Feed the live server's address to pytest-playwright's ``base_url``."""
    return live_server.url


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
        "permissions": ["clipboard-read", "clipboard-write"],
        "locale": "en-GB",
    }


@pytest.fixture(autouse=True)
def clean_mailbox(smtp_server: DevSMTPServer) -> Iterator[None]:
    smtp_server.clear()
    yield
    smtp_server.clear()

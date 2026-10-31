"""Helpers shared between test modules."""

from __future__ import annotations

import re
from email.message import EmailMessage

CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def extract_csrf_token(html: str) -> str:
    match = CSRF_RE.search(html)
    assert match, "CSRF token not found in page"
    return match.group(1)


class RecordingMailer:
    """Test double that records sent messages and can be told to fail."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail_with: Exception | None = None

    def send(self, message: EmailMessage) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(message)

    @property
    def last(self) -> EmailMessage:
        assert self.sent, "no email was sent"
        return self.sent[-1]

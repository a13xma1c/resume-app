"""Contact form model and validation (dependency-free)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields

NAME_MIN, NAME_MAX = 2, 100
SUBJECT_MAX = 150
MESSAGE_MIN, MESSAGE_MAX = 10, 5000
EMAIL_MAX = 254

# Pragmatic email check: one "@", no whitespace, a dot in the domain part.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_LINE_BREAK_RE = re.compile(r"[\r\n]")
_HONEYPOT_FIELD = "website"


@dataclass
class ContactForm:
    """A submitted contact form.

    ``website`` is a honeypot: it is visually hidden in the UI and real users
    never fill it in, so any value there marks the submission as spam.
    """

    name: str = ""
    email: str = ""
    subject: str = ""
    message: str = ""
    website: str = ""
    errors: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    @classmethod
    def from_mapping(cls, data: Mapping[str, str]) -> ContactForm:
        """Build a form from request data, trimming surrounding whitespace."""
        values = {}
        for f in fields(cls):
            if not f.init:
                continue
            raw = data.get(f.name, "")
            values[f.name] = (raw if isinstance(raw, str) else str(raw)).strip()
        return cls(**values)

    @property
    def is_spam(self) -> bool:
        return bool(self.website)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def validate(self) -> bool:
        """Validate all fields, populating ``errors``. Returns True when valid."""
        errors: dict[str, str] = {}

        if not self.name:
            errors["name"] = "Please enter your name."
        elif len(self.name) < NAME_MIN:
            errors["name"] = f"Name must be at least {NAME_MIN} characters."
        elif len(self.name) > NAME_MAX:
            errors["name"] = f"Name must be at most {NAME_MAX} characters."
        elif _LINE_BREAK_RE.search(self.name):
            errors["name"] = "Name cannot contain line breaks."

        if not self.email:
            errors["email"] = "Please enter your email address."
        elif len(self.email) > EMAIL_MAX or not _EMAIL_RE.match(self.email):
            errors["email"] = "Please enter a valid email address."

        if len(self.subject) > SUBJECT_MAX:
            errors["subject"] = f"Subject must be at most {SUBJECT_MAX} characters."
        elif _LINE_BREAK_RE.search(self.subject):
            errors["subject"] = "Subject cannot contain line breaks."

        if not self.message:
            errors["message"] = "Please enter a message."
        elif len(self.message) < MESSAGE_MIN:
            errors["message"] = f"Message must be at least {MESSAGE_MIN} characters."
        elif len(self.message) > MESSAGE_MAX:
            errors["message"] = f"Message must be at most {MESSAGE_MAX} characters."

        self.errors = errors
        return not errors

    def as_dict(self) -> dict[str, str]:
        """Public field values (excluding the honeypot), e.g. for re-rendering."""
        return {
            "name": self.name,
            "email": self.email,
            "subject": self.subject,
            "message": self.message,
        }

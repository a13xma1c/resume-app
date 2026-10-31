"""Unit tests for ContactForm validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from resumeapp.forms import (
    EMAIL_MAX,
    MESSAGE_MAX,
    MESSAGE_MIN,
    NAME_MAX,
    NAME_MIN,
    SUBJECT_MAX,
    ContactForm,
)


def make_form(**overrides: str) -> ContactForm:
    data = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "subject": "Hello",
        "message": "This is a sufficiently long message.",
        "website": "",
    }
    data.update(overrides)
    return ContactForm.from_mapping(data)


def test_valid_form_has_no_errors() -> None:
    form = make_form()
    assert form.validate() is True
    assert form.errors == {}
    assert form.is_valid
    assert not form.is_spam


def test_from_mapping_strips_whitespace_and_ignores_unknown_keys() -> None:
    form = ContactForm.from_mapping(
        {"name": "  Jane  ", "email": "\tjane@example.com\n", "message": " hi there friend ", "bogus": "x"}
    )
    assert form.name == "Jane"
    assert form.email == "jane@example.com"
    assert form.message == "hi there friend"
    assert form.subject == ""
    assert not hasattr(form, "bogus")


def test_from_mapping_coerces_non_string_values() -> None:
    form = ContactForm.from_mapping(cast("Mapping[str, str]", {"name": 12345, "email": None}))
    assert form.name == "12345"
    assert form.email == "None"  # validated (and rejected) later


def test_from_mapping_with_empty_mapping() -> None:
    form = ContactForm.from_mapping({})
    assert form.validate() is False
    assert set(form.errors) == {"name", "email", "message"}


@pytest.mark.parametrize(
    "name,error_fragment",
    [
        ("", "enter your name"),
        ("  ", "enter your name"),
        ("A", f"at least {NAME_MIN}"),
        ("A" * (NAME_MAX + 1), f"at most {NAME_MAX}"),
        ("Jane\nDoe", "line breaks"),
        ("Jane\rDoe", "line breaks"),
    ],
)
def test_name_validation(name: str, error_fragment: str) -> None:
    form = make_form(name=name)
    assert form.validate() is False
    assert error_fragment in form.errors["name"]


@pytest.mark.parametrize("name", ["Jo", "Zoë Müller", "A" * NAME_MAX, "O'Brien-Smith Jr."])
def test_name_accepts_reasonable_values(name: str) -> None:
    form = make_form(name=name)
    assert form.validate(), form.errors


@pytest.mark.parametrize(
    "email",
    [
        "",
        "plain",
        "missing@tld",
        "@example.com",
        "user@",
        "user @example.com",
        "user@exa mple.com",
        "user@@example.com",
        "a@b.c",  # TLD too short
        "x" * (EMAIL_MAX - 10) + "@example.com",  # too long
        "user@example.com\nBcc: evil@example.com",
    ],
)
def test_email_rejects_invalid_addresses(email: str) -> None:
    form = make_form(email=email)
    assert form.validate() is False
    assert "email" in form.errors


@pytest.mark.parametrize(
    "email",
    [
        "jane@example.com",
        "jane.doe+tag@sub.example.co.uk",
        "JANE@EXAMPLE.COM",
        "o'brien@example.io",
        "user_name-1@example-domain.org",
    ],
)
def test_email_accepts_valid_addresses(email: str) -> None:
    form = make_form(email=email)
    assert form.validate(), form.errors


def test_subject_is_optional() -> None:
    form = make_form(subject="")
    assert form.validate()


def test_subject_too_long() -> None:
    form = make_form(subject="s" * (SUBJECT_MAX + 1))
    assert not form.validate()
    assert f"at most {SUBJECT_MAX}" in form.errors["subject"]


def test_subject_rejects_line_breaks() -> None:
    form = make_form(subject="Hi\r\nBcc: x@y.z")
    assert not form.validate()
    assert "line breaks" in form.errors["subject"]


@pytest.mark.parametrize(
    "message,error_fragment",
    [
        ("", "enter a message"),
        ("short", f"at least {MESSAGE_MIN}"),
        ("m" * (MESSAGE_MAX + 1), f"at most {MESSAGE_MAX}"),
    ],
)
def test_message_validation(message: str, error_fragment: str) -> None:
    form = make_form(message=message)
    assert not form.validate()
    assert error_fragment in form.errors["message"]


def test_message_boundaries_are_inclusive() -> None:
    assert make_form(message="m" * MESSAGE_MIN).validate()
    assert make_form(message="m" * MESSAGE_MAX).validate()


def test_message_may_contain_line_breaks() -> None:
    form = make_form(message="Line one\nLine two\r\nLine three, all good.")
    assert form.validate()


def test_honeypot_marks_spam_but_is_not_a_validation_error() -> None:
    form = make_form(website="http://spam.example")
    assert form.is_spam
    assert form.validate()  # still "valid" so bots can't detect the trap


def test_validate_resets_previous_errors() -> None:
    form = make_form(name="")
    assert not form.validate()
    form.name = "Jane"
    assert form.validate()
    assert form.errors == {}


def test_as_dict_excludes_honeypot_and_errors() -> None:
    form = make_form(website="bot")
    assert form.as_dict() == {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "subject": "Hello",
        "message": "This is a sufficiently long message.",
    }


def test_repr_does_not_leak_errors_field() -> None:
    form = make_form()
    assert "errors" not in repr(form)

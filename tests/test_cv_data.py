"""Sanity checks on the structured CV data that every page is rendered from."""

from __future__ import annotations

import json
import re

import pytest

from resumeapp.cv_data import CV_DATA, Certification, Education, Experience

PERIOD_RE = re.compile(r"^[A-Z][a-z]{2} \d{4} - ([A-Z][a-z]{2} \d{4}|Present)$")


def test_top_level_sections_present() -> None:
    assert set(CV_DATA) == {"personal", "skills", "languages", "experience", "education", "certifications", "courses"}


def test_data_is_json_serialisable() -> None:
    json.dumps(CV_DATA)


def test_personal_fields() -> None:
    personal = CV_DATA["personal"]
    for key in ("name", "title", "location", "email", "phone", "linkedin", "linkedin_display", "summary", "highlights"):
        assert personal.get(key), f"personal.{key} is missing or empty"
    assert "@" in personal["email"]
    assert personal["linkedin"].startswith("https://")
    assert personal["linkedin_display"] in personal["linkedin"]
    assert len(personal["highlights"]) == 4
    for item in personal["highlights"]:
        assert set(item) == {"label", "value", "desc"}


@pytest.mark.parametrize("exp", CV_DATA["experience"], ids=lambda e: e["company"])
def test_experience_entries_are_well_formed(exp: Experience) -> None:
    for key in ("role", "company", "location", "period", "key_technologies", "responsibilities"):
        assert exp.get(key), f"{key} missing"
    assert isinstance(exp["is_current"], bool)
    assert PERIOD_RE.match(exp["period"]), exp["period"]
    assert len(exp["key_technologies"]) == len(set(exp["key_technologies"])), "duplicate tech"
    assert all(r.strip() for r in exp["responsibilities"])


def test_exactly_one_current_role_and_it_is_first() -> None:
    current = [e for e in CV_DATA["experience"] if e["is_current"]]
    assert len(current) == 1
    assert CV_DATA["experience"][0] is current[0]
    assert current[0]["period"].endswith("Present")


def test_experience_is_in_reverse_chronological_order() -> None:
    def start_year(exp: Experience) -> int:
        return int(exp["period"].split(" - ")[0].split()[1])

    years = [start_year(e) for e in CV_DATA["experience"]]
    assert years == sorted(years, reverse=True)


def test_skills_have_no_empty_categories_or_duplicates() -> None:
    for category, items in CV_DATA["skills"].items():
        assert category.strip() and items
        assert len(items) == len(set(items)), f"duplicate skill in {category}"


@pytest.mark.parametrize("edu", CV_DATA["education"], ids=lambda e: e["institution"])
def test_education_entries(edu: Education) -> None:
    assert set(edu) == {"degree", "institution", "location", "period"}
    assert all(edu.values())


@pytest.mark.parametrize("cert", CV_DATA["certifications"], ids=lambda c: c["badge"])
def test_certification_entries(cert: Certification) -> None:
    assert set(cert) == {"title", "issuer", "date", "badge"}
    assert all(cert.values())


def test_languages_and_courses() -> None:
    assert {lang["name"] for lang in CV_DATA["languages"]} == {"English", "French", "Romanian"}
    assert all(lang["level"] for lang in CV_DATA["languages"])
    assert len(CV_DATA["courses"]) == len(set(CV_DATA["courses"])) > 0

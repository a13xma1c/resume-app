"""Browser tests for the experience filter and cross-page tag deep links."""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from resumeapp.cv_data import CV_DATA

ROLE_COUNT = len(CV_DATA["experience"])


def matching_roles(query: str) -> list[str]:
    """Companies whose timeline item matches ``query`` (mirrors the logic in main.js)."""
    q = query.lower()
    matches = []
    for exp in CV_DATA["experience"]:
        haystack = " ".join(
            [
                exp["role"],
                exp["company"],
                exp["location"],
                exp["period"],
                *exp["key_technologies"],
                *exp["responsibilities"],
            ]
        ).lower()
        if q in haystack:
            matches.append(exp["company"])
    return matches


def visible_roles(page: Page) -> int:
    return page.locator(".timeline-item:visible").count()


def test_all_roles_visible_initially(page: Page) -> None:
    page.goto("/experience")
    expect(page.locator(".timeline-item")).to_have_count(ROLE_COUNT)
    assert visible_roles(page) == ROLE_COUNT
    expect(page.locator("#experience-empty")).to_be_hidden()


def test_typing_filters_roles_and_updates_url(page: Page) -> None:
    page.goto("/experience")
    assert matching_roles("BigQuery") == ["eMAG"]
    page.fill("#exp-filter-input", "BigQuery")
    expect(page.locator(".timeline-item:visible")).to_have_count(1)
    expect(page.locator(".timeline-item:visible .exp-company")).to_have_text("eMAG")
    expect(page).to_have_url(re.compile(r"/experience\?q=BigQuery$"))

    page.fill("#exp-filter-input", "")
    expect(page.locator(".timeline-item:visible")).to_have_count(ROLE_COUNT)
    expect(page).to_have_url(re.compile(r"/experience$"))


def test_filter_is_case_insensitive_and_matches_free_text(page: Page) -> None:
    page.goto("/experience")
    assert matching_roles("soap protocol") == ["alfrednet"]
    page.fill("#exp-filter-input", "soap PROTOCOL")
    expect(page.locator(".timeline-item:visible")).to_have_count(1)
    expect(page.locator(".timeline-item:visible .exp-company")).to_have_text("alfrednet")


def test_no_match_shows_empty_state(page: Page) -> None:
    page.goto("/experience")
    page.fill("#exp-filter-input", "cobol-mainframe-xyz")
    expect(page.locator(".timeline-item:visible")).to_have_count(0)
    expect(page.locator("#experience-empty")).to_be_visible()
    expect(page.locator("#experience-empty")).to_contain_text("No roles match")


def test_query_param_prefills_filter(page: Page) -> None:
    expected = matching_roles("Kafka")
    page.goto("/experience?q=Kafka")
    expect(page.locator("#exp-filter-input")).to_have_value("Kafka")
    expect(page.locator(".timeline-item:visible")).to_have_count(len(expected))
    expect(page.locator(".timeline-item:visible .exp-company")).to_have_text(expected)
    expect(page.locator("#toast")).to_contain_text(f'Filtered for: "Kafka" ({len(expected)} matching roles)')


def test_clicking_a_tag_filters_and_clicking_again_clears(page: Page) -> None:
    page.goto("/experience")
    expected = matching_roles("Scala")
    assert 1 < len(expected) < ROLE_COUNT, "need a tag that matches some but not all roles"
    tag = page.locator(".quick-filters .tech-tag", has_text="Scala").first
    tag.click()
    expect(page.locator("#exp-filter-input")).to_have_value("Scala")
    expect(page.locator(".timeline-item:visible")).to_have_count(len(expected))
    expect(page.locator(".timeline-item:visible .exp-company")).to_have_text(expected)
    expect(page.locator("#toast")).to_contain_text(f"{len(expected)} matching roles")

    tag.click()
    expect(page.locator("#exp-filter-input")).to_have_value("")
    expect(page.locator(".timeline-item:visible")).to_have_count(ROLE_COUNT)
    expect(page.locator("#toast")).to_contain_text("Cleared filter")


def test_tags_are_keyboard_operable(page: Page) -> None:
    page.goto("/experience")
    tag = page.locator(".quick-filters .tech-tag", has_text="Terraform").first
    tag.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#exp-filter-input")).to_have_value("Terraform")
    expect(page.locator(".timeline-item:visible")).to_have_count(len(matching_roles("Terraform")))


def test_skill_pill_on_skills_page_deep_links_to_experience(page: Page) -> None:
    page.goto("/skills")
    page.locator(".skill-pill", has_text="Apache Kafka").click()
    expect(page).to_have_url(re.compile(r"/experience\?q=Apache%20Kafka$"))
    expect(page.locator("#exp-filter-input")).to_have_value("Apache Kafka")
    expect(page.locator(".timeline-item:visible")).to_have_count(len(matching_roles("Apache Kafka")))


def test_tech_tag_on_home_page_deep_links_to_experience(page: Page) -> None:
    page.goto("/")
    page.locator(".section-current-role .tech-tag", has_text="Snowflake").click()
    expect(page).to_have_url(re.compile(r"/experience\?q=Snowflake$"))
    expect(page.locator(".timeline-item:visible .exp-company")).to_have_text(matching_roles("Snowflake"))


def test_full_cv_page_filter_works_too(page: Page) -> None:
    page.goto("/cv")
    page.fill("#exp-filter-input", "GCP")
    expect(page.locator(".timeline-item:visible")).to_have_count(len(matching_roles("GCP")))
    expect(page).to_have_url(re.compile(r"/cv\?q=GCP$"))

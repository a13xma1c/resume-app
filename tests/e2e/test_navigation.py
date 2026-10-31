"""Browser tests for navigation, theming and the shared layout."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import ConsoleMessage, Page, expect

from resumeapp.cv_data import CV_DATA

PAGES = [
    ("/", "Home", "Alex Maican - Big Data Engineer"),
    ("/experience", "Experience", "Experience - Alex Maican"),
    ("/skills", "Skills", "Skills - Alex Maican"),
    ("/education", "Education", "Education & Certifications - Alex Maican"),
    ("/cv", "Full CV", "Full CV - Alex Maican"),
    ("/contact", "Contact", "Contact - Alex Maican"),
]


@pytest.mark.parametrize("path,label,title", PAGES)
def test_page_loads_with_title_and_active_nav(page: Page, path: str, label: str, title: str) -> None:
    page.goto(path)
    expect(page).to_have_title(title)
    active = page.locator("nav .nav-link.active")
    expect(active).to_have_count(1)
    expect(active).to_have_text(label)
    expect(active).to_have_attribute("aria-current", "page")


def test_clicking_through_the_nav_visits_every_page(page: Page, base_url: str) -> None:
    page.goto("/")
    for path, label, title in PAGES[1:]:
        page.get_by_role("navigation").get_by_role("link", name=label, exact=True).click()
        expect(page).to_have_url(f"{base_url}{path}")
        expect(page).to_have_title(title)


def test_home_calls_to_action(page: Page) -> None:
    page.goto("/")
    expect(page.get_by_role("heading", level=1)).to_have_text(CV_DATA["personal"]["name"])
    page.get_by_role("link", name="View full CV").click()
    expect(page).to_have_title("Full CV - Alex Maican")
    page.go_back()
    page.get_by_role("link", name="Get in touch").click()
    expect(page).to_have_title("Contact - Alex Maican")


def test_explore_cards_link_to_sections(page: Page) -> None:
    page.goto("/")
    cards = page.locator(".explore-card")
    expect(cards).to_have_count(4)
    cards.filter(has_text="Skills").click()
    expect(page).to_have_url(re.compile(r"/skills$"))


def test_theme_toggle_persists_across_reload_and_pages(page: Page) -> None:
    page.goto("/")
    html = page.locator("html")
    expect(html).to_have_attribute("data-theme", "light")

    page.locator("#theme-toggle").click()
    expect(html).to_have_attribute("data-theme", "dark")
    expect(page.locator("#toast")).to_have_class("toast show")
    expect(page.locator("#toast")).to_contain_text("dark mode")
    assert page.evaluate("localStorage.getItem('theme')") == "dark"

    page.reload()
    expect(html).to_have_attribute("data-theme", "dark")
    page.goto("/skills")
    expect(html).to_have_attribute("data-theme", "dark")

    page.locator("#theme-toggle").click()
    expect(html).to_have_attribute("data-theme", "light")
    assert page.evaluate("localStorage.getItem('theme')") == "light"


def test_dark_theme_changes_background_colour(page: Page) -> None:
    page.goto("/")
    body = page.locator("body")
    expect(body).to_have_css("background-color", "rgb(248, 250, 252)")  # --bg-page light (#f8fafc)
    page.locator("#theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(body).to_have_css("background-color", "rgb(11, 15, 25)")  # --bg-page dark (#0b0f19)


def test_system_dark_preference_is_respected(page: Page) -> None:
    page.emulate_media(color_scheme="dark")
    page.goto("/")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")


def test_mobile_navigation_menu(page: Page) -> None:
    page.set_viewport_size({"width": 420, "height": 800})
    page.goto("/")
    links = page.locator("#nav-links")
    toggle = page.locator("#nav-toggle")
    expect(toggle).to_be_visible()
    expect(links).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")

    toggle.click()
    expect(links).to_be_visible()
    expect(toggle).to_have_attribute("aria-expanded", "true")

    page.keyboard.press("Escape")
    expect(links).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")

    toggle.click()
    links.get_by_role("link", name="Contact", exact=True).click()
    expect(page).to_have_url(re.compile(r"/contact$"))


def test_desktop_hides_hamburger(page: Page) -> None:
    page.goto("/")
    expect(page.locator("#nav-toggle")).to_be_hidden()
    expect(page.locator("#nav-links")).to_be_visible()


def test_copy_button_writes_to_clipboard_and_shows_toast(page: Page, base_url: str) -> None:
    page.goto("/")
    email = CV_DATA["personal"]["email"]
    page.locator(f".copy-btn[data-copy='{email}']").first.click()
    expect(page.locator("#toast")).to_contain_text(email)
    assert page.evaluate("navigator.clipboard.readText()") == email
    # Clicking the copy button must not follow the surrounding mailto: link.
    expect(page).to_have_url(f"{base_url}/")


def test_pdf_download_link(page: Page) -> None:
    page.goto("/cv")
    with page.expect_download() as download_info:
        page.get_by_role("link", name="Download PDF").click()
    download = download_info.value
    assert download.suggested_filename == "Alex_Maican_CV.pdf"


def test_404_page_offers_way_back(page: Page) -> None:
    response = page.goto("/this-page-does-not-exist")
    assert response is not None and response.status == 404
    expect(page.locator(".error-code")).to_have_text("404")
    page.get_by_role("link", name="Back to home").click()
    expect(page).to_have_title("Alex Maican - Big Data Engineer")


def test_skip_link_targets_main_content(page: Page) -> None:
    page.goto("/")
    page.keyboard.press("Tab")
    skip = page.locator(".skip-link")
    expect(skip).to_be_focused()
    expect(skip).to_have_attribute("href", "#main-content")
    expect(page.locator("#main-content")).to_have_count(1)


def test_no_console_errors_on_any_page(page: Page) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    def on_console(msg: ConsoleMessage) -> None:
        # Google Fonts are a third-party nicety; ignore them when offline.
        if msg.type == "error" and "fonts.g" not in msg.location.get("url", ""):
            errors.append(f"{msg.location.get('url')}: {msg.text}")

    page.on("console", on_console)
    for path, _, _ in PAGES:
        page.goto(path)
    assert errors == []

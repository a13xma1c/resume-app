"""Browser tests for the page carousel, scroll reveal and micro-animations."""

from __future__ import annotations

import re
import sys

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

MARKER_JS = "window.__marker = 42"
MARKER_SURVIVES = "window.__marker === 42"


def nav_link(page: Page, label: str) -> Locator:
    return page.get_by_role("navigation").get_by_role("link", name=label, exact=True)


def wait_settled(page: Page, path: str | None = None) -> None:
    """Wait until the carousel shows ``path`` (if given) and no slide is in progress.

    Without ``path`` this could return *before* a just-started navigation has
    fetched anything, so callers that triggered a navigation must pass the
    destination.
    """
    page.wait_for_function(
        """(path) => {
            const stage = document.getElementById('main-content');
            const panels = stage.querySelectorAll('.page-panel');
            const here = path === null || (location.pathname === path && panels[0].dataset.pagePath === path);
            return here && !stage.classList.contains('is-animating') && panels.length === 1;
        }""",
        arg=path,
    )


# "Open in new tab" is Ctrl+click everywhere except macOS, where it is Cmd+click
# (Ctrl+click opens the context menu there).
NEW_TAB_MODIFIER = "Meta" if sys.platform == "darwin" else "Control"


# --- carousel navigation ---------------------------------------------------------


def test_nav_click_is_a_soft_navigation(page: Page, base_url: str) -> None:
    page.goto("/")
    page.evaluate(MARKER_JS)
    nav_link(page, "Skills").click()

    expect(page).to_have_url(f"{base_url}/skills")
    expect(page).to_have_title("Skills - Alex Maican")
    wait_settled(page, "/skills")
    expect(page.locator(".page-panel h1")).to_have_text("Skills & Expertise")
    assert page.evaluate(MARKER_SURVIVES), "page was fully reloaded instead of swapped in place"
    expect(page.locator(".page-panel")).to_have_attribute("data-page-path", "/skills")


def test_forward_navigation_slides_from_the_right(page: Page) -> None:
    page.goto("/")
    nav_link(page, "Education").click(no_wait_after=True)
    page.wait_for_function("() => document.getElementById('main-content').dataset.direction === 'forward'")
    stage = page.locator("#main-content")
    expect(stage).to_have_class(re.compile(r"\bis-animating\b"))
    expect(page.locator(".page-panel")).to_have_count(2)
    expect(page.locator(".page-panel.is-leaving")).to_have_attribute("data-page-path", "/")
    expect(page.locator(".page-panel.is-entering")).to_have_attribute("data-page-path", "/education")
    wait_settled(page, "/education")
    expect(stage).not_to_have_attribute("data-direction", re.compile(".+"))
    assert page.evaluate("document.getElementById('main-content').style.height") == ""


def test_backward_navigation_slides_from_the_left(page: Page) -> None:
    page.goto("/cv")
    nav_link(page, "Experience").click(no_wait_after=True)
    page.wait_for_function("() => document.getElementById('main-content').dataset.direction === 'backward'")
    expect(page.locator(".page-panel.is-entering")).to_have_class(re.compile(r"\bfrom-left\b"))
    expect(page.locator(".page-panel.is-leaving")).to_have_class(re.compile(r"\bto-right\b"))
    wait_settled(page, "/experience")
    expect(page).to_have_title("Experience - Alex Maican")


def test_incoming_panel_is_visible_while_sliding(page: Page) -> None:
    """Above-the-fold content must not wait for the scroll-reveal observer."""
    page.goto("/")
    nav_link(page, "Skills").click(no_wait_after=True)
    page.wait_for_selector(".page-panel.is-entering")
    heading = page.locator(".page-panel.is-entering .page-header")
    expect(heading).to_have_class(re.compile(r"\bis-visible\b"))
    expect(heading).to_have_class(re.compile(r"\breveal-instant\b"))
    wait_settled(page, "/skills")


def test_active_nav_link_and_indicator_follow_the_page(page: Page) -> None:
    page.goto("/")
    nav_link(page, "Contact").click()
    wait_settled(page, "/contact")
    active = page.locator(".nav-link.active")
    expect(active).to_have_count(1)
    expect(active).to_have_text("Contact")
    expect(active).to_have_attribute("aria-current", "page")
    page.wait_for_function(
        """() => {
            const a = document.querySelector('.nav-link.active');
            const i = document.querySelector('.nav-indicator');
            const x = new DOMMatrixReadOnly(getComputedStyle(i).transform).m41;
            return Math.abs(x - a.offsetLeft) < 1.5 && Math.abs(i.offsetWidth - a.offsetWidth) < 1.5
                && getComputedStyle(i).opacity === '1';
        }"""
    )


def test_browser_history_rolls_pages_back_and_forward(page: Page, base_url: str) -> None:
    page.goto("/")
    page.evaluate(MARKER_JS)
    nav_link(page, "Experience").click()
    wait_settled(page, "/experience")
    nav_link(page, "Skills").click()
    wait_settled(page, "/skills")

    page.go_back()
    expect(page).to_have_url(f"{base_url}/experience")
    expect(page).to_have_title("Experience - Alex Maican")
    wait_settled(page, "/experience")
    page.go_back()
    expect(page).to_have_url(f"{base_url}/")
    wait_settled(page, "/")
    expect(page.locator(".page-panel h1")).to_have_text("Alex Maican")
    page.go_forward()
    expect(page).to_have_url(f"{base_url}/experience")
    wait_settled(page, "/experience")
    assert page.evaluate(MARKER_SURVIVES), "history navigation caused a full reload"


def test_rapid_clicks_settle_on_the_last_page(page: Page, base_url: str) -> None:
    page.goto("/")
    nav_link(page, "Experience").click(no_wait_after=True)
    nav_link(page, "Education").click(no_wait_after=True)
    nav_link(page, "Contact").click(no_wait_after=True)
    expect(page).to_have_url(f"{base_url}/contact")
    wait_settled(page, "/contact")
    expect(page.locator(".page-panel")).to_have_count(1)
    expect(page.locator(".page-panel")).to_have_attribute("data-page-path", "/contact")
    expect(page.locator(".page-panel h1")).to_have_text("Get in Touch")


def test_swapped_in_pages_are_fully_interactive(page: Page) -> None:
    page.goto("/")
    nav_link(page, "Experience").click()
    wait_settled(page, "/experience")
    page.fill("#exp-filter-input", "BigQuery")
    expect(page.locator(".timeline-item:visible")).to_have_count(1)
    expect(page).to_have_url(re.compile(r"/experience\?q=BigQuery$"))

    nav_link(page, "Contact").click()
    wait_settled(page, "/contact")
    expect(page.locator("#message-counter")).to_have_text("0 / 5000")
    page.fill("#message", "hello")
    expect(page.locator("#message-counter")).to_have_text("5 / 5000")


def test_tag_on_home_rolls_to_filtered_experience(page: Page) -> None:
    page.goto("/")
    page.evaluate(MARKER_JS)
    page.locator(".section-current-role .tech-tag", has_text="Snowflake").click()
    expect(page).to_have_url(re.compile(r"/experience\?q=Snowflake$"))
    wait_settled(page, "/experience")
    expect(page.locator("#exp-filter-input")).to_have_value("Snowflake")
    assert page.evaluate(MARKER_SURVIVES)


def test_hovering_a_nav_link_prefetches_the_page(page: Page) -> None:
    page.goto("/")
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url) if r.url.endswith("/education") else None)
    with page.expect_request(lambda r: r.url.endswith("/education")) as prefetch:
        nav_link(page, "Education").hover()
    assert prefetch.value.headers.get("x-requested-with") == "carousel"
    nav_link(page, "Education").click()
    wait_settled(page, "/education")
    expect(page).to_have_title("Education & Certifications - Alex Maican")
    assert len(requests) == 1, "click should have used the prefetched page"


def test_modifier_click_opens_a_new_tab_normally(page: Page, base_url: str) -> None:
    page.goto("/")
    with page.context.expect_page() as popup_info:
        nav_link(page, "Skills").click(modifiers=[NEW_TAB_MODIFIER])  # type: ignore[list-item]
    popup = popup_info.value
    popup.wait_for_url(f"{base_url}/skills")
    expect(page).to_have_url(f"{base_url}/")  # original tab stayed put
    popup.close()


def test_reduced_motion_uses_plain_navigation(page: Page, base_url: str) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.goto("/")
    page.evaluate(MARKER_JS)
    nav_link(page, "Skills").click()
    expect(page).to_have_url(f"{base_url}/skills")
    expect(page).to_have_title("Skills - Alex Maican")
    assert not page.evaluate(MARKER_SURVIVES), "reduced-motion users should get a normal page load"
    # ...and everything is simply visible, no reveal animation pending.
    expect(page.locator("[data-reveal]").first).to_have_css("opacity", "1")


def test_non_page_links_fall_back_to_full_navigation(page: Page, base_url: str) -> None:
    page.goto("/")
    page.evaluate(MARKER_JS)
    page.evaluate("window.resumeApp.navigateTo('/does-not-exist')")
    page.wait_for_url(f"{base_url}/does-not-exist")
    expect(page.locator(".error-code")).to_have_text("404")
    assert not page.evaluate(MARKER_SURVIVES)


def test_mobile_menu_closes_after_rolling_to_a_page(page: Page) -> None:
    page.set_viewport_size({"width": 420, "height": 800})
    page.goto("/")
    page.locator("#nav-toggle").click()
    page.locator("#nav-links").get_by_role("link", name="Skills", exact=True).click()
    wait_settled(page, "/skills")
    expect(page.locator("#nav-links")).to_be_hidden()
    expect(page.locator("#nav-toggle")).to_have_attribute("aria-expanded", "false")
    expect(page).to_have_title("Skills - Alex Maican")


def test_touch_swipe_moves_to_neighbouring_page(browser: Browser, base_url: str) -> None:
    context = browser.new_context(base_url=base_url, has_touch=True, viewport={"width": 420, "height": 800})
    page = context.new_page()
    try:
        page.goto("/skills")
        page.evaluate(MARKER_JS)

        def swipe(from_x: int, to_x: int) -> None:
            page.evaluate(
                """([fromX, toX]) => {
                    const touch = (x) => new Touch({identifier: 1, target: document.body, clientX: x, clientY: 300});
                    const mk = (type, x) => new TouchEvent(type, {
                        bubbles: true,
                        touches: type === 'touchend' ? [] : [touch(x)],
                        changedTouches: [touch(x)],
                    });
                    document.body.dispatchEvent(mk('touchstart', fromX));
                    document.body.dispatchEvent(mk('touchend', toX));
                }""",
                [from_x, to_x],
            )

        swipe(350, 60)  # swipe left → next page
        expect(page).to_have_url(f"{base_url}/education")
        wait_settled(page, "/education")
        swipe(60, 350)  # swipe right → previous page
        expect(page).to_have_url(f"{base_url}/skills")
        wait_settled(page, "/skills")
        swipe(200, 170)  # too short to count
        page.wait_for_timeout(300)
        expect(page).to_have_url(f"{base_url}/skills")
        assert page.evaluate(MARKER_SURVIVES)
    finally:
        context.close()


# --- scroll reveal -----------------------------------------------------------------


def test_elements_reveal_as_they_scroll_into_view(page: Page) -> None:
    page.goto("/experience")
    items = page.locator(".timeline-item")
    first, last = items.first, items.last
    expect(first).to_have_class(re.compile(r"\bis-visible\b"))
    # The last role sits far below the fold and must still be hidden.
    assert "is-visible" not in (last.get_attribute("class") or "")
    expect(last).to_have_css("opacity", "0")

    last.scroll_into_view_if_needed()
    expect(last).to_have_class(re.compile(r"\bis-visible\b"))
    expect(last).to_have_css("opacity", "1")


def test_sibling_reveals_are_staggered(page: Page) -> None:
    page.goto("/")
    delays = page.eval_on_selector_all(
        ".explore-grid .explore-card", "els => els.map(e => e.style.getPropertyValue('--reveal-delay'))"
    )
    assert delays == ["0ms", "70ms", "140ms", "210ms"]


def test_reveal_does_not_block_hover_lift(page: Page) -> None:
    page.goto("/")
    card = page.locator(".explore-card").first
    card.scroll_into_view_if_needed()
    expect(card).to_have_class(re.compile(r"\bis-visible\b"))
    page.wait_for_timeout(1000)  # let the entrance animation finish
    card.hover()
    expect(card).to_have_css("transform", re.compile(r"matrix\(1, 0, 0, 1, 0, -3\)"))


def test_js_enabled_marker_and_failsafe_flag(page: Page) -> None:
    page.goto("/")
    expect(page.locator("html")).to_have_class(re.compile(r"\bjs-anim\b"))
    expect(page.locator("html")).to_have_class(re.compile(r"\bpage-loaded\b"))
    assert page.evaluate("window.__animReady") is True
    page.wait_for_timeout(2700)
    assert "anim-failsafe" not in page.evaluate("document.documentElement.className")


def test_failsafe_reveals_content_if_main_js_is_blocked(page: Page) -> None:
    page.route(re.compile(r"/static/js/main\.js(\?.*)?$"), lambda route: route.abort())
    page.goto("/")
    card = page.locator(".explore-card").first
    expect(card).to_have_css("opacity", "0")  # hidden, waiting for JS…
    expect(page.locator("html")).to_have_class(re.compile(r"\banim-failsafe\b"), timeout=5000)
    expect(card).to_have_css("opacity", "1")  # …then shown by the fail-safe


# --- micro-animations ----------------------------------------------------------------


def test_theme_toggle_spins_its_icon(page: Page) -> None:
    page.goto("/")
    toggle = page.locator("#theme-toggle")
    toggle.click()
    expect(toggle).to_have_class(re.compile(r"\bis-spinning\b"))


def test_copy_button_pops(page: Page) -> None:
    page.goto("/")
    btn = page.locator(".copy-btn").first
    btn.click()
    expect(btn).to_have_class(re.compile(r"\bis-copied\b"))


def test_current_role_marker_pulses(page: Page) -> None:
    page.goto("/experience")
    animation = page.evaluate(
        "getComputedStyle(document.querySelector('.marker-dot.active-marker'), '::after').animationName"
    )
    assert animation == "pulse-ring"


def test_print_styles_force_revealed_content(page: Page) -> None:
    page.goto("/experience")
    page.emulate_media(media="print")
    last = page.locator(".timeline-item").last
    expect(last).to_have_css("opacity", "1")


@pytest.mark.parametrize("path", ["/", "/experience", "/skills", "/education", "/cv", "/contact"])
def test_no_console_errors_during_carousel_navigation(page: Page, path: str) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto("/")
    page.evaluate(f"window.resumeApp.navigateTo('{path}')")
    expect(page).to_have_url(re.compile(re.escape(path) + "$"))
    wait_settled(page, path)
    assert errors == []


def test_navigation_is_announced_to_assistive_tech(page: Page) -> None:
    page.goto("/")
    announcer = page.locator("#route-announcer")
    expect(announcer).to_have_text("")
    nav_link(page, "Skills").click()
    wait_settled(page, "/skills")
    expect(announcer).to_have_text("Navigated to Skills - Alex Maican")
    # The stage itself is not a live region (that would read the whole page aloud).
    assert page.locator("#main-content").get_attribute("aria-live") is None


def test_back_restores_scroll_position(page: Page, base_url: str) -> None:
    page.goto("/experience")
    page.evaluate("window.scrollTo(0, 900)")
    page.wait_for_function("() => window.scrollY > 800")
    nav_link(page, "Skills").click()
    wait_settled(page, "/skills")
    assert page.evaluate("window.scrollY") == 0
    page.go_back()
    expect(page).to_have_url(f"{base_url}/experience")
    wait_settled(page, "/experience")
    page.wait_for_function("() => Math.abs(window.scrollY - 900) < 5")


def test_clicking_the_current_page_link_only_scrolls_to_top(page: Page) -> None:
    page.goto("/experience")
    page.evaluate("window.scrollTo(0, 600)")
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))
    nav_link(page, "Experience").click()
    page.wait_for_function("() => window.scrollY === 0")
    expect(page.locator(".page-panel")).to_have_count(1)
    assert not any(u.endswith("/experience") for u in requests), "same-page click must not re-fetch"


def test_print_button_triggers_print(page: Page) -> None:
    page.goto("/cv")
    # Wrap in a function: a bare expression that *evaluates to* a function would be invoked by Playwright.
    page.evaluate("() => { window.__printed = 0; window.print = () => { window.__printed++; }; }")
    page.get_by_role("button", name="Print").click()
    assert page.evaluate("window.__printed") == 1


def test_csp_does_not_block_site_scripts_or_fonts(page: Page) -> None:
    violations: list[str] = []
    page.on("console", lambda m: violations.append(m.text) if "Content Security Policy" in m.text else None)
    page.goto("/")
    page.wait_for_timeout(500)
    assert page.evaluate("window.__animReady") is True
    assert violations == []

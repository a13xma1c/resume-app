"""Browser tests for the contact form, verified end-to-end against the SMTP server."""

from __future__ import annotations

import re

from playwright.sync_api import Page, Route, expect

from resumeapp.smtp_server import DevSMTPServer


def fill_form(
    page: Page,
    *,
    name: str = "Jane Doe",
    email: str = "jane@example.com",
    subject: str = "Senior Data Engineer role",
    message: str = "Hi Alex, we're building a lakehouse on GCP and would love to talk.",
) -> None:
    page.fill("#name", name)
    page.fill("#email", email)
    page.fill("#subject", subject)
    page.fill("#message", message)


def test_form_renders_with_accessible_labels(page: Page) -> None:
    page.goto("/contact")
    expect(page.get_by_label("Name *")).to_be_visible()
    expect(page.get_by_label("Email *")).to_be_visible()
    expect(page.get_by_label("Subject (optional)")).to_be_visible()
    expect(page.get_by_label("Message *")).to_be_visible()
    expect(page.get_by_role("button", name="Send message")).to_be_enabled()
    # Honeypot is present in the DOM but not visible or focusable.
    honeypot = page.locator("#website")
    expect(honeypot).to_have_count(1)
    expect(honeypot).not_to_be_in_viewport()


def test_successful_submission_delivers_email(page: Page, smtp_server: DevSMTPServer) -> None:
    page.goto("/contact")
    fill_form(page)
    page.get_by_role("button", name="Send message").click()

    expect(page).to_have_url(re.compile(r"/contact$"))
    flash = page.locator(".flash-success")
    expect(flash).to_be_visible()
    expect(flash).to_contain_text("Thanks for reaching out!")
    # Form is reset after the redirect.
    expect(page.locator("#name")).to_have_value("")
    expect(page.locator("#message")).to_have_value("")

    messages = smtp_server.wait_for_messages(1)
    assert len(messages) == 1
    mail = messages[0]
    assert mail.rcpt_tos == ("owner@example.com",)
    assert mail.mail_from == "noreply@example.com"
    assert mail.subject == "[CV Contact] Senior Data Engineer role"
    assert mail.message["Reply-To"] == "Jane Doe <jane@example.com>"
    assert "lakehouse on GCP" in mail.body
    assert mail.path is not None and mail.path.exists()


def test_submit_button_shows_sending_state(page: Page) -> None:
    page.goto("/contact")
    fill_form(page)

    # Answer the POST with "204 No Content": browsers then stay on the current
    # document, which freezes the in-flight UI state so it can be asserted.
    def swallow_post(route: Route) -> None:
        if route.request.method == "POST":
            route.fulfill(status=204)
        else:
            route.continue_()

    page.route(re.compile(r"/contact$"), swallow_post)
    page.get_by_role("button", name="Send message").click(no_wait_after=True)

    button = page.locator("#contact-submit")
    expect(button).to_be_disabled()
    expect(button).to_contain_text("Sending...")
    expect(button).to_have_class(re.compile(r"\bis-loading\b"))
    # Nothing else changed on the page.
    expect(page.locator("#name")).to_have_value("Jane Doe")


def test_browser_validation_blocks_empty_submit(page: Page, smtp_server: DevSMTPServer) -> None:
    page.goto("/contact")
    page.get_by_role("button", name="Send message").click()
    # Still on the page, no navigation, HTML5 validation message on first field.
    expect(page).to_have_url(re.compile(r"/contact$"))
    invalid = page.evaluate("document.getElementById('name').validity.valueMissing")
    assert invalid is True
    assert page.evaluate("document.activeElement.id") == "name"
    assert smtp_server.wait_for_messages(1, timeout=0.3) == []


def test_server_side_validation_errors_are_shown(page: Page, smtp_server: DevSMTPServer) -> None:
    page.goto("/contact")
    # "a@b" passes the browser's loose email check but fails the server's.
    fill_form(page, email="a@b")
    page.get_by_role("button", name="Send message").click()

    expect(page.locator(".flash-error")).to_contain_text("Please correct the highlighted fields.")
    error = page.locator("#email-error")
    expect(error).to_have_text("Please enter a valid email address.")
    expect(page.locator("#email")).to_have_attribute("aria-invalid", "true")
    expect(page.locator("#email")).to_be_focused()
    # Other values are preserved.
    expect(page.locator("#name")).to_have_value("Jane Doe")
    expect(page.locator("#subject")).to_have_value("Senior Data Engineer role")
    assert smtp_server.wait_for_messages(1, timeout=0.3) == []

    # Fix the field and resubmit successfully from the re-rendered form.
    page.fill("#email", "jane@example.com")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".flash-success")).to_be_visible()
    assert len(smtp_server.wait_for_messages(1)) == 1


def test_character_counter_tracks_message_length(page: Page) -> None:
    page.goto("/contact")
    counter = page.locator("#message-counter")
    expect(counter).to_have_text("0 / 5000")
    page.fill("#message", "Hello there")
    expect(counter).to_have_text("11 / 5000")
    page.fill("#message", "")
    expect(counter).to_have_text("0 / 5000")


def test_long_message_is_accepted_and_delivered_intact(page: Page, smtp_server: DevSMTPServer) -> None:
    long_message = ("Paragraph about data platforms. " * 150).strip()  # ~4,800 chars
    page.goto("/contact")
    fill_form(page, message=long_message)
    expect(page.locator("#message-counter")).to_have_text(f"{len(long_message)} / 5000")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".flash-success")).to_be_visible()
    mail = smtp_server.wait_for_messages(1)[0]
    assert long_message in mail.body


def test_unicode_message_round_trip(page: Page, smtp_server: DevSMTPServer) -> None:
    page.goto("/contact")
    fill_form(
        page,
        name="Zoë Müller-Ștefănescu",
        subject="Întâlnire ☕",
        message="Bună ziua! 你好 — interested in Spark/Scala 🚀",
    )
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".flash-success")).to_be_visible()
    mail = smtp_server.wait_for_messages(1)[0]
    assert mail.subject == "[CV Contact] Întâlnire ☕"
    assert "Zoë Müller-Ștefănescu" in str(mail.message["Reply-To"])
    assert "你好 — interested in Spark/Scala 🚀" in mail.body


def test_honeypot_submission_is_silently_dropped(page: Page, smtp_server: DevSMTPServer) -> None:
    page.goto("/contact")
    fill_form(page)
    page.evaluate("document.getElementById('website').value = 'http://spam.example'")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".flash-success")).to_be_visible()  # bot sees "success"
    assert smtp_server.wait_for_messages(1, timeout=0.5) == []


def test_flash_message_disappears_on_next_visit(page: Page) -> None:
    page.goto("/contact")
    fill_form(page)
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".flash-success")).to_be_visible()
    page.reload()
    expect(page.locator(".flash-success")).to_have_count(0)


def test_contact_details_links(page: Page) -> None:
    page.goto("/contact")
    expect(page.locator(".contact-list a[href^='mailto:']")).to_have_attribute("href", "mailto:test@test.com")
    expect(page.locator(".contact-list a[href^='tel:']")).to_have_attribute("href", "tel:+0000000000")
    linkedin = page.locator(".contact-list a[target='_blank']")
    expect(linkedin).to_have_attribute("rel", "noopener noreferrer")

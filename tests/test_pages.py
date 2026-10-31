"""Tests for the content pages and shared layout (navigation, footer, errors)."""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient
from markupsafe import escape

from resumeapp.app import NAV_ITEMS
from resumeapp.cv_data import CV_DATA

PAGES = {
    "/": "Home",
    "/experience": "Experience",
    "/skills": "Skills",
    "/education": "Education",
    "/cv": "Full CV",
    "/contact": "Contact",
}


@pytest.mark.parametrize("path", list(PAGES))
def test_page_returns_200_html(client: FlaskClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")


@pytest.mark.parametrize("path", list(PAGES))
def test_every_page_has_full_navigation(client: FlaskClient, path: str) -> None:
    html = client.get(path).get_data(as_text=True)
    assert '<nav class="site-nav"' in html
    for nav_path in PAGES:
        assert f'href="{nav_path}"' in html, f"{path} is missing nav link to {nav_path}"


@pytest.mark.parametrize("path,label", PAGES.items())
def test_active_nav_link_marks_current_page(client: FlaskClient, path: str, label: str) -> None:
    html = client.get(path).get_data(as_text=True)
    active_snippet = f'href="{path}"\n                           class="nav-link active"'
    assert active_snippet in html
    assert 'aria-current="page"' in html
    # Exactly one link is marked active.
    assert html.count("nav-link active") == 1


def test_nav_items_constant_matches_registered_endpoints(app: Flask) -> None:
    with app.test_request_context():
        from flask import url_for

        paths = [url_for(endpoint) for endpoint, _ in NAV_ITEMS]
    assert paths == list(PAGES)
    assert [label for _, label in NAV_ITEMS] == list(PAGES.values())


@pytest.mark.parametrize("path", list(PAGES))
def test_pages_share_theme_toggle_and_footer(client: FlaskClient, path: str) -> None:
    html = client.get(path).get_data(as_text=True)
    assert html.count('id="theme-toggle"') == 1
    assert '<footer class="cv-footer">' in html
    assert 'href="/api/cv"' in html
    assert "Built with Python &amp; Flask" in html


# --- Home ----------------------------------------------------------------------


def test_home_page_content(client: FlaskClient) -> None:
    html = client.get("/").get_data(as_text=True)
    personal = CV_DATA["personal"]
    assert f"<title>{personal['name']} - {personal['title']}</title>" in html
    assert personal["summary"] in html
    assert personal["email"] in html
    assert personal["linkedin"] in html
    for item in personal["highlights"]:
        assert item["value"] in html
    # Calls to action
    assert "Get in touch" in html
    assert "View full CV" in html


def test_home_page_shows_current_role_and_stats(client: FlaskClient) -> None:
    html = client.get("/").get_data(as_text=True)
    current = next(e for e in CV_DATA["experience"] if e["is_current"])
    assert "Current Role" in html
    assert current["company"] in html
    assert current["period"] in html
    assert str(escape(current["responsibilities"][0])) in html
    # Only the first three responsibilities are previewed on the home page.
    assert str(escape(current["responsibilities"][3])) not in html

    n_skills = sum(len(v) for v in CV_DATA["skills"].values())
    assert f"{len(CV_DATA['experience'])} roles" in html
    assert f"{n_skills} technologies in {len(CV_DATA['skills'])} categories" in html
    assert (
        f"{len(CV_DATA['education'])} degrees and {len(CV_DATA['certifications'])} professional certifications" in html
    )


# --- Experience ----------------------------------------------------------------


def test_experience_page_lists_all_roles(client: FlaskClient) -> None:
    html = client.get("/experience").get_data(as_text=True)
    assert "<title>Experience - Alex Maican</title>" in html
    assert html.count('class="timeline-item"') == len(CV_DATA["experience"])
    for exp in CV_DATA["experience"]:
        assert exp["role"] in html
        assert exp["company"] in html
        assert exp["period"] in html
        for resp in exp["responsibilities"]:
            assert str(escape(resp)) in html


def test_experience_page_has_filter_and_quick_picks(client: FlaskClient) -> None:
    html = client.get("/experience").get_data(as_text=True)
    assert 'id="exp-filter-input"' in html
    assert 'class="quick-filters"' in html
    assert 'id="experience-empty"' in html
    # Quick picks are de-duplicated technologies in first-seen order.
    first_tech = CV_DATA["experience"][0]["key_technologies"][0]
    assert f'data-tag="{first_tech.lower()}"' in html


def test_experience_items_expose_filter_metadata(client: FlaskClient) -> None:
    html = client.get("/experience").get_data(as_text=True)
    for exp in CV_DATA["experience"]:
        assert f'data-company="{exp["company"].lower()}"' in html
        assert f'data-role="{exp["role"].lower()}"' in html
    assert "active-marker" in html  # the current role is highlighted
    assert html.count("active-marker") == sum(1 for e in CV_DATA["experience"] if e["is_current"])


# --- Skills --------------------------------------------------------------------


def test_skills_page_content(client: FlaskClient) -> None:
    html = client.get("/skills").get_data(as_text=True)
    assert "<title>Skills - Alex Maican</title>" in html
    for category, items in CV_DATA["skills"].items():
        assert str(escape(category)) in html
        for skill in items:
            assert f'data-skill="{escape(skill.lower())}"' in html
    for lang in CV_DATA["languages"]:
        assert lang["name"] in html
        assert lang["level"] in html
    # Skills page must not have a filter box; tags deep-link to /experience instead.
    assert 'id="exp-filter-input"' not in html
    assert 'data-experience-url="/experience"' in html


# --- Education -----------------------------------------------------------------


def test_education_page_content(client: FlaskClient) -> None:
    html = client.get("/education").get_data(as_text=True)
    assert "Education &amp; Certifications - Alex Maican" in html
    for edu in CV_DATA["education"]:
        assert str(escape(edu["degree"])) in html
        assert str(escape(edu["institution"])) in html
        assert edu["period"] in html
    for cert in CV_DATA["certifications"]:
        assert str(escape(cert["title"])) in html
        assert str(escape(cert["issuer"])) in html
    for course in CV_DATA["courses"]:
        assert str(escape(course)) in html


# --- Full CV -------------------------------------------------------------------


def test_full_cv_page_contains_every_section(client: FlaskClient) -> None:
    html = client.get("/cv").get_data(as_text=True)
    assert "<title>Full CV - Alex Maican</title>" in html
    for heading in (
        "Professional Profile",
        "Work Experience",
        "Skills &amp; Expertise",
        "Certifications",
        "Education",
        "Languages",
        "Relevant Courses",
    ):
        assert heading in html, f"missing section: {heading}"
    assert "Download PDF" in html
    assert "window.print()" in html
    assert 'id="exp-filter-input"' in html
    assert html.count('class="timeline-item"') == len(CV_DATA["experience"])


def test_full_cv_page_is_the_original_single_page_view(client: FlaskClient) -> None:
    """Regression: the original index content lives on /cv now."""
    html = client.get("/cv").get_data(as_text=True)
    for needle in (
        "Alex Maican",
        "Big Data Engineer",
        "Apache Spark",
        "IBM",
        "eMAG",
        "Orange Services",
        "Databricks Certified Data Engineer Associate",
    ):
        assert needle in html


# --- Error handling ------------------------------------------------------------


def test_404_renders_custom_page_with_navigation(client: FlaskClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "<title>404 Not Found - Alex Maican</title>" in html
    assert 'class="error-code">404<' in html
    assert '<nav class="site-nav"' in html
    assert "Back to home" in html


def test_405_renders_custom_page(client: FlaskClient) -> None:
    response = client.post("/skills", data={})
    assert response.status_code == 405
    html = response.get_data(as_text=True)
    assert 'class="error-code">405<' in html


def test_trailing_slash_variants_do_not_500(client: FlaskClient) -> None:
    # Flask redirects "/contact/" → "/contact" when strict_slashes applies, or 404s.
    response = client.get("/contact/")
    assert response.status_code in (301, 308, 404)


# --- Security headers ----------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/contact", "/api/cv", "/does-not-exist"])
def test_security_headers_present_on_all_responses(client: FlaskClient, path: str) -> None:
    response = client.get(path)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


@pytest.mark.parametrize(
    "path,mimetype", [("/static/css/style.css", "text/css"), ("/static/js/main.js", "text/javascript")]
)
def test_static_assets_are_served(client: FlaskClient, path: str, mimetype: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith(mimetype)
    response.close()


def test_templates_escape_user_visible_values(app: Flask) -> None:
    """Jinja autoescaping must be on for .html templates."""
    autoescape = app.jinja_env.autoescape
    assert callable(autoescape) and autoescape("contact.html") is True

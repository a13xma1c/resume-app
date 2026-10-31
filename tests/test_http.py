"""Tests for HTTP hygiene: CSP, HSTS, caching, static versioning, proxies, health."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from resumeapp import create_app
from resumeapp.http import BOOTSTRAP_SCRIPT, BOOTSTRAP_SCRIPT_HASH, CACHEABLE_ENDPOINTS, build_csp, script_hash
from resumeapp.security import RateLimiter

from .helpers import RecordingMailer, extract_csrf_token

INLINE_SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.S)
CSP_HASH_RE = re.compile(r"script-src 'self' ('sha256-[A-Za-z0-9+/=]+')")


# --- Content-Security-Policy -------------------------------------------------------


def test_csp_hash_matches_the_inline_bootstrap_script(client: FlaskClient) -> None:
    response = client.get("/")
    html = response.get_data(as_text=True)
    inline = INLINE_SCRIPT_RE.findall(html)
    assert inline == [BOOTSTRAP_SCRIPT], "exactly one inline script, byte-identical to the allow-listed source"
    header_hash = CSP_HASH_RE.search(response.headers["Content-Security-Policy"])
    assert header_hash is not None
    assert header_hash.group(1) == script_hash(inline[0]) == BOOTSTRAP_SCRIPT_HASH


def test_csp_header_is_identical_across_requests(client: FlaskClient) -> None:
    """No nonces: responses stay deterministic so ETag caching keeps working."""
    assert (
        client.get("/").headers["Content-Security-Policy"] == client.get("/skills").headers["Content-Security-Policy"]
    )
    assert "nonce-" not in client.get("/").headers["Content-Security-Policy"]


def test_script_hash_format() -> None:
    token = script_hash("alert(1)")
    assert token.startswith("'sha256-") and token.endswith("'")
    assert token == "'sha256-bhHHL3z2vDgxUt0W3dWQOrprscmda2Y5pLsLg4GF+pI='"  # known vector


def test_csp_directives(client: FlaskClient) -> None:
    csp = client.get("/contact").headers["Content-Security-Policy"]
    for directive in (
        "default-src 'self'",
        "style-src 'self' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
    ):
        assert directive in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


def test_build_csp_allow_lists_only_the_bootstrap_hash() -> None:
    assert build_csp().count("sha256-") == 1
    assert BOOTSTRAP_SCRIPT_HASH in build_csp()


@pytest.mark.parametrize("path", ["/", "/experience", "/skills", "/education", "/cv", "/contact", "/does-not-exist"])
def test_no_inline_event_handlers_or_scripts_without_nonce(client: FlaskClient, path: str) -> None:
    html = client.get(path).get_data(as_text=True)
    assert not re.search(r"\son[a-z]+=", html), "inline event handlers would be blocked by the CSP"
    for match in re.finditer(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S):
        attrs, body = match.group("attrs"), match.group("body")
        assert "src=" in attrs or body == BOOTSTRAP_SCRIPT, f"unexpected inline script: {body[:60]}"


# --- HSTS / secure cookies -----------------------------------------------------------


def test_no_hsts_by_default(client: FlaskClient) -> None:
    assert "Strict-Transport-Security" not in client.get("/").headers


def test_hsts_when_enabled(app_config: dict[str, Any], mailer: RecordingMailer) -> None:
    app_config.update(HSTS_ENABLED=True, HSTS_MAX_AGE=600)
    response = create_app(app_config, mailer=mailer).test_client().get("/")
    assert response.headers["Strict-Transport-Security"] == "max-age=600; includeSubDomains"


def test_secure_cookie_env_enables_hsts_and_https_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "1")
    app = create_app({"TESTING": True})
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["HSTS_ENABLED"] is True
    assert app.config["PREFERRED_URL_SCHEME"] == "https"
    response = app.test_client().get("/contact")
    assert "Secure" in response.headers["Set-Cookie"]


# --- Caching -----------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/experience", "/skills", "/education", "/cv"])
def test_html_pages_have_etag_and_revalidate(client: FlaskClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    etag = response.headers.get("ETag")
    assert etag
    assert response.cache_control.no_cache
    assert not response.cache_control.no_store
    assert "Accept-Encoding" in response.headers["Vary"]

    revalidation = client.get(path, headers={"If-None-Match": etag})
    assert revalidation.status_code == 304
    assert revalidation.data == b""
    assert revalidation.headers["ETag"] == etag


def test_etag_changes_when_content_changes(client: FlaskClient) -> None:
    assert client.get("/").headers["ETag"] != client.get("/skills").headers["ETag"]


def test_stale_etag_gets_full_response(client: FlaskClient) -> None:
    response = client.get("/", headers={"If-None-Match": '"definitely-stale"'})
    assert response.status_code == 200
    assert len(response.data) > 1000


def test_api_is_publicly_cacheable(client: FlaskClient, app: Flask) -> None:
    response = client.get("/api/cv")
    assert response.cache_control.public
    assert response.cache_control.max_age == app.config["API_CACHE_MAX_AGE"]
    assert response.headers.get("ETag")
    assert client.get("/api/cv", headers={"If-None-Match": response.headers["ETag"]}).status_code == 304


def test_contact_page_is_never_cached(client: FlaskClient) -> None:
    response = client.get("/contact")
    assert response.cache_control.no_store
    assert "ETag" not in response.headers


def test_contact_post_responses_are_not_cached(client: FlaskClient, csrf_token: str) -> None:
    response = client.post("/contact", data={"csrf_token": csrf_token, "name": "", "email": "", "message": ""})
    assert response.status_code == 400
    assert "ETag" not in response.headers


def test_error_pages_are_not_cached(client: FlaskClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert "ETag" not in response.headers


def test_pdf_and_health_are_not_cached(client: FlaskClient) -> None:
    pdf = client.get("/download-pdf")
    assert pdf.cache_control.no_store
    pdf.close()
    assert client.get("/healthz").cache_control.no_store


def test_cacheable_endpoints_constant_matches_routes(app: Flask) -> None:
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert endpoints >= CACHEABLE_ENDPOINTS
    assert "contact.contact" not in CACHEABLE_ENDPOINTS


# --- Static asset versioning -------------------------------------------------------------


def test_static_urls_are_versioned_with_content_hash(client: FlaskClient, app: Flask) -> None:
    html = client.get("/").get_data(as_text=True)
    css = re.search(r'href="/static/css/style\.css\?v=([0-9a-f]{12})"', html)
    js = re.search(r'src="/static/js/main\.js\?v=([0-9a-f]{12})" defer', html)
    assert css and js
    # Same file → same version on every render; different files → different versions.
    again = re.search(r"style\.css\?v=([0-9a-f]{12})", client.get("/skills").get_data(as_text=True))
    assert again is not None and again.group(1) == css.group(1)
    assert css.group(1) != js.group(1)


def test_static_version_changes_when_file_changes(
    tmp_path: Path, mailer: RecordingMailer, app_config: dict[str, Any]
) -> None:
    from resumeapp.http import static_file_version

    app = create_app(app_config, mailer=mailer)
    app.static_folder = str(tmp_path)
    asset = tmp_path / "a.css"
    asset.write_text("body{}")
    with app.test_request_context():
        v1 = static_file_version("a.css")
        assert static_file_version("a.css") == v1  # cached
        asset.write_text("body{color:red}")
        import os

        os.utime(asset, (asset.stat().st_atime, asset.stat().st_mtime + 10))
        v2 = static_file_version("a.css")
        assert v2 != v1
        assert static_file_version("missing.css") == "0"


def test_static_files_get_long_max_age(client: FlaskClient) -> None:
    response = client.get("/static/css/style.css?v=abc")
    assert response.status_code == 200
    assert response.cache_control.max_age == 31_536_000
    response.close()


# --- Reverse proxy support -------------------------------------------------------------------


def valid_payload(token: str) -> dict[str, str]:
    return {"csrf_token": token, "name": "Bob", "email": "bob@example.com", "message": "Hello Alex, nice CV!"}


def test_forwarded_headers_are_ignored_without_trusted_proxies(
    app_config: dict[str, Any], mailer: RecordingMailer
) -> None:
    app_config["CONTACT_RATE_LIMIT"] = 1
    client = create_app(app_config, mailer=mailer).test_client()
    token = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    assert client.post("/contact", data=valid_payload(token)).status_code == 302
    # A spoofed X-Forwarded-For must not give the same client a fresh quota.
    spoofed = client.post("/contact", data=valid_payload(token), headers={"X-Forwarded-For": "203.0.113.9"})
    assert spoofed.status_code == 429


def test_trusted_proxy_uses_forwarded_client_ip(app_config: dict[str, Any], mailer: RecordingMailer) -> None:
    app_config.update(CONTACT_RATE_LIMIT=1, TRUSTED_PROXIES=1)
    app = create_app(app_config, mailer=mailer)
    client = app.test_client()
    token = extract_csrf_token(client.get("/contact").get_data(as_text=True))
    first = client.post("/contact", data=valid_payload(token), headers={"X-Forwarded-For": "203.0.113.1"})
    second = client.post("/contact", data=valid_payload(token), headers={"X-Forwarded-For": "203.0.113.2"})
    third = client.post("/contact", data=valid_payload(token), headers={"X-Forwarded-For": "203.0.113.1"})
    assert (first.status_code, second.status_code, third.status_code) == (302, 302, 429)
    assert "IP:      203.0.113.2" in mailer.sent[1].get_content()
    limiter: RateLimiter = app.extensions["rate_limiter"]
    assert limiter.remaining("203.0.113.1") == 0


def test_trusted_proxy_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXIES", "2")
    app = create_app({"TESTING": True})
    assert app.config["TRUSTED_PROXIES"] == 2
    assert type(app.wsgi_app).__name__ == "ProxyFix"


def test_no_proxy_middleware_by_default(app: Flask) -> None:
    assert type(app.wsgi_app).__name__ != "ProxyFix"


# --- Health endpoint ------------------------------------------------------------------------------


def test_healthz(client: FlaskClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["mailer"] == "console"  # RecordingMailer is not an SMTPMailer
    assert data["pdf_available"] is True
    assert isinstance(data["version"], str) and data["version"]


def test_healthz_reports_smtp_mailer_and_missing_pdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    client = create_app({"TESTING": True, "CV_PDF_PATH": str(tmp_path / "nope.pdf")}).test_client()
    data = client.get("/healthz").get_json()
    assert data["mailer"] == "smtp"
    assert data["pdf_available"] is False

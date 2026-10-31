"""HTTP hygiene helpers: security headers, CSP nonces, caching and static versioning."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from flask import Flask, Response, current_app, request, url_for
from markupsafe import Markup

#: Endpoints whose GET responses are deterministic for a given deployment and may
#: therefore be served with an ETag and answered with ``304 Not Modified``.
CACHEABLE_ENDPOINTS = frozenset(
    {"pages.home", "pages.experience", "pages.skills", "pages.education", "pages.full_cv", "api.cv"}
)

STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


#: The only inline script on the site. It runs before first paint (so the saved
#: theme applies without a flash) and arms the scroll-reveal fail-safe. Keeping
#: the source here lets the CSP allow-list its hash instead of a per-request
#: nonce – a nonce would make every response unique and defeat ETag caching.
BOOTSTRAP_SCRIPT = (
    "(function(){try{var t=localStorage.getItem('theme');"
    "if(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches)t='dark';"
    "if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}"
    "document.documentElement.classList.add('js-anim');"
    "setTimeout(function(){if(!window.__animReady)document.documentElement.classList.add('anim-failsafe');},2500);"
    "})();"
)


def script_hash(source: str) -> str:
    """CSP ``'sha256-…'`` token for an inline script body."""
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode('ascii')}'"


BOOTSTRAP_SCRIPT_HASH = script_hash(BOOTSTRAP_SCRIPT)


def build_csp() -> str:
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {BOOTSTRAP_SCRIPT_HASH}",
            "style-src 'self' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "object-src 'none'",
        ]
    )


CONTENT_SECURITY_POLICY = build_csp()


def static_url(filename: str) -> str:
    """``url_for('static', …)`` plus a content-hash query string for cache busting.

    Combined with a long ``SEND_FILE_MAX_AGE_DEFAULT`` this lets browsers cache
    assets indefinitely while guaranteeing a fresh download whenever a file changes.
    """
    return url_for("static", filename=filename, v=static_file_version(filename))


def static_file_version(filename: str) -> str:
    app = current_app
    cache: dict[str, tuple[float, str]] = app.extensions.setdefault("static_versions", {})
    static_folder = app.static_folder
    if static_folder is None:  # pragma: no cover - the app always has one
        return "0"
    path = Path(static_folder) / filename
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return "0"
    cached = cache.get(filename)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    cache[filename] = (mtime, digest)
    return digest


def apply_response_headers(response: Response) -> Response:
    """``after_request`` hook: security headers + caching policy."""
    for header, value in STATIC_HEADERS.items():
        response.headers.setdefault(header, value)
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    if current_app.config.get("HSTS_ENABLED"):
        response.headers.setdefault(
            "Strict-Transport-Security", f"max-age={current_app.config['HSTS_MAX_AGE']}; includeSubDomains"
        )

    if request.endpoint == "static" or response.status_code != 200 or request.method not in {"GET", "HEAD"}:
        return response

    if request.endpoint in CACHEABLE_ENDPOINTS and not response.direct_passthrough:
        response.add_etag()
        if request.endpoint == "api.cv":
            response.cache_control.public = True
            response.cache_control.max_age = current_app.config["API_CACHE_MAX_AGE"]
        else:
            # HTML: always revalidate, but a matching ETag costs only a 304.
            response.cache_control.no_cache = True
        response.headers.setdefault("Vary", "Accept-Encoding")
        response.make_conditional(request)  # turns the response into a 304 when ETags match
        return response

    if request.endpoint is not None and request.endpoint != "static":
        # Contact page (CSRF token), health check, PDF: never cache.
        response.cache_control.no_store = True
    return response


def init_http(app: Flask) -> None:
    """Install the hooks, helpers and deployment middleware on ``app``."""
    trusted = int(app.config.get("TRUSTED_PROXIES", 0) or 0)
    if trusted > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted, x_proto=trusted, x_host=trusted, x_port=trusted)  # type: ignore[method-assign]

    app.after_request(apply_response_headers)
    app.context_processor(lambda: {"bootstrap_script": Markup(BOOTSTRAP_SCRIPT), "static_url": static_url})

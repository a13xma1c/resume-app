"""Flask application factory for the CV website."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

from .config import BASE_DIR, load_config
from .cv_data import CV_DATA
from .mail import ConsoleMailer, Mailer, SMTPMailer
from .security import RateLimiter, generate_csrf_token
from .views import api_bp, contact_bp, pages_bp

NAV_ITEMS = (
    ("pages.home", "Home"),
    ("pages.experience", "Experience"),
    ("pages.skills", "Skills"),
    ("pages.education", "Education"),
    ("pages.full_cv", "Full CV"),
    ("contact.contact", "Contact"),
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def create_mailer(config: Mapping[str, Any], logger: logging.Logger) -> Mailer:
    """Pick the mail transport based on configuration."""
    if config.get("MAIL_SUPPRESS_SEND") or not config.get("MAIL_SERVER"):
        logger.warning(
            "MAIL_SERVER is not configured (or MAIL_SUPPRESS_SEND is on); "
            "contact form emails will be logged instead of sent."
        )
        return ConsoleMailer(logger)
    return SMTPMailer(
        config["MAIL_SERVER"],
        config["MAIL_PORT"],
        username=config.get("MAIL_USERNAME"),
        password=config.get("MAIL_PASSWORD"),
        use_tls=config.get("MAIL_USE_TLS", True),
        use_ssl=config.get("MAIL_USE_SSL", False),
        timeout=config.get("MAIL_TIMEOUT", 10),
    )


def create_app(
    test_config: Mapping[str, Any] | None = None,
    *,
    mailer: Mailer | None = None,
) -> Flask:
    """Create and configure the Flask CV application.

    ``test_config`` overrides values loaded from the environment; ``mailer``
    replaces the transport chosen from configuration (handy in tests).
    """
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config.from_mapping(load_config())
    if test_config:
        app.config.from_mapping(test_config)

    if app.config.get("SECRET_KEY_IS_EPHEMERAL") and not app.testing:
        app.logger.warning(
            "SECRET_KEY is not set; using a random key. Sessions (and CSRF tokens) "
            "will not survive restarts. Set SECRET_KEY in production."
        )

    app.extensions["mailer"] = mailer or create_mailer(app.config, app.logger)
    app.extensions["rate_limiter"] = RateLimiter(
        app.config["CONTACT_RATE_LIMIT"], app.config["CONTACT_RATE_WINDOW"]
    )

    app.register_blueprint(pages_bp)
    app.register_blueprint(contact_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        return {
            "cv": CV_DATA,
            "nav_items": NAV_ITEMS,
            "csrf_token": generate_csrf_token,
            "current_year": datetime.now(timezone.utc).year,
            "contact_recipient": app.config["CONTACT_RECIPIENT"],
        }

    @app.after_request
    def set_security_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return (
            render_template(
                "error.html",
                code=error.code,
                name=error.name,
                description=error.description,
            ),
            error.code,
        )

    return app


def main() -> None:
    """Entry point for the ``resumeapp`` CLI runner."""
    app = create_app()
    port = int(os.environ.get("PORT", "5123"))
    debug = os.environ.get("FLASK_DEBUG", "1").lower() in {"1", "true", "yes", "on"}
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()

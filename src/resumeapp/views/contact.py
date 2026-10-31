"""Contact page: renders the form and emails submissions to the site owner."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..forms import ContactForm
from ..mail import MailDeliveryError, build_contact_email
from ..security import CSRF_FORM_FIELD, validate_csrf_token

bp = Blueprint("contact", __name__, url_prefix="/contact")

SUCCESS_MESSAGE = "Thanks for reaching out! Your message has been sent and I'll get back to you soon."
CSRF_ERROR = "Your session has expired. Please try sending the message again."
RATE_LIMIT_ERROR = "You've sent several messages recently. Please wait a while before trying again."
DELIVERY_ERROR = "Sorry, the message could not be sent right now. Please try again later or email me directly."


def _render(form: ContactForm, status: int = 200, form_error: str | None = None):
    return (
        render_template("contact.html", form=form, form_error=form_error),
        status,
    )


@bp.route("", methods=["GET"])
def contact():
    return _render(ContactForm())


@bp.route("", methods=["POST"])
def submit():
    form = ContactForm.from_mapping(request.form)

    if current_app.config["CSRF_ENABLED"] and not validate_csrf_token(request.form.get(CSRF_FORM_FIELD)):
        return _render(form, 400, CSRF_ERROR)

    if not form.validate():
        return _render(form, 400, "Please correct the highlighted fields.")

    # Bots fill in the hidden honeypot field. Pretend everything went fine so
    # they get no feedback, but don't send anything.
    if form.is_spam:
        current_app.logger.info("Contact form honeypot triggered from %s", request.remote_addr)
        flash(SUCCESS_MESSAGE, "success")
        return redirect(url_for("contact.contact"))

    limiter = current_app.extensions["rate_limiter"]
    if not limiter.hit(request.remote_addr or "unknown"):
        return _render(form, 429, RATE_LIMIT_ERROR)

    message = build_contact_email(
        form,
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipient=current_app.config["CONTACT_RECIPIENT"],
        subject_prefix=current_app.config["CONTACT_SUBJECT_PREFIX"],
        remote_addr=request.remote_addr,
    )

    try:
        current_app.extensions["mailer"].send(message)
    except MailDeliveryError:
        current_app.logger.exception("Failed to deliver contact form email")
        return _render(form, 503, DELIVERY_ERROR)

    flash(SUCCESS_MESSAGE, "success")
    return redirect(url_for("contact.contact"))

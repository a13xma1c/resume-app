# Alex Maican - Interactive CV Website

A modern, responsive, multi-page CV & Portfolio website built with **Python**, **Flask**, and managed with **uv**. The content is modeled directly on Alex Maican's CV (`Alex Maican - CV.pdf`).

## Features

- **Multi-page site** with a shared, sticky navigation bar and active-page highlighting:
  - **Home** – hero, professional summary, highlights, "explore" cards and a current-role teaser.
  - **Experience** – full work history with a live keyword filter and technology "quick picks"; deep-linkable via `/experience?q=spark`.
  - **Skills** – categorised skill badges (click one to jump to the matching roles) and spoken languages.
  - **Education** – degrees, certifications and relevant courses.
  - **Full CV** – the complete one-page, print-optimised CV with download/print buttons.
  - **Contact** – a form that emails messages to a predefined address (see [Contact form & email](#contact-form--email)).
- **Interactive UI**:
  - **Dark / Light Mode** with system-preference detection and `localStorage` persistence (no flash of wrong theme).
  - **Live Filter / Search** over work experience by keywords, technologies or company, with an empty-state message.
  - **Quick Copy** buttons for email and phone with toast notifications.
  - **Responsive navigation** with a mobile hamburger menu; keyboard-accessible tags and skip link.
- **PDF Download & View**: Direct download (`/download-pdf`) and inline viewing (`/view-pdf`) of the source CV PDF.
- **REST API**: `/api/cv` JSON endpoint providing the full structured resume data.
- **Print Optimisation**: Tailored `@media print` stylesheet for clean physical prints or browser PDF exports.
- **Hardened by default**: CSRF tokens, honeypot spam trap, per-IP rate limiting, header-injection checks, request size limit, custom error pages and security headers.

---

## Quickstart with `uv`

### 1. Install dependencies
```bash
uv sync
```

### 2. Run the application
```bash
uv run python app.py
```
or via the installed package script:
```bash
uv run resumeapp
```
or with the Flask CLI:
```bash
uv run flask --app app run --port 5000
```

Open [http://localhost:5123](http://localhost:5123) (or the port you chose) in your web browser.

> Without any configuration the site works fully; contact-form messages are **logged to the console** instead of emailed. See below to enable real delivery.

---

## Pages & Endpoints

| Route | Method | Description |
|---|---|---|
| `/` | GET | Home / landing page |
| `/experience` | GET | Work experience timeline with filter (`?q=` pre-fills the filter) |
| `/skills` | GET | Skills & languages |
| `/education` | GET | Education, certifications & courses |
| `/cv` | GET | Full single-page, print-ready CV |
| `/contact` | GET | Contact form |
| `/contact` | POST | Submit the contact form (sends an email) |
| `/api/cv` | GET | Structured CV data in JSON format |
| `/download-pdf` | GET | Download the original CV PDF |
| `/view-pdf` | GET | View the PDF inline in the browser |

---

## Contact form & email

Submissions are validated server-side (name, valid email, optional subject, 10–5000 char message), protected against CSRF and bots, rate-limited per IP, and then emailed to **`CONTACT_RECIPIENT`** via SMTP. The email is sent *from* `MAIL_DEFAULT_SENDER` with `Reply-To` set to the visitor, so replying is one click.

Configuration is done through environment variables (see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | random per start | Session/CSRF signing key. **Set this in production.** |
| `CONTACT_RECIPIENT` | email from `cv_data.py` | Predefined address that receives the messages |
| `CONTACT_SUBJECT_PREFIX` | `[CV Contact]` | Prefix added to email subjects |
| `CONTACT_RATE_LIMIT` / `CONTACT_RATE_WINDOW` | `5` / `3600` | Max submissions per IP per window (seconds); `0` disables |
| `MAIL_SERVER` | *(unset → log only)* | SMTP host; when unset, emails are logged instead of sent |
| `MAIL_PORT` | `587` (`465` if SSL) | SMTP port |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | *(none)* | SMTP credentials |
| `MAIL_USE_TLS` | `true` | Use STARTTLS |
| `MAIL_USE_SSL` | `false` | Use implicit TLS (mutually exclusive with `MAIL_USE_TLS`) |
| `MAIL_DEFAULT_SENDER` | `MAIL_USERNAME` or `no-reply@localhost` | `From` address |
| `MAIL_TIMEOUT` | `10` | SMTP connection timeout (seconds) |
| `MAIL_SUPPRESS_SEND` | `false` | Force console logging even when `MAIL_SERVER` is set |
| `CV_PDF_PATH` | `./Alex Maican - CV.pdf` | Location of the downloadable PDF |
| `PORT` / `FLASK_DEBUG` | `5123` / `1` | Dev-server options for `python app.py` / `uv run resumeapp` |

Example (Gmail with an app password):

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export CONTACT_RECIPIENT="you@example.com"
export MAIL_SERVER="smtp.gmail.com"
export MAIL_USERNAME="you@gmail.com"
export MAIL_PASSWORD="xxxx xxxx xxxx xxxx"
uv run resumeapp
```

> The rate limiter is in-memory and therefore per-process; if you deploy with several workers, each worker keeps its own counters. Behind a reverse proxy, wrap the app with Werkzeug's `ProxyFix` so `request.remote_addr` reflects the real client IP.

---

## Project layout

```
app.py                      # WSGI entry point (creates the app)
src/resumeapp/
  app.py                    # application factory, context processors, error handling
  config.py                 # environment-driven configuration
  cv_data.py                # structured CV content
  forms.py                  # ContactForm validation
  mail.py                   # email composition + SMTP / console transports
  security.py               # CSRF helpers and rate limiter
  views/                    # blueprints: pages, contact, api
templates/                  # Jinja templates (base layout, pages, partials/)
static/                     # CSS & JS
tests/                      # pytest suite
```

---

## Testing

Run the test suite with `pytest`:

```bash
uv run pytest
```

The suite (~250 tests) covers:

- every page (content, navigation, active links, titles, error pages, security headers);
- the JSON API and PDF endpoints (including the missing-file case, using a temporary PDF);
- the contact form end-to-end: success path and email contents, every validation rule, CSRF, honeypot, rate limiting, delivery failures, XSS/header-injection attempts, payload limits;
- unit tests for form validation, email building, SMTP/console mailers (with `smtplib` mocked), CSRF helpers, the rate limiter (including thread safety), configuration parsing, the app factory and the CLI entry point;
- integrity checks on the CV data itself.

No network access or real mail server is needed.

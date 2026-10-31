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
- **Carousel page transitions**: internal links are intercepted and the next page is fetched and *rolled* in horizontally — forward pages slide in from the right, earlier pages from the left — with a slight overshoot so it snaps into place. Browser back/forward roll too, a sliding pill in the nav follows the active page, nav links are prefetched on hover, touch devices can swipe between pages, and everything degrades to ordinary navigation (modifier-clicks, fetch errors, `prefers-reduced-motion`).
- **Scroll & micro-animations**: cards, timeline entries and headers fade/rise in as they scroll into view (staggered, `IntersectionObserver`), plus hover lifts, a pulsing "current role" marker, floating avatar, shimmering header bar, spinning theme icon, growing title underline and animated flashes/menus. All honour `prefers-reduced-motion`; print output is unaffected; if the script fails to load a fail-safe reveals everything.
- **Interactive UI**:
  - **Dark / Light Mode** with system-preference detection and `localStorage` persistence (no flash of wrong theme).
  - **Live Filter / Search** over work experience by keywords, technologies or company, with an empty-state message.
  - **Quick Copy** buttons for email and phone with toast notifications.
  - **Responsive navigation** with a mobile hamburger menu; keyboard-accessible tags and skip link.
- **PDF Download & View**: Direct download (`/download-pdf`) and inline viewing (`/view-pdf`) of the source CV PDF.
- **REST API**: `/api/cv` JSON endpoint providing the full structured resume data.
- **Print Optimisation**: Tailored `@media print` stylesheet for clean physical prints or browser PDF exports.
- **Hardened by default**: CSRF tokens, honeypot spam trap, per-IP rate limiting, header-injection checks, request size limit, custom error pages, and a strict hash-based Content-Security-Policy plus the usual security headers (HSTS when served over HTTPS).
- **Cache-friendly**: ETags with `304 Not Modified` for pages and the API, content-hashed static asset URLs with a one-year `max-age`, `no-store` where it matters (contact form, health check).
- **Deployment-ready**: `TRUSTED_PROXIES` for reverse proxies, `GET /healthz` for load balancers, GitHub Actions CI running lint, types, unit, browser and load tests.
- **Persistent SMTP connection**: the mailer keeps its SMTP session open between sends (with automatic reconnect) instead of paying a TCP+TLS handshake per email.
- **Bundled SMTP server** (`resumeapp-smtp`) that receives contact-form emails locally and saves them as `.eml` files — for development, end-to-end tests and load tests.
- **Fully typed** (`mypy --strict` on the app *and* the tests) with unit, integration, Playwright browser and Locust load test suites.

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

> Without any configuration the site works fully; contact-form messages are **logged to the console** instead of emailed. To actually *receive* them locally, run with the bundled SMTP server: `DEV_SMTP=1 uv run resumeapp` (see [SMTP server](#smtp-server)). For real delivery, configure an SMTP provider as described below.

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
| `/healthz` | GET | Health probe: `{"status", "version", "mailer", "pdf_available"}` |
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
| `MAIL_KEEPALIVE` | `true` | Reuse one SMTP session across sends (set `false` to connect per email) |
| `CV_PDF_PATH` | `./Alex Maican - CV.pdf` | Location of the downloadable PDF |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` behind HTTPS (also enables HSTS by default) |
| `HSTS_ENABLED` / `HSTS_MAX_AGE` | `= SESSION_COOKIE_SECURE` / `31536000` | `Strict-Transport-Security` header |
| `TRUSTED_PROXIES` | `0` | Reverse proxies whose `X-Forwarded-*` headers to trust (for real client IPs) |
| `STATIC_MAX_AGE` / `API_CACHE_MAX_AGE` | `31536000` / `300` | Browser cache lifetimes for versioned assets and `/api/cv` |
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

### SMTP server

The project ships its own SMTP server (built on [aiosmtpd](https://aiosmtpd.readthedocs.io)) so you can see exactly what the form sends without an external provider. It accepts mail on a local port, keeps messages in memory and writes each one to a directory as an `.eml` file that any mail client can open. It never relays anything.

**Option A – everything in one process**

```bash
DEV_SMTP=1 uv run resumeapp
# contact emails are delivered over SMTP to the embedded server and saved to ./mail-outbox/*.eml
```

`DEV_SMTP_PORT` (default `0` = free port) and `DEV_SMTP_MAILDIR` (default `mail-outbox`) tune it.

**Option B – standalone server** (e.g. to share it between the app, Locust and a mail client)

```bash
uv run resumeapp-smtp --port 1025 --maildir ./mail-outbox      # add --user/--password to require AUTH
MAIL_SERVER=127.0.0.1 MAIL_PORT=1025 MAIL_USE_TLS=false uv run resumeapp
```

Programmatic use (this is what the test suites do):

```python
from resumeapp.smtp_server import DevSMTPServer

with DevSMTPServer(port=0) as smtp:  # port 0 → pick a free one
    app = create_app(smtp.mail_config())  # points MAIL_* at the server
    ...
    message = smtp.wait_for_messages(1)[0]  # StoredMessage: subject, body, rcpt_tos, path…
```

> The rate limiter is in-memory and therefore per-process; if you deploy with several workers, each worker keeps its own counters. Behind a reverse proxy set `TRUSTED_PROXIES` to the number of proxies so `request.remote_addr` reflects the real client IP (otherwise every visitor would share the proxy's quota).

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
  http.py                   # CSP & security headers, ETag/caching policy, static asset versioning, ProxyFix
  smtp_server.py            # bundled SMTP server (DevSMTPServer + `resumeapp-smtp` CLI)
  views/                    # blueprints: pages, contact, api
templates/                  # Jinja templates (base layout, pages, partials/)
static/                     # CSS & JS
loadtests/                  # Locust locustfiles (flat and staged ramp profiles)
tests/                      # unit & integration tests (fully typed)
  e2e/                      # Playwright browser tests (marker: e2e)
  load/                     # Locust-driven volumetric tests (marker: load)
```

---

## Testing

All test code is type-annotated and checked with `mypy --strict` alongside the application code, and linted/formatted with Ruff. The same steps run in CI (`.github/workflows/ci.yml`):

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy            # checks src/, tests/ and loadtests/
```

### Unit & integration tests (default)

```bash
uv run pytest
```

~355 fast tests, no network or browser needed. They cover every page (content, navigation, titles, error pages, security headers), the JSON API and PDF endpoints, the contact form end-to-end (success path, every validation rule, CSRF, honeypot, rate limiting, delivery failures, XSS/header-injection attempts, payload limits), and unit tests for form validation, email building, the SMTP/console mailers, CSRF helpers, the rate limiter, configuration parsing, the app factory, the CLI entry points and the CV data. The SMTP server tests perform **real SMTP conversations** over loopback — `SMTPMailer` → `DevSMTPServer` — including AUTH success/failure and a full web-form → SMTP round trip.

### Browser tests (Playwright)

```bash
uv run playwright install chromium   # once
uv run pytest -m e2e                 # add --headed to watch, --browser firefox/webkit for others
```

76 tests drive a real Chromium against a live Flask server (served by Waitress) **and** a live SMTP server: navigation and active links, theme toggle persistence (incl. `prefers-color-scheme`), the mobile menu, clipboard copy, PDF download, the experience filter (typing, tag clicks, keyboard, `?q=` deep links from other pages, empty state), the contact form — HTML5 validation, server-side errors with focus management, the "Sending…" state, Unicode and 5 000-character messages, honeypot, flash lifecycle — asserting on the email that actually arrives at the SMTP server, and the motion layer: carousel direction and settling, history/back-forward, rapid clicks, prefetching, modifier-clicks, swipe, reduced-motion and fetch-failure fallbacks, scroll reveal and its stagger/fail-safe, and the micro-animations.

### Load tests (Locust)

```bash
uv run pytest -m load                                                        # ≈10 s smoke run
LOAD_USERS=1000 LOAD_SPAWN_RATE=50 LOAD_DURATION=60 uv run pytest -m load    # heavy run
```

The pytest wrapper starts the SMTP server in-process and the app on several worker processes sharing one socket (pre-fork, like gunicorn), runs Locust headless as a subprocess with `FastHttpUser`s (one keep-alive connection per user), and asserts on the collected statistics: zero failed requests, p95 latency within budget for every endpoint, traffic on every page, and that each accepted contact submission produced an email while invalid/honeypot submissions produced none. `LOAD_SERVER_PROCESSES`, `LOAD_PROCESSES`, `LOAD_MAX_P95_MS` and `LOAD_MAX_FAIL_RATIO` tune it for the machine at hand.

For interactive or long-running load tests against any deployment, see [`loadtests/README.md`](loadtests/README.md) — thresholds are enforced via the process exit code so the run can gate CI.

"""Volumetric load tests for the CV website, driven by Locust.

Two user populations are simulated:

* :class:`Visitor` – browses the content pages, the JSON API and static
  assets (the bulk of real traffic).
* :class:`ContactSender` – completes the contact form, including the CSRF
  handshake, so the SMTP delivery path is exercised under load. It also sends
  invalid and maximum-size submissions.

Pass/fail thresholds are evaluated when the run ends (see :func:`check_thresholds`)
and reflected in the process exit code, so the suite can gate a CI pipeline::

    # interactive UI on http://localhost:8089
    locust -f loadtests/locustfile.py --host http://127.0.0.1:5123

    # headless: 50 users, ramp 10/s, run for 2 minutes
    locust -f loadtests/locustfile.py --host http://127.0.0.1:5123 \\
        --headless -u 50 -r 10 -t 2m --csv loadtests/results/run

    # heavy: spread the load generation over 4 worker processes
    locust -f loadtests/locustfile.py --host http://127.0.0.1:5123 \\
        --headless -u 1000 -r 100 -t 5m --processes 4

Environment variables:

``LOAD_MAX_FAIL_RATIO``   max fraction of failed requests (default ``0.01``)
``LOAD_MAX_P95_MS``       max 95th-percentile response time in ms (default ``800``)
``LOAD_MAX_AVG_MS``       max average response time in ms (default ``400``)
``LOAD_MIN_REQUESTS``     minimum number of requests for a valid run (default ``1``)
``LOAD_ALLOW_RATE_LIMIT`` treat ``429`` on the contact form as success (default ``0``)
``LOAD_EXPECT_PDF``       also request ``/download-pdf`` and expect ``200`` (default ``0``)

The target app should run with ``CONTACT_RATE_LIMIT=0`` (or ``LOAD_ALLOW_RATE_LIMIT=1``
here) and with either ``MAIL_SUPPRESS_SEND=1`` or the bundled ``resumeapp-smtp`` server,
so that no real emails are sent.
"""

from __future__ import annotations

import os
import random
import re
import string
from typing import Any

from locust import between, events, task
from locust.contrib.fasthttp import FastHttpUser
from locust.env import Environment
from locust.runners import WorkerRunner
from locust.stats import StatsEntry

CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')

TECHNOLOGIES = ["Spark", "Airflow", "GCP", "Kafka", "Scala", "Snowflake", "Kubernetes", "Python", "Terraform"]
MAX_MESSAGE = 5000


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def random_text(length: int) -> str:
    alphabet = string.ascii_letters + "     "
    return "".join(random.choice(alphabet) for _ in range(length)).strip() or "x" * length


class Visitor(FastHttpUser):
    """Reads pages, the API and assets – the dominant traffic pattern.

    ``FastHttpUser`` (geventhttpclient) is used instead of the python-requests
    based ``HttpUser``: it needs roughly 5× less CPU per request, which matters
    when a single machine has to simulate ~1000 users, and it keeps one
    persistent connection per user, so the load generator does not run out of
    ephemeral ports.
    """

    weight = 6
    wait_time = between(0.5, 2.0)

    @task(5)
    def home(self) -> None:
        self.client.get("/", name="GET /")

    @task(4)
    def experience(self) -> None:
        self.client.get("/experience", name="GET /experience")

    @task(2)
    def experience_filtered(self) -> None:
        tech = random.choice(TECHNOLOGIES)
        # The filter is client-side; the query string must not break the page.
        self.client.get(f"/experience?q={tech}", name="GET /experience?q=<tech>")

    @task(3)
    def skills(self) -> None:
        self.client.get("/skills", name="GET /skills")

    @task(2)
    def education(self) -> None:
        self.client.get("/education", name="GET /education")

    @task(2)
    def full_cv(self) -> None:
        self.client.get("/cv", name="GET /cv")

    @task(3)
    def api(self) -> None:
        with self.client.get("/api/cv", name="GET /api/cv", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
            elif "experience" not in response.json():
                response.failure("payload missing 'experience'")

    @task(2)
    def static_assets(self) -> None:
        self.client.get("/static/css/style.css", name="GET /static/css/style.css")
        self.client.get("/static/js/main.js", name="GET /static/js/main.js")

    @task(1)
    def not_found(self) -> None:
        with self.client.get(
            f"/missing-{random.randint(1, 10_000)}", name="GET /<404>", catch_response=True
        ) as response:
            if response.status_code == 404:
                response.success()
            else:
                response.failure(f"expected 404, got {response.status_code}")

    @task(1)
    def download_pdf(self) -> None:
        if not env_flag("LOAD_EXPECT_PDF"):
            return
        self.client.get("/download-pdf", name="GET /download-pdf")


class ContactSender(FastHttpUser):
    """Fills in the contact form – the only write path of the application."""

    weight = 2
    wait_time = between(1.0, 3.0)
    csrf_token: str = ""

    def on_start(self) -> None:
        self.refresh_token()

    def refresh_token(self) -> None:
        response = self.client.get("/contact", name="GET /contact")
        match = CSRF_RE.search(response.text or "")
        self.csrf_token = match.group(1) if match else ""

    def _payload(self, **overrides: str) -> dict[str, str]:
        n = random.randint(1, 1_000_000)
        data = {
            "csrf_token": self.csrf_token,
            "name": f"Load Tester {n}",
            "email": f"load.tester.{n}@example.com",
            "subject": f"Load test message #{n}",
            "message": f"Automated load-test submission number {n}. Please ignore this message.",
            "website": "",
        }
        data.update(overrides)
        return data

    def _post(self, name: str, data: dict[str, str], expected_status: int) -> None:
        with self.client.post("/contact", data=data, name=name, catch_response=True, allow_redirects=False) as response:
            rate_limited_ok = response.status_code == 429 and env_flag("LOAD_ALLOW_RATE_LIMIT")
            if response.status_code == expected_status or rate_limited_ok:
                response.success()
            elif response.status_code == 400 and "session has expired" in (response.text or ""):
                # CSRF token rotated (e.g. server restarted) – fetch a new one.
                self.refresh_token()
                response.failure("csrf token rejected; refreshed")
            else:
                response.failure(f"expected {expected_status}, got {response.status_code}")

    @task(6)
    def submit_valid(self) -> None:
        self._post("POST /contact (valid)", self._payload(), 302)

    @task(2)
    def submit_max_size(self) -> None:
        self._post("POST /contact (5000 chars)", self._payload(message=random_text(MAX_MESSAGE)), 302)

    @task(2)
    def submit_invalid(self) -> None:
        self._post(
            "POST /contact (invalid)", self._payload(name="Invalid Sender", email="not-an-email", message="short"), 400
        )

    @task(1)
    def submit_honeypot(self) -> None:
        # Bots get a fake success; nothing must be sent.
        self._post("POST /contact (honeypot)", self._payload(name="Honeypot Bot", website="http://spam.example"), 302)


# --- pass/fail thresholds --------------------------------------------------------


def check_thresholds(total: StatsEntry) -> list[str]:
    """Return a list of threshold violations for the aggregated stats."""
    max_fail_ratio = env_float("LOAD_MAX_FAIL_RATIO", 0.01)
    max_p95 = env_float("LOAD_MAX_P95_MS", 800)
    max_avg = env_float("LOAD_MAX_AVG_MS", 400)
    min_requests = int(env_float("LOAD_MIN_REQUESTS", 1))

    violations: list[str] = []
    if total.num_requests < min_requests:
        violations.append(f"only {total.num_requests} requests were made (minimum {min_requests})")
    if total.num_requests == 0:
        return violations

    p95 = total.get_response_time_percentile(0.95) or 0
    if total.fail_ratio > max_fail_ratio:
        violations.append(f"failure ratio {total.fail_ratio:.2%} exceeds {max_fail_ratio:.2%}")
    if p95 > max_p95:
        violations.append(f"p95 response time {p95:.0f} ms exceeds {max_p95:.0f} ms")
    if total.avg_response_time > max_avg:
        violations.append(f"average response time {total.avg_response_time:.0f} ms exceeds {max_avg:.0f} ms")
    return violations


def enforce_thresholds(environment: Environment, **_kwargs: Any) -> None:
    """``quitting`` listener: print a summary and fail the run on violations."""
    if isinstance(environment.runner, WorkerRunner):
        # With ``--processes``/distributed runs this fires in every worker too, but
        # workers reset their stats after each report; only the master has totals.
        return
    total = environment.stats.total
    violations = check_thresholds(total)
    p95 = total.get_response_time_percentile(0.95) or 0
    print(
        f"\nLoad summary: {total.num_requests} requests, {total.num_failures} failures "
        f"({total.fail_ratio:.2%}), avg {total.avg_response_time:.0f} ms, p95 {p95:.0f} ms, "
        f"{total.total_rps:.1f} req/s"
    )
    if violations:
        for violation in violations:
            print(f"THRESHOLD VIOLATED: {violation}")
        environment.process_exit_code = 1
    else:
        print("All load thresholds met.")


events.quitting.add_listener(enforce_thresholds)  # type: ignore[no-untyped-call]

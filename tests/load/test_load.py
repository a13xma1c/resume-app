"""Volumetric load tests: run Locust headless against the live app + SMTP server.

Locust is executed as a subprocess (its gevent monkey-patching must not touch
the pytest process, which runs the Flask and SMTP servers on real threads).
Results are read back from the CSV files Locust writes.

Tunables (environment variables): ``LOAD_USERS`` (default 25),
``LOAD_SPAWN_RATE`` (default 25), ``LOAD_DURATION`` seconds (default 10).
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from resumeapp import create_app
from resumeapp.smtp_server import DevSMTPServer

from ..live_server import LiveServer

ROOT = Path(__file__).resolve().parents[2]
LOCUSTFILE = ROOT / "loadtests" / "locustfile.py"

USERS = int(os.environ.get("LOAD_USERS", "25"))
SPAWN_RATE = int(os.environ.get("LOAD_SPAWN_RATE", "25"))
DURATION = int(os.environ.get("LOAD_DURATION", "10"))

# Generous CI-safe ceilings for a single-process dev server on shared hardware.
MAX_FAIL_RATIO = 0.0
MAX_P95_MS = 2000
MIN_TOTAL_REQUESTS = USERS * 2


@dataclass(frozen=True)
class RequestStats:
    name: str
    requests: int
    failures: int
    median_ms: float
    p95_ms: float
    avg_ms: float

    @property
    def fail_ratio(self) -> float:
        return self.failures / self.requests if self.requests else 0.0


@dataclass(frozen=True)
class LoadRun:
    exit_code: int
    stdout: str
    stats: dict[str, RequestStats]
    failures: list[dict[str, str]]
    emails_received: int

    @property
    def total(self) -> RequestStats:
        return self.stats["Aggregated"]


def parse_stats(csv_path: Path) -> dict[str, RequestStats]:
    stats: dict[str, RequestStats] = {}
    with csv_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            stats[row["Name"]] = RequestStats(
                name=row["Name"],
                requests=int(row["Request Count"]),
                failures=int(row["Failure Count"]),
                median_ms=float(row["Median Response Time"]),
                p95_ms=float(row["95%"]),
                avg_ms=float(row["Average Response Time"]),
            )
    return stats


@pytest.fixture(scope="module")
def smtp_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[DevSMTPServer]:
    with DevSMTPServer(port=0, maildir=tmp_path_factory.mktemp("load-outbox")) as server:
        yield server


@pytest.fixture(scope="module")
def live_server(smtp_server: DevSMTPServer) -> Iterator[LiveServer]:
    app = create_app(
        {
            "SECRET_KEY": "load-secret",
            "CONTACT_RECIPIENT": "owner@example.com",
            "MAIL_DEFAULT_SENDER": "noreply@example.com",
            "CONTACT_RATE_LIMIT": 0,
            **smtp_server.mail_config(),
        }
    )
    # Keep the request log quiet: thousands of lines would swamp the report.
    import logging

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    with LiveServer(app) as server:
        yield server


@pytest.fixture(scope="module")
def load_run(live_server: LiveServer, smtp_server: DevSMTPServer, tmp_path_factory: pytest.TempPathFactory) -> LoadRun:
    """Execute one headless Locust run and collect its results (shared by all tests)."""
    out_dir = tmp_path_factory.mktemp("locust")
    prefix = out_dir / "run"
    command = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(LOCUSTFILE),
        "--host",
        live_server.url,
        "--headless",
        "-u",
        str(USERS),
        "-r",
        str(SPAWN_RATE),
        "-t",
        f"{DURATION}s",
        "--csv",
        str(prefix),
        "--only-summary",
        "--loglevel",
        "WARNING",
    ]
    env = {
        **os.environ,
        "LOAD_MAX_FAIL_RATIO": str(MAX_FAIL_RATIO),
        "LOAD_MAX_P95_MS": str(MAX_P95_MS),
        "LOAD_MAX_AVG_MS": str(MAX_P95_MS),
        "LOAD_MIN_REQUESTS": str(MIN_TOTAL_REQUESTS),
    }
    smtp_server.clear()
    completed = subprocess.run(command, capture_output=True, text=True, env=env, timeout=DURATION + 90, check=False)
    stats = parse_stats(prefix.with_name("run_stats.csv"))

    failures: list[dict[str, str]] = []
    failures_csv = prefix.with_name("run_failures.csv")
    if failures_csv.exists():
        with failures_csv.open(newline="") as handle:
            failures = list(csv.DictReader(handle))

    # Give in-flight SMTP deliveries a moment to land before counting.
    expected_mails = sum(
        s.requests - s.failures
        for name, s in stats.items()
        if name in {"POST /contact (valid)", "POST /contact (5000 chars)"}
    )
    smtp_server.wait_for_messages(expected_mails, timeout=10)

    return LoadRun(
        exit_code=completed.returncode,
        stdout=completed.stdout + completed.stderr,
        stats=stats,
        failures=failures,
        emails_received=len(smtp_server.messages),
    )


def test_locust_run_completes_and_meets_thresholds(load_run: LoadRun) -> None:
    assert load_run.exit_code == 0, f"Locust reported threshold violations:\n{load_run.stdout}"
    assert "All load thresholds met." in load_run.stdout


def test_generated_meaningful_volume(load_run: LoadRun) -> None:
    total = load_run.total
    assert total.requests >= MIN_TOTAL_REQUESTS, f"only {total.requests} requests in {DURATION}s"
    # Every endpoint family received traffic.
    for name in ("GET /", "GET /experience", "GET /skills", "GET /education", "GET /cv", "GET /api/cv", "GET /contact"):
        assert name in load_run.stats, f"{name} never requested"
        assert load_run.stats[name].requests > 0


def test_no_failed_requests(load_run: LoadRun) -> None:
    assert load_run.failures == [], f"unexpected failures: {load_run.failures[:5]}"
    assert load_run.total.failures == 0


def test_latency_within_budget(load_run: LoadRun) -> None:
    total = load_run.total
    assert total.p95_ms <= MAX_P95_MS, f"p95 {total.p95_ms} ms exceeds {MAX_P95_MS} ms"
    assert total.median_ms <= total.p95_ms
    for name, entry in load_run.stats.items():
        assert entry.p95_ms <= MAX_P95_MS, f"{name}: p95 {entry.p95_ms} ms exceeds {MAX_P95_MS} ms"


def test_contact_form_volume_and_outcomes(load_run: LoadRun) -> None:
    valid = load_run.stats.get("POST /contact (valid)")
    invalid = load_run.stats.get("POST /contact (invalid)")
    assert valid is not None and valid.requests > 0, "no valid contact submissions were made"
    assert valid.failures == 0
    assert invalid is not None and invalid.requests > 0
    assert invalid.failures == 0  # 400s are the expected outcome there


def test_every_accepted_submission_produced_an_email(load_run: LoadRun) -> None:
    accepted = sum(
        s.requests - s.failures
        for name, s in load_run.stats.items()
        if name in {"POST /contact (valid)", "POST /contact (5000 chars)"}
    )
    assert accepted > 0
    # Every accepted submission must have produced an email. When the run
    # deadline hits, Locust kills in-flight users, so the server may finish
    # (and email) a handful of submissions that never reached the stats –
    # at most one per simulated user.
    assert accepted <= load_run.emails_received <= accepted + USERS


def test_rejected_submissions_do_not_generate_email(load_run: LoadRun, smtp_server: DevSMTPServer) -> None:
    rejected = sum(
        s.requests
        for name, s in load_run.stats.items()
        if name in {"POST /contact (invalid)", "POST /contact (honeypot)"}
    )
    assert rejected > 0, "no invalid/honeypot submissions were made"
    senders = [str(m.message["Reply-To"]) for m in smtp_server.messages]
    assert not any("Invalid Sender" in s or "not-an-email" in s for s in senders)
    assert not any("Honeypot Bot" in s for s in senders)


def test_large_payload_submissions_succeed(load_run: LoadRun) -> None:
    large = load_run.stats.get("POST /contact (5000 chars)")
    if large is None or large.requests == 0:
        pytest.skip("no 5000-char submissions happened in this short run")
    assert large.failures == 0
    assert large.p95_ms <= MAX_P95_MS


def test_error_pages_served_quickly(load_run: LoadRun) -> None:
    not_found = load_run.stats.get("GET /<404>")
    if not_found is None:
        pytest.skip("no 404 requests happened in this short run")
    assert not_found.failures == 0
    assert not_found.p95_ms <= MAX_P95_MS

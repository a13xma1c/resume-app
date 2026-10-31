"""Staged ramp-up / peak / cool-down profile using the same user classes.

    locust -f loadtests/locustfile_ramp.py --host http://127.0.0.1:5123 --headless

When a ``LoadTestShape`` is present, Locust ignores ``-u``/``-r``/``-t`` and
follows the stages below instead. Tune them with ``LOAD_PEAK_USERS``.
"""

from __future__ import annotations

import os

from locust import LoadTestShape

# Locust puts the locustfile's directory on sys.path, so the sibling module is
# importable by its bare name at runtime; the package form keeps type checkers happy.
try:
    from loadtests.locustfile import ContactSender, Visitor
except ModuleNotFoundError:  # pragma: no cover - running via `locust -f loadtests/locustfile_ramp.py`
    from locustfile import ContactSender, Visitor  # type: ignore[import-not-found,no-redef]  # noqa: F401

PEAK_USERS = int(os.environ.get("LOAD_PEAK_USERS", "60"))


class StagesShape(LoadTestShape):
    """Warm-up → steady state → peak burst → cool-down."""

    stages = (
        # (end time in seconds, users, spawn rate)
        (30, PEAK_USERS // 4, 5),
        (90, PEAK_USERS // 2, 10),
        (120, PEAK_USERS, 20),
        (150, PEAK_USERS // 2, 10),
        (170, 1, 10),
    )

    def tick(self) -> tuple[int, float] | None:
        run_time: float = self.get_run_time()  # type: ignore[no-untyped-call]
        for end, users, spawn_rate in self.stages:
            if run_time < end:
                return users, spawn_rate
        return None

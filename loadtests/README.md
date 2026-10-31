# Load tests

Volumetric load tests built with [Locust](https://locust.io).

## Running against a local server

Start the app with the rate limiter off and the bundled SMTP sink so that no real
emails are sent:

```bash
DEV_SMTP=1 CONTACT_RATE_LIMIT=0 FLASK_DEBUG=0 uv run resumeapp
```

Then, in another terminal:

```bash
# Interactive UI on http://localhost:8089
uv run locust -f loadtests/locustfile.py --host http://127.0.0.1:5123

# Headless, CI-friendly: 50 users, ramp 10 users/s, 2 minutes, CSV output
uv run locust -f loadtests/locustfile.py --host http://127.0.0.1:5123 \
    --headless -u 50 -r 10 -t 2m --csv loadtests/results/run

# Staged ramp / peak / cool-down profile
LOAD_PEAK_USERS=100 uv run locust -f loadtests/locustfile_ramp.py --host http://127.0.0.1:5123 --headless
```

The process exits non-zero when a threshold is violated (see the top of
`locustfile.py` for the `LOAD_*` environment variables that tune them).

## Running from pytest

`tests/load/` spins up the app and the SMTP server in-process and runs Locust headless
as a subprocess against them, then asserts on the collected statistics (failure ratio,
p95 latency, and that every accepted contact submission produced exactly one email):

```bash
uv run pytest -m load
```

Tune the pytest run with `LOAD_USERS`, `LOAD_SPAWN_RATE` and `LOAD_DURATION` (seconds).

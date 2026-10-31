# Load tests

Volumetric load tests built with [Locust](https://locust.io). Users are simulated with
`FastHttpUser` (one persistent HTTP connection per user, ~5× less CPU than python-requests),
so a single machine can drive a thousand users.

## Running from pytest (recommended)

```bash
uv run pytest -m load                                                 # ~10 s smoke run
LOAD_USERS=1000 LOAD_SPAWN_RATE=50 LOAD_DURATION=60 uv run pytest -m load   # heavy run
```

`tests/load/` starts the SMTP sink in-process and the app on **several worker processes**
sharing one listening socket (the pre-fork model gunicorn uses), then runs Locust headless as
a subprocess and asserts on the collected statistics: no failed requests, p95 latency within
budget for every endpoint, traffic on every page, and that each accepted contact submission
produced an email while invalid/honeypot submissions produced none.

| Variable | Default | Meaning |
|---|---|---|
| `LOAD_USERS` | `25` | simulated users |
| `LOAD_SPAWN_RATE` | `25` | users started per second |
| `LOAD_DURATION` | `10` | seconds |
| `LOAD_SERVER_PROCESSES` | half the cores (1–4) | app worker processes |
| `LOAD_PROCESSES` | `1` | Locust worker processes (`--processes`); raise for 1000+ users |
| `LOAD_MAX_P95_MS` | `2000` | latency budget, applied per endpoint |
| `LOAD_MAX_FAIL_RATIO` | `0` | tolerated failure ratio |

> A single Python process is GIL-bound and serves a few hundred requests per second, while 1000
> users with 0.5–2 s think time demand ~700 req/s. Give the server enough workers
> (`LOAD_SERVER_PROCESSES`) and the load generator enough processes (`LOAD_PROCESSES`) for the
> machine you run on; a laptop running *both* sides will be CPU-bound long before the app is.

## Running Locust standalone

Start the SMTP sink and the app on a production-grade server with keep-alive and several
threads — **not** the Werkzeug development server (`uv run resumeapp`), which closes the
connection after every response; at a few hundred requests per second that exhausts the
client's ephemeral ports within seconds on macOS (`OSError: Can't assign requested address`).

```bash
uv run resumeapp-smtp --port 1025 --maildir ./mail-outbox

MAIL_SERVER=127.0.0.1 MAIL_PORT=1025 MAIL_USE_TLS=false CONTACT_RATE_LIMIT=0 SECRET_KEY=load \
  uv run waitress-serve --listen 127.0.0.1:5123 --threads 16 --connection-limit 4000 \
  --call resumeapp:create_app
```

Then, in another terminal:

```bash
# Interactive UI on http://localhost:8089
uv run locust -f loadtests/locustfile.py --host http://127.0.0.1:5123

# Headless, CI-friendly: 50 users, ramp 10 users/s, 2 minutes, CSV output
uv run locust -f loadtests/locustfile.py --host http://127.0.0.1:5123 \
    --headless -u 50 -r 10 -t 2m --csv loadtests/results/run

# Heavy: 1000 users, load generation spread over 4 processes
uv run locust -f loadtests/locustfile.py --host http://127.0.0.1:5123 \
    --headless -u 1000 -r 100 -t 5m --processes 4

# Staged ramp / peak / cool-down profile
LOAD_PEAK_USERS=100 uv run locust -f loadtests/locustfile_ramp.py --host http://127.0.0.1:5123 --headless
```

The process exits non-zero when a threshold is violated (see the top of `locustfile.py` for
the `LOAD_*` environment variables that tune them). For a multi-process app server use
gunicorn (`gunicorn -w 4 'resumeapp:create_app()'`) on Linux/macOS.

"""Run the Flask app on a real WSGI server in a background thread.

Used by the browser (Playwright) and load (Locust) tests. Waitress is used
rather than Werkzeug's development server because the latter sends
``Connection: close`` on every response: under load each request then costs
a new TCP connection and the load-generating machine quickly exhausts its
ephemeral ports (``OSError: Can't assign requested address``). Waitress
supports HTTP/1.1 keep-alive, so each simulated user holds a single connection.
"""

from __future__ import annotations

import contextlib
import logging
import multiprocessing
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from types import TracebackType
from typing import Any

from flask import Flask
from waitress import wasyncore
from waitress.server import BaseWSGIServer, create_server

from resumeapp import create_app

logger = logging.getLogger(__name__)

# Enough headroom for a heavy local Locust run (each user keeps one connection open).
DEFAULT_CONNECTION_LIMIT = 4096
DEFAULT_THREADS = 16
MIN_OPEN_FILES = 10_240


def raise_open_file_limit(minimum: int = MIN_OPEN_FILES) -> int | None:
    """Lift the soft ``RLIMIT_NOFILE`` so thousands of keep-alive sockets fit.

    macOS in particular defaults to a very low soft limit (often 256). Returns
    the resulting soft limit, or ``None`` where the platform has no ``resource``
    module (Windows) or the limit cannot be changed.
    """
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows
        return None
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft >= minimum or soft == resource.RLIM_INFINITY:
        return soft
    target = minimum if hard == resource.RLIM_INFINITY else min(minimum, hard)
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ValueError, OSError):  # pragma: no cover - depends on OS policy
        logger.warning("Could not raise open-file limit from %s to %s", soft, target)
        return soft
    return target


class LiveServer:
    """Serve ``app`` on an ephemeral loopback port until stopped."""

    def __init__(
        self,
        app: Flask,
        host: str = "127.0.0.1",
        *,
        threads: int = DEFAULT_THREADS,
        connection_limit: int = DEFAULT_CONNECTION_LIMIT,
    ) -> None:
        self.app = app
        self.host = host
        # Owning the socket map lets ``stop()`` close lingering keep-alive
        # channels so the I/O loop can exit promptly.
        self._map: dict[int, Any] = {}
        server = create_server(
            app,
            host=host,
            port=0,
            map=self._map,
            threads=threads,
            connection_limit=connection_limit,
            channel_timeout=10,
            cleanup_interval=1,
        )
        # A single host/port always yields a TcpWSGIServer (not a MultiSocketServer).
        assert isinstance(server, BaseWSGIServer)
        self._server: BaseWSGIServer = server
        self.port: int = int(server.effective_port)  # type: ignore[attr-defined]  # missing from the stubs
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="live-server", daemon=True)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _serve(self) -> None:
        """Waitress's I/O loop, but interruptible.

        ``server.run()`` loops until the socket map is empty, so stopping it means
        closing sockets from another thread while it sits in ``select()`` – which
        surfaces as ``OSError: Bad file descriptor`` in the server thread. Polling
        with a stop flag lets ``stop()`` join the thread first and close sockets
        afterwards, race-free.
        """
        poll = wasyncore.poll2 if self._server.adj.asyncore_use_poll else wasyncore.poll
        while not self._stop.is_set() and self._map:
            poll(0.1, self._map)

    def start(self) -> LiveServer:
        raise_open_file_limit()
        logging.getLogger("waitress").setLevel(logging.WARNING)  # hide the "Serving on ..." banner
        logging.getLogger("waitress.queue").setLevel(logging.ERROR)  # "Task queue depth is N" is expected under load
        self._thread.start()
        return self

    def stop(self) -> None:
        # 1. Stop the I/O loop and wait for it, so nothing is inside select().
        self._stop.set()
        self._thread.join(timeout=10)
        # 2. Let worker threads finish in-flight requests.
        self._server.task_dispatcher.shutdown(cancel_pending=True, timeout=10)
        # 3. Now it is safe to close the listener, the trigger pipe and any channels.
        self._server.close()
        for channel in list(self._map.values()):
            with contextlib.suppress(Exception):  # best effort during teardown
                channel.close()

    def __enter__(self) -> LiveServer:
        return self.start()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.stop()


# --- multi-process variant -----------------------------------------------------------


def default_server_processes() -> int:
    """A sensible worker count for load tests: half the cores, between 1 and 4."""
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def _serve_forever(config: Mapping[str, Any], sock: socket.socket, threads: int, connection_limit: int) -> None:
    """Worker-process entry point: build the app and serve on the shared socket."""
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger("waitress").setLevel(logging.ERROR)
    app = create_app(dict(config))
    server = create_server(
        app,
        sockets=[sock],
        threads=threads,
        connection_limit=connection_limit,
        channel_timeout=10,
        cleanup_interval=1,
    )
    server.run()


class MultiProcessLiveServer:
    """Serve the app from several worker processes sharing one listening socket.

    A single Python process is GIL-bound and saturates at a few hundred
    requests per second; production deployments run multiple workers, and so
    should a load test that simulates hundreds or thousands of users. The
    parent binds the socket and the kernel distributes accepted connections
    across the workers (the same pre-fork model gunicorn uses). Workers are
    *spawned* rather than forked because the pytest process is multi-threaded.
    """

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        processes: int | None = None,
        host: str = "127.0.0.1",
        threads: int = DEFAULT_THREADS,
        connection_limit: int = DEFAULT_CONNECTION_LIMIT,
    ) -> None:
        if processes is not None and processes < 1:
            raise ValueError("processes must be >= 1")
        self.config = dict(config)
        self.host = host
        self.processes = processes or default_server_processes()
        self.threads = threads
        self.connection_limit = connection_limit
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, 0))
        self._sock.listen(1024)
        self.port: int = int(self._sock.getsockname()[1])
        self._workers: list[multiprocessing.process.BaseProcess] = []

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def running(self) -> bool:
        return any(worker.is_alive() for worker in self._workers)

    def start(self, ready_timeout: float = 30.0) -> MultiProcessLiveServer:
        raise_open_file_limit()
        ctx = multiprocessing.get_context("spawn")
        for index in range(self.processes):
            worker = ctx.Process(
                target=_serve_forever,
                args=(self.config, self._sock, self.threads, self.connection_limit),
                name=f"live-server-{index}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)
        self._wait_until_ready(ready_timeout)
        return self

    def _wait_until_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if not self.running:
                raise RuntimeError("live server workers exited during start-up")
            try:
                with urllib.request.urlopen(f"{self.url}/api/cv", timeout=2) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_error = exc
            time.sleep(0.1)
        raise RuntimeError(f"live server did not become ready within {timeout}s: {last_error}")

    def stop(self) -> None:
        for worker in self._workers:
            if worker.is_alive():
                worker.terminate()
        for worker in self._workers:
            worker.join(timeout=10)
            if worker.is_alive():  # pragma: no cover - stubborn worker
                worker.kill()
                worker.join(timeout=5)
        self._workers.clear()
        self._sock.close()

    def __enter__(self) -> MultiProcessLiveServer:
        return self.start()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.stop()

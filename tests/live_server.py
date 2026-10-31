"""Run the Flask app in a background thread for browser and load tests."""

from __future__ import annotations

import threading
from types import TracebackType

from flask import Flask
from werkzeug.serving import BaseWSGIServer, make_server


class LiveServer:
    """Serve ``app`` on an ephemeral loopback port until stopped."""

    def __init__(self, app: Flask, host: str = "127.0.0.1") -> None:
        self.app = app
        self.host = host
        self._server: BaseWSGIServer = make_server(host, 0, app, threaded=True)
        self.port: int = int(self._server.server_port)
        self._thread = threading.Thread(target=self._server.serve_forever, name="live-server", daemon=True)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> LiveServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> LiveServer:
        return self.start()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.stop()

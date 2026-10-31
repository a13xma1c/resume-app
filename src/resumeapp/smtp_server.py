"""A small SMTP server that receives the contact-form emails.

Built on :mod:`aiosmtpd`, it accepts mail on a local port, keeps every message
in memory and (optionally) writes each one to a directory as an ``.eml`` file
so it can be opened in any mail client. It is meant for local development,
end-to-end tests and load tests – it never relays anything anywhere.

Run it standalone::

    resumeapp-smtp --port 1025 --maildir ./mail-outbox

and point the web app at it::

    MAIL_SERVER=127.0.0.1 MAIL_PORT=1025 MAIL_USE_TLS=false resumeapp

or simply start both together with ``DEV_SMTP=1 resumeapp``.
"""

from __future__ import annotations

import argparse
import email
import email.policy
import logging
import signal
import socket
import threading
import time
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from types import FrameType, TracebackType
from typing import Any

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, AuthResult, Envelope, LoginPassword, Session

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1025


@dataclass(frozen=True)
class StoredMessage:
    """An email accepted by the server, plus its SMTP envelope."""

    mail_from: str
    rcpt_tos: tuple[str, ...]
    message: EmailMessage
    received_at: datetime
    peer: str
    path: Path | None = None

    @property
    def subject(self) -> str:
        return str(self.message.get("Subject", ""))

    @property
    def body(self) -> str:
        body = self.message.get_body(preferencelist=("plain", "html"))
        if body is None:
            return ""
        content = body.get_content()
        return content if isinstance(content, str) else content.decode("utf-8", "replace")


class MailboxHandler:
    """aiosmtpd handler that stores messages in memory and on disk."""

    def __init__(self, maildir: Path | None = None) -> None:
        self.maildir = maildir
        self._messages: list[StoredMessage] = []
        self._lock = threading.Lock()
        self._received = threading.Condition(self._lock)
        if maildir is not None:
            maildir.mkdir(parents=True, exist_ok=True)

    @property
    def messages(self) -> list[StoredMessage]:
        with self._lock:
            return list(self._messages)

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()

    def wait_for_messages(self, count: int = 1, timeout: float = 5.0) -> list[StoredMessage]:
        """Block until at least ``count`` messages have arrived (or time out)."""
        with self._received:
            self._received.wait_for(lambda: len(self._messages) >= count, timeout=timeout)
            return list(self._messages)

    async def handle_DATA(self, server: SMTP, session: Session, envelope: Envelope) -> str:
        raw = envelope.content or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "surrogateescape")
        parsed = email.message_from_bytes(raw, policy=email.policy.default)
        assert isinstance(parsed, EmailMessage)
        now = datetime.now(UTC)
        peer = session.peer[0] if session.peer else "?"

        path = None
        if self.maildir is not None:
            path = self._write(parsed, now)

        stored = StoredMessage(
            mail_from=envelope.mail_from or "",
            rcpt_tos=tuple(envelope.rcpt_tos),
            message=parsed,
            received_at=now,
            peer=peer,
            path=path,
        )
        with self._received:
            self._messages.append(stored)
            self._received.notify_all()

        logger.info(
            "Received mail from %s to %s | Subject: %s%s",
            stored.mail_from,
            ", ".join(stored.rcpt_tos),
            stored.subject,
            f" | saved to {path}" if path else "",
        )
        return "250 Message accepted for delivery"

    def _write(self, message: EmailMessage, now: datetime) -> Path:
        assert self.maildir is not None
        # Note: build file names by hand – ``Path.with_suffix`` would treat the
        # fractional seconds as a suffix and mangle the name.
        stem = f"{now.strftime('%Y%m%dT%H%M%S-%f')}-{threading.get_ident() % 10_000:04d}"
        path = self.maildir / f"{stem}.eml"
        counter = 1
        while path.exists():
            path = self.maildir / f"{stem}-{counter}.eml"
            counter += 1
        path.write_bytes(message.as_bytes())
        return path


class DevSMTPServer:
    """Threaded SMTP server wrapper with a simple start/stop lifecycle.

    ``username``/``password`` enable ``AUTH PLAIN``/``AUTH LOGIN`` checks so
    the client's login path can be exercised; without them any client is
    accepted. TLS is intentionally not offered – this is a local dev tool.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        maildir: Path | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        if (username is None) != (password is None):
            raise ValueError("username and password must be provided together")
        if port < 0:
            raise ValueError("port must be >= 0 (0 picks a free port)")
        self.host = host
        self._requested_port = port
        self.username = username
        self.password = password
        self.handler = MailboxHandler(maildir)
        self._controller: Controller | None = None

    # -- lifecycle -----------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._controller is not None

    @property
    def port(self) -> int:
        """The bound port (resolves 0 → the OS-assigned port once started)."""
        if self._controller is not None:
            return int(self._controller.port)
        return self._requested_port

    def start(self) -> DevSMTPServer:
        if self._controller is not None:
            raise RuntimeError("server is already running")
        kwargs: dict[str, Any] = {}
        if self.username is not None:
            kwargs.update(
                authenticator=self._authenticate,
                auth_required=True,
                auth_require_tls=False,
            )
        # aiosmtpd cannot bind port 0 itself (it reconnects to ``port`` to
        # confirm start-up), so resolve an ephemeral port up front.
        port = self._requested_port or find_free_port(self.host)
        if self.username is not None:
            # aiosmtpd warns on every connection about AUTH without TLS; that is
            # a deliberate trade-off for a loopback-only development server.
            warnings.filterwarnings("ignore", message="Requiring AUTH while not requiring TLS", category=UserWarning)
        controller = Controller(self.handler, hostname=self.host, port=port, **kwargs)
        controller.start()
        self._controller = controller
        logger.info("Dev SMTP server listening on %s:%s", self.host, self.port)
        return self

    def stop(self) -> None:
        if self._controller is None:
            return
        self._controller.stop()
        self._controller = None
        logger.info("Dev SMTP server stopped")

    def __enter__(self) -> DevSMTPServer:
        return self.start()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.stop()

    # -- convenience ---------------------------------------------------------

    @property
    def messages(self) -> list[StoredMessage]:
        return self.handler.messages

    def clear(self) -> None:
        self.handler.clear()

    def wait_for_messages(self, count: int = 1, timeout: float = 5.0) -> list[StoredMessage]:
        return self.handler.wait_for_messages(count, timeout)

    def mail_config(self) -> dict[str, Any]:
        """Flask config values that point the web app at this server."""
        return {
            "MAIL_SERVER": self.host,
            "MAIL_PORT": self.port,
            "MAIL_USE_TLS": False,
            "MAIL_USE_SSL": False,
            "MAIL_USERNAME": self.username,
            "MAIL_PASSWORD": self.password,
            "MAIL_SUPPRESS_SEND": False,
        }

    def _authenticate(
        self, server: SMTP, session: Session, envelope: Envelope, mechanism: str, auth_data: Any
    ) -> AuthResult:
        if not isinstance(auth_data, LoginPassword):
            return AuthResult(success=False, handled=False)
        ok = (
            auth_data.login.decode("utf-8", "replace") == self.username
            and auth_data.password.decode("utf-8", "replace") == self.password
        )
        if not ok:
            logger.warning("Rejected SMTP login for user %r", auth_data.login)
        # handled=False lets aiosmtpd send the 235 / 535 status line itself.
        return AuthResult(success=ok, handled=False)


def find_free_port(host: str = DEFAULT_HOST) -> int:
    """Ask the OS for a currently unused TCP port on ``host``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def iter_eml_files(maildir: Path) -> Iterator[Path]:
    """Yield stored ``.eml`` files oldest-first."""
    yield from sorted(maildir.glob("*.eml"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resumeapp-smtp",
        description="Local SMTP server that captures contact-form emails.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"interface to bind (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to bind (default: {DEFAULT_PORT})")
    parser.add_argument(
        "--maildir",
        type=Path,
        default=Path("mail-outbox"),
        help="directory where received messages are written as .eml files (default: ./mail-outbox)",
    )
    parser.add_argument("--no-maildir", action="store_true", help="keep messages in memory only")
    parser.add_argument("--user", help="require SMTP AUTH with this username")
    parser.add_argument("--password", help="password for --user")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (args.user is None) != (args.password is None):
        build_parser().error("--user and --password must be given together")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    server = DevSMTPServer(
        args.host,
        args.port,
        maildir=None if args.no_maildir else args.maildir,
        username=args.user,
        password=args.password,
    )

    stop = threading.Event()

    def _on_signal(signum: int, frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    with server:
        print(f"SMTP server listening on {server.host}:{server.port} (Ctrl+C to stop)")
        if server.handler.maildir is not None:
            print(f"Messages are saved to {server.handler.maildir.resolve()}")
        print(
            "Point the app at it with: "
            f"MAIL_SERVER={server.host} MAIL_PORT={server.port} MAIL_USE_TLS=false"
            + (f" MAIL_USERNAME={server.username} MAIL_PASSWORD=..." if server.username else "")
        )
        while not stop.is_set():
            time.sleep(0.2)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

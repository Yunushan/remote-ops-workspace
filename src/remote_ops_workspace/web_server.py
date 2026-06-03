from __future__ import annotations

import http.server
import ipaddress
import socketserver
from functools import partial
from pathlib import Path

from . import command_safety as safe
from .paths import repo_root


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "worker-src 'self'; "
        "manifest-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        print(f"web: {format % args}")

    def end_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def list_directory(self, path: str):  # type: ignore[override]
        self.send_error(404, "Directory listing is disabled")
        return None


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def validate_web_bind(host: str, *, allow_public_bind: bool = False) -> str:
    normalized = safe.host(host, "web bind host").lower()
    if _is_loopback_host(normalized):
        return host
    if not allow_public_bind:
        raise ValueError(
            "serve-web refuses non-loopback bind hosts by default; "
            "use --allow-public-bind only for trusted networks or container entrypoints"
        )
    return host


def _is_loopback_host(host: str) -> bool:
    if host in {"localhost", "ip6-localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve_web(
    host: str = "127.0.0.1",
    port: int = 8765,
    directory: Path | None = None,
    *,
    allow_public_bind: bool = False,
) -> None:
    host = validate_web_bind(host, allow_public_bind=allow_public_bind)
    port = safe.port(port, "web port")
    web_dir = directory or (repo_root() / "apps" / "web")
    web_dir = web_dir.resolve()
    if not web_dir.exists() or not web_dir.is_dir():
        raise ValueError(f"web directory does not exist: {web_dir}")
    handler = partial(QuietHandler, directory=str(web_dir))
    with ReusableTCPServer((host, port), handler) as httpd:
        print(f"Remote Ops Web/PWA serving at http://{host}:{port}")
        if not _is_loopback_host(host.lower()):
            print("warning: Web/PWA is bound to a non-loopback interface; keep it on a trusted network.")
        httpd.serve_forever()

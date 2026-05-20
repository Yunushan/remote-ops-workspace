from __future__ import annotations

import http.server
import socketserver
from functools import partial
from pathlib import Path

from .paths import repo_root


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        print(f"web: {format % args}")


def serve_web(host: str = "127.0.0.1", port: int = 8765, directory: Path | None = None) -> None:
    web_dir = directory or (repo_root() / "apps" / "web")
    handler = partial(QuietHandler, directory=str(web_dir))
    with socketserver.TCPServer((host, port), handler) as httpd:
        print(f"Remote Ops Web/PWA serving at http://{host}:{port}")
        httpd.serve_forever()

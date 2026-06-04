import socket
from functools import partial
from pathlib import Path
from threading import Thread

from remote_ops_workspace.web_server import (
    SECURITY_HEADERS,
    QuietHandler,
    ReusableTCPServer,
    validate_web_bind,
)


def test_web_security_headers_include_browser_hardening() -> None:
    csp = SECURITY_HEADERS["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"
    assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    assert SECURITY_HEADERS["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in SECURITY_HEADERS["Permissions-Policy"]


def test_web_handler_emits_security_headers(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>ok</title>", encoding="utf-8")
    handler = partial(QuietHandler, directory=str(tmp_path))
    with ReusableTCPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with socket.create_connection((host, port), timeout=5) as client:
                client.sendall(b"GET /index.html HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                response = b""
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            headers = response.decode("iso-8859-1").split("\r\n\r\n", 1)[0]
            assert "X-Frame-Options: DENY" in headers
            assert "X-Content-Type-Options: nosniff" in headers
            assert "default-src 'self'" in headers
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_web_bind_rejects_public_hosts_without_explicit_opt_in() -> None:
    for host in ["0.0.0.0", "::", "192.0.2.10"]:
        try:
            validate_web_bind(host)
        except ValueError as exc:
            assert "--allow-public-bind" in str(exc)
        else:
            raise AssertionError(f"public web bind should require opt-in: {host}")


def test_web_bind_allows_loopback_and_explicit_public_opt_in() -> None:
    assert validate_web_bind("127.0.0.1") == "127.0.0.1"
    assert validate_web_bind("::1") == "::1"
    assert validate_web_bind("localhost") == "localhost"
    assert validate_web_bind("0.0.0.0", allow_public_bind=True) == "0.0.0.0"


def test_web_assets_avoid_persistent_profile_storage() -> None:
    app_js = Path("apps/web/app.js").read_text(encoding="utf-8")
    assert "sessionStorage" in app_js
    assert "localStorage" not in app_js
    assert "cleanDemoField" in app_js


def test_service_worker_cache_is_same_origin_get_only() -> None:
    service_worker = Path("apps/web/sw.js").read_text(encoding="utf-8")
    assert "event.request.method !== 'GET'" in service_worker
    assert "url.origin !== self.location.origin" in service_worker
    assert "caches.delete" in service_worker
    assert "remote-ops-workspace-static-v2" in service_worker


def test_web_container_defaults_are_hardened() -> None:
    dockerfile = Path("docker/Dockerfile.web").read_text(encoding="utf-8")
    compose = Path("docker/compose.yaml").read_text(encoding="utf-8")

    assert "USER 10001:10001" in dockerfile
    assert "--allow-public-bind" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "127.0.0.1:8765:8765" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose

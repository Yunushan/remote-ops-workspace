import json
import os
import socket
from functools import partial
from pathlib import Path
from threading import Thread

from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore
from remote_ops_workspace.web_server import (
    SECURITY_HEADERS,
    QuietHandler,
    ReusableTCPServer,
    WebProfileApi,
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


def test_web_handler_serves_enterprise_policy_endpoint(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>ok</title>", encoding="utf-8")
    (tmp_path / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "allow_user_profiles": False,
                "allow_custom_commands": False,
                "locked_settings": [{"key": "protocol", "value": "ssh"}],
            }
        ),
        encoding="utf-8",
    )
    old_home = os.environ.get("ROW_HOME")
    os.environ["ROW_HOME"] = str(tmp_path)
    handler = partial(QuietHandler, directory=str(tmp_path))
    with ReusableTCPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with socket.create_connection((host, port), timeout=5) as client:
                client.sendall(
                    b"GET /enterprise-policy.json HTTP/1.1\r\n"
                    b"Host: 127.0.0.1\r\nConnection: close\r\n\r\n"
                )
                response = b""
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            body = response.decode("iso-8859-1").split("\r\n\r\n", 1)[1]
            payload = json.loads(body)
            assert payload["active"] is True
            assert payload["allow_user_profiles"] is False
            assert payload["locked_settings"] == [{"key": "protocol", "value": "ssh"}]
        finally:
            server.shutdown()
            thread.join(timeout=5)
            if old_home is None:
                os.environ.pop("ROW_HOME", None)
            else:
                os.environ["ROW_HOME"] = old_home


def test_web_handler_serves_unauthenticated_liveness_endpoint(tmp_path: Path) -> None:
    handler = partial(QuietHandler, directory=str(tmp_path))
    with ReusableTCPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with socket.create_connection((host, port), timeout=5) as client:
                client.sendall(b"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                response = b""
                while chunk := client.recv(4096):
                    response += chunk
            assert response.startswith(b"HTTP/1.0 200")
            assert json.loads(response.split(b"\r\n\r\n", 1)[1]) == {"status": "ok"}
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


def test_browser_profile_api_requires_bearer_token_and_redacts_secret_fields(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    api = WebProfileApi(store, "x" * 24)

    assert api.authorized(None) is False
    assert api.authorized("Bearer wrong") is False
    assert api.authorized(f"Bearer {'x' * 24}") is True
    try:
        api.add_profile(
            {
                "name": "edge",
                "protocol": "ssh",
                "host": "edge.example.invalid",
                "credential_ref": "vault:edge",
            }
        )
    except ValueError as exc:
        assert "secret-bearing" in str(exc)
    else:
        raise AssertionError("browser API must reject credential references")

    try:
        api.add_profile(
            {
                "name": "option-secret",
                "protocol": "ssh",
                "host": "edge.example.invalid",
                "options": {"password": "not-for-browser"},
            }
        )
    except ValueError as exc:
        assert "secret-bearing options" in str(exc)
    else:
        raise AssertionError("browser API must reject secret-like option keys")

    created = api.add_profile({"name": "edge", "protocol": "ssh", "host": "edge.example.invalid"})
    assert created["name"] == "edge"
    assert "credential_ref" not in created
    store.add(Profile(name="vaulted", protocol="ssh", host="vault.example.invalid", credential_ref="vault:vaulted"))
    assert "credential_ref" not in api.profiles()[1]
    store.add(
        Profile(
            name="legacy-secret-option",
            protocol="ssh",
            host="legacy.example.invalid",
            options={"access_token": "legacy-value", "compression": "yes"},
        )
    )
    legacy = next(profile for profile in api.profiles() if profile["name"] == "legacy-secret-option")
    assert legacy["options"] == {"compression": "yes"}
    assert api.health() == {"api_version": 1, "status": "ok", "profile_count": 3}


def test_browser_profile_api_serves_authenticated_http_catalogue(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="edge", protocol="ssh", host="edge.example.invalid"))
    token = "t" * 24
    handler_type = type("ApiHandler", (QuietHandler,), {"api": WebProfileApi(store, token)})
    handler = partial(handler_type, directory=str(tmp_path))
    with ReusableTCPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with socket.create_connection((host, port), timeout=5) as client:
                client.sendall(
                    b"GET /api/v1/profiles HTTP/1.1\r\n"
                    b"Host: 127.0.0.1\r\n"
                    + f"Authorization: Bearer {token}\r\n".encode("ascii")
                    + b"Connection: close\r\n\r\n"
                )
                response = b""
                while chunk := client.recv(4096):
                    response += chunk
            headers, body = response.decode("iso-8859-1").split("\r\n\r\n", 1)
            assert headers.startswith("HTTP/1.0 200")
            assert json.loads(body)["profiles"][0]["name"] == "edge"
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_web_assets_avoid_persistent_profile_storage() -> None:
    app_js = Path("apps/web/app.js").read_text(encoding="utf-8")
    assert "sessionStorage" in app_js
    assert "localStorage" not in app_js
    assert "cleanDemoField" in app_js
    assert "loadEnterprisePolicy" in app_js
    assert "reviewEnterpriseWebProfile" in app_js
    assert "enterprise-policy.json" in app_js


def test_service_worker_cache_is_same_origin_get_only() -> None:
    service_worker = Path("apps/web/sw.js").read_text(encoding="utf-8")
    assert "event.request.method !== 'GET'" in service_worker
    assert "url.origin !== self.location.origin" in service_worker
    assert "caches.delete" in service_worker
    assert "remote-ops-workspace-static-v2" in service_worker


def test_web_pwa_declares_android_and_ios_browser_install_contract() -> None:
    manifest = json.loads(Path("apps/web/manifest.json").read_text(encoding="utf-8"))
    index = Path("apps/web/index.html").read_text(encoding="utf-8")
    styles = Path("apps/web/styles.css").read_text(encoding="utf-8")
    app = Path("apps/web/app.js").read_text(encoding="utf-8")
    service_worker = Path("apps/web/sw.js").read_text(encoding="utf-8")

    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in index
    assert '<link rel="manifest" href="manifest.json">' in index
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "./index.html"
    assert manifest["scope"] == "./"
    assert manifest["prefer_related_applications"] is False
    assert "serviceWorker" in app
    assert "manifest.json" in service_worker
    assert "repeat(auto-fit, minmax(280px, 1fr))" in styles
    assert "@media (max-width: 800px)" in styles


def test_web_container_defaults_are_hardened() -> None:
    dockerfile = Path("docker/Dockerfile.web").read_text(encoding="utf-8")
    compose = Path("docker/compose.yaml").read_text(encoding="utf-8")

    assert "USER 10001:10001" in dockerfile
    assert "--allow-public-bind" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "--constraint requirements-release.txt pip setuptools wheel" in dockerfile
    assert "pip install --no-cache-dir --no-compile --no-build-isolation ." in dockerfile
    assert "127.0.0.1:8765:8765" in compose
    assert "restart: unless-stopped" in compose
    assert "pids_limit: 128" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose


def test_web_image_uses_an_explicit_runtime_allowlist() -> None:
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")
    assert dockerignore.startswith("# Build the Web/PWA image")
    assert "*\n" in dockerignore
    assert "!src/**" in dockerignore
    assert "!apps/web/**" in dockerignore

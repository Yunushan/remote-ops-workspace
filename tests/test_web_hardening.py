import json
import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from remote_ops_workspace import cli, web_server
from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore
from remote_ops_workspace.web_server import (
    SECURITY_HEADERS,
    QuietHandler,
    ReusableTCPServer,
    WebProfileApi,
    validate_web_bind,
)


@contextmanager
def _live_server(
    directory: Path,
    *,
    api: WebProfileApi | None = None,
    handler_base: type[QuietHandler] = QuietHandler,
) -> Iterator[tuple[str, int]]:
    handler_type = type("TestWebHandler", (handler_base,), {"api": api})
    handler = partial(handler_type, directory=str(directory))
    with ReusableTCPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            yield str(host), int(port)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


def _http_request(
    address: tuple[str, int],
    path: str,
    *,
    method: str = "GET",
    body: bytes | str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection(*address, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        response_headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, response_headers, response.read()
    finally:
        connection.close()


def _raw_http_request(address: tuple[str, int], request: bytes) -> bytes:
    with socket.create_connection(address, timeout=5) as client:
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        response = b""
        while chunk := client.recv(4096):
            response += chunk
    return response


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
    assert validate_web_bind("web.example.invalid", allow_public_bind=True) == "web.example.invalid"


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


def test_browser_profile_api_rejects_short_tokens_and_malformed_payloads(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    with pytest.raises(ValueError, match="at least 24 characters"):
        WebProfileApi(store, "too-short")

    api = WebProfileApi(store, "x" * 24)
    cases = (
        ([], "payload must be a JSON object"),
        ({"profile": []}, "profile must be a JSON object"),
        ({"name": "bad-options", "protocol": "ssh", "options": []}, "options must be"),
        ({"name": "bad-replace", "protocol": "ssh", "replace": "yes"}, "replace must be"),
    )
    for payload, message in cases:
        with pytest.raises(ValueError, match=message):
            api.add_profile(payload)


def test_browser_profile_api_rejects_sensitive_key_aliases(tmp_path: Path) -> None:
    api = WebProfileApi(ProfileStore(tmp_path / "profiles.json"), "x" * 24)
    sensitive_keys = (
        "api_key",
        "Authorization",
        "cookie",
        "credential_ref",
        "identity-file",
        "key_path",
        "passphrase",
        "private_key",
    )
    for index, key in enumerate(sensitive_keys):
        with pytest.raises(ValueError, match="secret-bearing fields"):
            api.add_profile(
                {
                    "name": f"blocked-field-{index}",
                    "protocol": "ssh",
                    key: "must-not-persist",
                }
            )
        with pytest.raises(ValueError, match="secret-bearing options"):
            api.add_profile(
                {
                    "name": f"blocked-option-{index}",
                    "protocol": "ssh",
                    "options": {key: "must-not-persist"},
                }
            )

    created = api.add_profile(
        {
            "name": "smartcard",
            "protocol": "ssh",
            "host": "smartcard.example.invalid",
            "options": {"smartcard_auth": "true"},
        }
    )
    assert created["options"] == {"smartcard_auth": "true"}


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


def test_browser_profile_api_authenticates_every_api_endpoint(tmp_path: Path) -> None:
    token = "t" * 24
    api = WebProfileApi(ProfileStore(tmp_path / "profiles.json"), token)
    with _live_server(tmp_path, api=api) as address:
        for path in ("/api/v1/health", "/api/v1/profiles"):
            status, headers, body = _http_request(address, path)
            assert status == 401
            assert headers["www-authenticate"] == "Bearer"
            assert body == b""

        status, headers, body = _http_request(
            address,
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert status == 200
        assert headers["cache-control"] == "no-store"
        assert json.loads(body) == {"api_version": 1, "profile_count": 0, "status": "ok"}

        status, headers, body = _http_request(
            address,
            "/api/v1/profiles",
            method="POST",
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert status == 401
        assert headers["connection"] == "close"
        assert body == b""


def test_browser_profile_api_returns_disabled_and_unauthorized_http_contracts(tmp_path: Path) -> None:
    with _live_server(tmp_path) as address:
        status, _, body = _http_request(address, "/api/v1/health")
        assert status == 404
        assert "browser API is disabled" in json.loads(body)["error"]

        status, _, body = _http_request(
            address,
            "/api/v1/profiles",
            method="POST",
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert status == 404
        assert "browser API is disabled" in json.loads(body)["error"]

        status, _, _ = _http_request(address, "/api/v1/not-found", method="POST", body=b"{}")
        assert status == 404

        status, _, _ = _http_request(
            address,
            "/api/v1/not-found",
            method="POST",
            headers={"Content-Length": "invalid"},
        )
        assert status == 404

        status, _, _ = _http_request(address, "/api/v1/not-found", method="POST")
        assert status == 404


def test_rejected_post_closes_without_waiting_for_declared_body(tmp_path: Path) -> None:
    with _live_server(tmp_path) as address:
        with socket.create_connection(address, timeout=5) as client:
            client.settimeout(1)
            client.sendall(
                b"POST /api/v1/not-found HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Length: 65536\r\n"
                b"Connection: keep-alive\r\n\r\n"
            )
            response = b""
            while chunk := client.recv(4096):
                response += chunk

    assert response.startswith(b"HTTP/1.0 404")


def test_discard_request_body_tolerates_nonblocking_read_errors() -> None:
    events: list[object] = []

    class Connection:
        def gettimeout(self) -> float:
            return 15.0

        def setblocking(self, enabled: bool) -> None:
            events.append(enabled)

        def settimeout(self, timeout: float) -> None:
            events.append(timeout)

    class Body:
        def read1(self, size: int) -> bytes:
            assert size == web_server.MAX_REQUEST_BODY_BYTES
            raise BlockingIOError

    handler = object.__new__(QuietHandler)
    handler.connection = Connection()
    handler.rfile = Body()
    handler.close_connection = False

    handler._discard_request_body()

    assert handler.close_connection is True
    assert events == [False, 15.0]


def test_browser_profile_api_validates_http_writes_and_replace_flow(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    token = "t" * 24
    authorization = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    api = WebProfileApi(store, token)
    with _live_server(tmp_path, api=api) as address:
        malformed_requests = (
            (b"", {**authorization, "Content-Length": "0"}),
            (b"", {**authorization, "Content-Length": "invalid"}),
            (b"", {**authorization, "Content-Length": "65537"}),
            (b"{}", {"Authorization": f"Bearer {token}", "Content-Type": "text/plain"}),
            (b"{}", {"Authorization": f"Bearer {token}", "Content-Type": "application/jsonp"}),
            (b"{", authorization),
            (b"\xff", authorization),
        )
        for body, headers in malformed_requests:
            status, response_headers, response_body = _http_request(
                address,
                "/api/v1/profiles",
                method="POST",
                body=body,
                headers=headers,
            )
            assert status == 400
            assert response_headers["content-type"] == "application/json; charset=utf-8"
            assert json.loads(response_body)["error"]

        profile = {"name": "edge", "protocol": "ssh", "host": "edge.example.invalid"}
        authorization["Content-Type"] = "application/json; charset=utf-8"
        status, _, body = _http_request(
            address,
            "/api/v1/profiles",
            method="POST",
            body=json.dumps({"profile": profile}).encode("utf-8"),
            headers=authorization,
        )
        assert status == 201
        assert json.loads(body)["host"] == "edge.example.invalid"

        status, _, body = _http_request(
            address,
            "/api/v1/profiles",
            method="POST",
            body=json.dumps({"profile": profile}).encode("utf-8"),
            headers=authorization,
        )
        assert status == 400
        assert "already exists" in json.loads(body)["error"]

        profile["host"] = "edge-replaced.example.invalid"
        status, _, body = _http_request(
            address,
            "/api/v1/profiles",
            method="POST",
            body=json.dumps({"profile": profile, "replace": True}).encode("utf-8"),
            headers=authorization,
        )
        assert status == 201
        assert json.loads(body)["host"] == "edge-replaced.example.invalid"
        assert store.get("edge").host == "edge-replaced.example.invalid"


def test_browser_profile_api_rejects_incomplete_http_body(tmp_path: Path) -> None:
    token = "t" * 24
    api = WebProfileApi(ProfileStore(tmp_path / "profiles.json"), token)
    with _live_server(tmp_path, api=api) as address:
        response = _raw_http_request(
            address,
            b"POST /api/v1/profiles HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            + f"Authorization: Bearer {token}\r\n".encode("ascii")
            + b"Content-Type: application/json\r\n"
            b"Content-Length: 10\r\n"
            b"Connection: close\r\n\r\n{}",
        )

    headers, body = response.split(b"\r\n\r\n", 1)
    assert headers.startswith(b"HTTP/1.0 400")
    assert "does not match Content-Length" in json.loads(body)["error"]


def test_web_handler_refuses_directory_listing_and_paths_outside_root(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    with _live_server(tmp_path) as address:
        status, _, _ = _http_request(address, "/folder/")
        assert status == 404

    outside = tmp_path.parent / "outside-web-root.txt"
    outside.write_text("must not be served", encoding="utf-8")

    class EscapingHandler(QuietHandler):
        def translate_path(self, path: str) -> str:
            return str(outside)

    with _live_server(tmp_path, handler_base=EscapingHandler) as address:
        status, _, body = _http_request(address, "/outside-web-root.txt")
        assert status == 404
        assert b"must not be served" not in body


def test_serve_web_validates_configuration_and_runs_server(monkeypatch, tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="web directory does not exist"):
        web_server.serve_web(directory=missing)

    web_root = tmp_path / "web"
    web_root.mkdir()
    with pytest.raises(ValueError, match="loopback bind host"):
        web_server.serve_web(
            host="0.0.0.0",
            directory=web_root,
            allow_public_bind=True,
            api_token="t" * 24,
        )

    calls: list[tuple[tuple[str, int], object]] = []

    class FakeServer:
        def __init__(self, address, handler) -> None:
            calls.append((address, handler))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def serve_forever(self) -> None:
            return None

    monkeypatch.setattr(web_server, "ReusableTCPServer", FakeServer)
    store = ProfileStore(tmp_path / "profiles.json")
    web_server.serve_web(directory=web_root, api_token="t" * 24, profile_store=store)
    web_server.serve_web(host="0.0.0.0", directory=web_root, allow_public_bind=True)

    assert [address for address, _ in calls] == [("127.0.0.1", 8765), ("0.0.0.0", 8765)]
    output = capsys.readouterr().out
    assert "Browser profile API enabled" in output
    assert "bound to a non-loopback interface" in output


def test_serve_web_cli_reads_api_token_from_environment(monkeypatch) -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        ["serve-web", "--host", "127.0.0.1", "--port", "9876", "--api-token-env", "ROW_TOKEN"]
    )
    captured: dict[str, object] = {}
    monkeypatch.setenv("ROW_TOKEN", "t" * 24)
    monkeypatch.setattr(cli, "serve_web", lambda **kwargs: captured.update(kwargs))

    assert cli.cmd_serve_web(args) == 0
    assert captured == {
        "host": "127.0.0.1",
        "port": 9876,
        "allow_public_bind": False,
        "api_token": "t" * 24,
    }

    direct_args = parser.parse_args(["serve-web", "--api-token", "d" * 24])
    captured.clear()
    assert cli.cmd_serve_web(direct_args) == 0
    assert captured["api_token"] == "d" * 24

    monkeypatch.delenv("ROW_TOKEN")
    with pytest.raises(ValueError, match="environment variable is not set"):
        cli.cmd_serve_web(args)

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["serve-web", "--api-token", "x" * 24, "--api-token-env", "ROW_TOKEN"]
        )


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

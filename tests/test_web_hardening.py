import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from remote_ops_workspace import cli, web_server
from remote_ops_workspace.models import Profile
from remote_ops_workspace.process_status import terminate_owned_process
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


def test_web_request_logs_escape_accepted_terminal_control_sequences(capsys) -> None:
    handler = object.__new__(QuietHandler)
    handler.raw_requestline = b"GET /\x1b[2J\x08\x7f\x9b HTTP/1.1\r\n"
    handler.rfile = io.BytesIO(b"Host: localhost\r\n\r\n")

    assert handler.parse_request() is True
    handler.log_request(404)

    logged = capsys.readouterr().out
    assert 'web: "GET /\\x1b[2J\\x08\\x7f\\x9b HTTP/1.1" 404 -\n' == logged
    assert all(character not in logged for character in ("\x1b", "\x08", "\x7f", "\x9b"))


def test_web_log_messages_escape_line_breaks_and_backslashes(capsys) -> None:
    handler = object.__new__(QuietHandler)
    handler.log_message("value %s", "safe\\path\r\nforged\tentry")

    assert capsys.readouterr().out == "web: value safe\\\\path\\x0d\\x0aforged\\x09entry\n"


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
            assert payload["has_restricted_locks"] is False
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


def test_browser_profile_api_rejects_executable_local_and_opaque_metadata(tmp_path: Path) -> None:
    api = WebProfileApi(ProfileStore(tmp_path / "profiles.json"), "x" * 24)
    for protocol in ("local", "local-shell", "shell", "custom", "serial"):
        with pytest.raises(ValueError, match="local or executable"):
            api.add_profile({"name": f"unsafe-{protocol}", "protocol": protocol})

    unsafe_fields = {
        "command": "tool --password secret",
        "path": "C:/Users/operator/private.rdp",
        "unknown": "opaque",
    }
    for index, (key, value) in enumerate(unsafe_fields.items()):
        with pytest.raises(ValueError, match="local, executable or unsupported"):
            api.add_profile(
                {
                    "name": f"unsafe-field-{index}",
                    "protocol": "ssh",
                    "host": "edge.example.invalid",
                    key: value,
                }
            )

    for option, value in (
        ("proxy_command", "opaque value"),
        ("remote_command", "opaque value"),
        ("unknown_metadata", "opaque value"),
        ("agent_forward", "true"),
        ("x11", "trusted"),
        ("strict_host_key_checking", "no"),
    ):
        with pytest.raises(ValueError, match="executable, local or unrecognized options"):
            api.add_profile(
                {
                    "name": f"unsafe-option-{option}",
                    "protocol": "ssh",
                    "host": "edge.example.invalid",
                    "options": {option: value},
                }
            )

    with pytest.raises(ValueError, match="URL origins"):
        api.add_profile(
            {
                "name": "unsafe-url",
                "protocol": "https",
                "url": "https://operator:secret@example.invalid/path?token=secret",
            }
        )

    for unsafe_url in (
        "file://fileserver/private/share",
        "javascript://example.invalid/alert(1)",
        "data://example.invalid/text/plain,payload",
        "https://example.invalid/reset/capability-token",
    ):
        with pytest.raises(ValueError, match="URL origins"):
            api.add_profile(
                {
                    "name": "unsafe-url-scheme",
                    "protocol": "ica",
                    "url": unsafe_url,
                }
            )

    with pytest.raises(ValueError, match="secret-bearing public fields: description"):
        api.add_profile(
            {
                "name": "secret-metadata",
                "protocol": "ssh",
                "host": "edge.example.invalid",
                "description": "password=must-not-cross-boundary",
            }
        )

    with pytest.raises(ValueError, match="refuses port forwards"):
        api.add_profile(
            {
                "name": "forward",
                "protocol": "ssh",
                "host": "edge.example.invalid",
                "tunnels": [
                    {
                        "mode": "remote",
                        "local_host": "127.0.0.1",
                        "local_port": 22,
                        "remote_host": "0.0.0.0",
                        "remote_port": 2222,
                    }
                ],
            }
        )

    with pytest.raises(ValueError, match="envelope contains unsupported fields"):
        api.add_profile(
            {
                "profile": {
                    "name": "wrapped",
                    "protocol": "ssh",
                    "host": "edge.example.invalid",
                },
                "replace": False,
                "credential_ref": "vault:must-not-ignore",
            }
        )


def test_browser_profile_api_public_view_strips_legacy_local_and_executable_fields(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(
        Profile(
            name="legacy",
            protocol="ssh",
            host="edge.example.invalid",
            path="C:/Users/operator/private.rdp",
            command="tool --password secret",
            url="https://operator:secret@example.invalid/path?token=secret#private",
            options={"compression": "yes", "unknown_metadata": "secret"},
        )
    )

    public = WebProfileApi(store, "x" * 24).profiles()[0]
    assert "path" not in public
    assert "command" not in public
    assert public["url"] == "https://example.invalid"
    assert public["options"] == {"compression": "yes"}


def test_browser_profile_api_atomically_rejects_inherited_local_capabilities(
    tmp_path: Path,
) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(
        Profile(
            name="edge",
            protocol="ssh",
            host="edge.example.invalid",
            group="prod",
            credential_ref="vault:edge",
            identity_file="/private/id_ed25519",
        )
    )
    store.set_group_defaults(
        "prod",
        {
            "credential_ref": "vault:prod",
            "options": {
                "agent_forward": "true",
                "proxy_jump": "bastion.example.invalid",
            },
        },
    )
    api = WebProfileApi(store, "x" * 24)
    original = store.path.read_bytes()

    with pytest.raises(ValueError, match="credentials or forwarding settings"):
        api.add_profile(
            {
                "name": "new-edge",
                "protocol": "ssh",
                "host": "new.example.invalid",
                "group": "prod",
            }
        )
    with pytest.raises(ValueError, match="credentials or forwarding settings"):
        api.add_profile(
            {
                "profile": {
                    "name": "edge",
                    "protocol": "ssh",
                    "host": "attacker.example.invalid",
                    "group": "prod",
                },
                "replace": True,
            }
        )

    assert store.path.read_bytes() == original
    assert store.get("edge").host == "edge.example.invalid"
    with pytest.raises(KeyError):
        store.get("new-edge")


def test_browser_profile_api_preserves_local_auth_for_same_binding_replace(
    tmp_path: Path,
) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(
        Profile(
            name="edge",
            protocol="ssh",
            host="edge.example.invalid",
            group="prod",
            credential_ref="vault:edge",
            identity_file="/private/id_ed25519",
        )
    )
    store.set_group_defaults(
        "prod",
        {
            "credential_ref": "vault:prod",
            "options": {"agent_forward": "true"},
        },
    )
    api = WebProfileApi(store, "x" * 24)

    api.add_profile(
        {
            "profile": {
                "name": "edge",
                "protocol": "ssh",
                "host": "edge.example.invalid",
                "group": "prod",
                "description": "updated label",
            },
            "replace": True,
        }
    )

    saved = store.get("edge")
    assert saved.credential_ref == "vault:edge"
    assert saved.identity_file == "/private/id_ed25519"
    assert saved.description == "updated label"


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


def _completed_web_policy_result(path: Path, scenario: str, nonce: str) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if (
        not isinstance(record, dict)
        or set(record) != {"complete", "scenario", "nonce", "saved", "blocked"}
        or record["complete"] is not True
        or record["scenario"] != scenario
        or record["nonce"] != nonce
        or type(record["saved"]) is not int
        or record["saved"] not in (0, 1)
        or not isinstance(record["blocked"], str)
    ):
        raise ValueError("Node completion record does not match this exact test invocation")
    return record


def _web_policy_milestones(path: Path) -> list[dict]:
    """Read bounded, monotonic diagnostics without treating them as completion."""
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("Node milestone diagnostics exceed their byte limit")
    records = json.loads(raw)
    stages = (
        "harness-start",
        "require-enter",
        "require-return",
        "submit-enter",
        "submit-return",
        "result-write-enter",
        "result-published",
        "exit-requested",
        "exit-event",
    )
    if not isinstance(records, list) or len(records) > len(stages):
        raise ValueError("Node milestone diagnostics exceed their stage limit")
    previous_ms = -1
    previous_stage = -1
    for record in records:
        if (
            not isinstance(record, dict)
            or set(record) != {"stage", "elapsed_ms"}
            or record["stage"] not in stages
            or type(record["elapsed_ms"]) is not int
            or not 0 <= record["elapsed_ms"] <= 86_400_000
            or record["elapsed_ms"] < previous_ms
            or stages.index(record["stage"]) <= previous_stage
        ):
            raise ValueError("Node milestone diagnostics are not bounded monotonic stages")
        previous_ms = record["elapsed_ms"]
        previous_stage = stages.index(record["stage"])
    return records


def _run_web_policy_harness(
    command: list[str],
    result_path: Path,
    scenario: str,
    nonce: str,
    *,
    timeout: float = 10,
    cleanup_timeout: float = 5,
) -> dict:
    """Retain result-vs-exit evidence; preserve timeout/nonzero as failures."""
    report = {
        "result_exists": False,
        "complete_result": False,
        "child_reaped": False,
        "cleanup_requested": False,
        "pre_cleanup_returncode": None,
    }
    process = None
    result = None
    failure = None
    started = time.monotonic()
    try:
        with (
            result_path.with_suffix(".stdout.log").open("wb") as stdout,
            result_path.with_suffix(".stderr.log").open("wb") as stderr,
        ):
            options = {}
            if os.name == "nt":
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = subprocess.SW_HIDE
                options = {"startupinfo": startup, "creationflags": subprocess.CREATE_NO_WINDOW}
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, **options
            )
            deadline = time.monotonic() + timeout
            while True:
                report["result_exists"] = result_path.exists()
                returncode = process.poll()
                if returncode is not None:
                    report["observed_returncode"] = returncode
                    if returncode != 0:
                        raise RuntimeError(
                            "Node harness exited nonzero; completion cannot override failure"
                        )
                unreadable = False
                try:
                    result = _completed_web_policy_result(result_path, scenario, nonce)
                except PermissionError:
                    # Windows rename/file-inspection sharing can transiently
                    # prevent opening a complete publication. Retry within the
                    # same deadline; an unreadable result never passes.
                    report["result_error_type"] = "PermissionError"
                    result = None
                    unreadable = True
                except (ValueError, UnicodeError) as exc:
                    report["result_error_type"] = type(exc).__name__
                    raise
                report["complete_result"] = result is not None
                observed_at = time.monotonic()
                report["last_observation_elapsed_seconds"] = observed_at - started
                if observed_at >= deadline:
                    report["timed_out"] = True
                    raise TimeoutError(
                        f"Node harness timed out; complete_result={result is not None}"
                    )
                if returncode is not None and not unreadable:
                    if result is None:
                        raise RuntimeError("Node harness exited without its completion record")
                    break
                time.sleep(0.01)
        return result
    except Exception as exc:
        failure = exc
        report["failure_type"] = type(exc).__name__
        raise
    finally:
        try:
            if process is not None:
                report["pre_cleanup_returncode"] = process.poll()
                if report["pre_cleanup_returncode"] is None:
                    report["cleanup_requested"] = True
                    terminate_owned_process(process, timeout_seconds=cleanup_timeout)
                process.wait(timeout=0)
                report.update(child_reaped=True, final_returncode=process.returncode)
        except Exception as exc:
            report["cleanup_failure_type"] = type(exc).__name__
            raise
        finally:
            report["elapsed_seconds"] = time.monotonic() - started
            progress = result_path.with_suffix(".progress.json")
            try:
                milestones = _web_policy_milestones(progress)
                report["milestones"] = [item["stage"] for item in milestones]
                report["milestone_timings"] = milestones
            except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
                report["milestones"] = []
                report["milestone_timings"] = []
                report["milestone_error_type"] = type(exc).__name__
            result_path.with_suffix(".runner.json").write_text(json.dumps(report, indent=2) + "\n")
            if isinstance(failure, TimeoutError):
                failure.args = (
                    f"{failure.args[0]}; result_exists={report['result_exists']}; "
                    f"milestones={','.join(report['milestones']) or 'none'}; "
                    f"milestone_timings={report['milestone_timings']}; "
                    f"pre_cleanup_returncode={report['pre_cleanup_returncode']}; "
                    f"cleanup_requested={report['cleanup_requested']}; "
                    f"child_reaped={report['child_reaped']}",
                )


@pytest.mark.parametrize(
    "mode", ("success", "nonzero", "complete-hang", "no-result-hang", "wrong-nonce")
)
def test_complete_result_never_excuses_failure_and_child_is_reaped(tmp_path, mode):
    result_path = tmp_path / "result.json"
    code = r"""
import json, os, sys, time
from pathlib import Path
path, mode = Path(sys.argv[1]), sys.argv[2]
if mode != "no-result-hang":
    record={"complete":True,"scenario":"pending","nonce":"wrong" if mode=="wrong-nonce" else "this-run", "saved":0,"blocked":"enterprise policy is unavailable"}
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record))
    os.replace(temporary,path)
if mode in ("complete-hang","no-result-hang"):
    time.sleep(60)
raise SystemExit(1 if mode=="nonzero" else 0)
"""
    command = [sys.executable, "-c", code, str(result_path), mode]
    # These fixture-only deadlines allow child startup before checking its
    # semantic result. The actual Node test retains its 10/30 second limits.
    fixture_timeout = 0.2 if mode == "no-result-hang" else 3
    if mode == "success":
        result = _run_web_policy_harness(
            command, result_path, "pending", "this-run", timeout=fixture_timeout
        )
        assert result["saved"] == 0
    else:
        error = (
            TimeoutError
            if mode.endswith("hang")
            else ValueError
            if mode == "wrong-nonce"
            else RuntimeError
        )
        with pytest.raises(error):
            _run_web_policy_harness(
                command, result_path, "pending", "this-run", timeout=fixture_timeout
            )
    report = json.loads(result_path.with_suffix(".runner.json").read_text())
    assert report["child_reaped"] is True
    if mode.endswith("hang"):
        assert report["cleanup_requested"] is True
        assert report["pre_cleanup_returncode"] is None
    elif mode in ("success", "nonzero"):
        assert report["cleanup_requested"] is False
        assert report["pre_cleanup_returncode"] == (1 if mode == "nonzero" else 0)
    if mode == "complete-hang":
        assert report["result_exists"] and report["complete_result"] and report["timed_out"]
    elif mode == "no-result-hang":
        assert report["result_exists"] is False and report["complete_result"] is False


def test_existing_exists_only_protocol_can_read_partial_json_but_atomic_protocol_cannot(tmp_path):
    result = tmp_path / "legacy.json"
    code = r"""
import sys,time
from pathlib import Path
path=Path(sys.argv[1]); path.write_text('{"saved":')
time.sleep(60)
"""
    process = subprocess.Popen([sys.executable, "-c", code, str(result)])
    try:
        import time

        deadline = time.monotonic() + 3
        while not result.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert result.exists()
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.read_text())
    finally:
        terminate_owned_process(process, timeout_seconds=1)
        process.wait(timeout=0)
    published = tmp_path / "atomic.json"
    temporary = published.with_suffix(".tmp")
    temporary.write_text('{"complete":')
    assert not published.exists()
    assert _completed_web_policy_result(published, "pending", "this-run") is None
    temporary.write_text(
        json.dumps(
            {
                "complete": True,
                "scenario": "pending",
                "nonce": "this-run",
                "saved": 0,
                "blocked": "enterprise policy is unavailable",
            }
        )
    )
    temporary.replace(published)
    assert _completed_web_policy_result(published, "pending", "this-run")["saved"] == 0


def test_zero_exit_and_complete_record_observed_after_deadline_still_fail(tmp_path, monkeypatch):
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "complete": True,
                "scenario": "pending",
                "nonce": "this-run",
                "saved": 0,
                "blocked": "unavailable",
            }
        )
    )

    class ExitedChild:
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout):
            assert timeout == 0
            return 0

    clock = iter((0, 0, 2, 3))
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: ExitedChild())
    monkeypatch.setitem(
        _run_web_policy_harness.__globals__,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None),
    )
    with pytest.raises(TimeoutError, match="complete_result=True"):
        _run_web_policy_harness(
            ["harmless-placeholder"], result_path, "pending", "this-run", timeout=1
        )
    report = json.loads(result_path.with_suffix(".runner.json").read_text())
    assert report["timed_out"] and report["complete_result"] and report["child_reaped"]
    assert report["observed_returncode"] == 0
    assert report["cleanup_requested"] is False
    assert report["pre_cleanup_returncode"] == 0


def test_unreadable_progress_preserves_timeout_and_owned_cleanup(tmp_path, monkeypatch):
    result_path = tmp_path / "result.json"
    progress_path = result_path.with_suffix(".progress.json")
    progress_path.write_text("[]")
    real_open = Path.open

    def unreadable_progress(path, *args, **kwargs):
        if path == progress_path:
            raise PermissionError("harmless simulated sharing conflict")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable_progress)
    with pytest.raises(TimeoutError, match="child_reaped=True"):
        _run_web_policy_harness(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            result_path,
            "pending",
            "this-run",
            timeout=0.1,
        )
    report = json.loads(result_path.with_suffix(".runner.json").read_text())
    assert report["failure_type"] == "TimeoutError"
    assert report["milestone_error_type"] == "PermissionError"
    assert report["milestones"] == []
    assert report["child_reaped"] is True
    assert report["cleanup_requested"] is True
    assert report["pre_cleanup_returncode"] is None


@pytest.mark.parametrize(
    "records",
    (
        [{"stage": "harness-start", "elapsed_ms": True}],
        [{"stage": "harness-start", "elapsed_ms": -1}],
        [{"stage": "harness-start", "elapsed_ms": 86_400_001}],
        [{"stage": "harness-start", "elapsed_ms": 0, "unexpected": "private"}],
        [{"stage": "unknown", "elapsed_ms": 0}],
        [
            {"stage": "harness-start", "elapsed_ms": 2},
            {"stage": "require-enter", "elapsed_ms": 1},
        ],
        [
            {"stage": "require-enter", "elapsed_ms": 1},
            {"stage": "harness-start", "elapsed_ms": 2},
        ],
        [{"stage": "harness-start", "elapsed_ms": 0}] * 10,
    ),
)
def test_web_policy_milestone_diagnostics_refuse_invalid_bounds(tmp_path, records):
    progress_path = tmp_path / "progress.json"
    progress_path.write_text(json.dumps(records), encoding="utf-8")
    with pytest.raises(ValueError):
        _web_policy_milestones(progress_path)


def test_web_policy_milestone_diagnostics_refuse_oversized_input(tmp_path):
    progress_path = tmp_path / "progress.json"
    progress_path.write_bytes(b" " * 4097)
    with pytest.raises(ValueError, match="byte limit"):
        _web_policy_milestones(progress_path)


def test_valid_zero_exit_completion_still_fails_when_reaping_is_unconfirmed(tmp_path, monkeypatch):
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "complete": True,
                "scenario": "pending",
                "nonce": "this-run",
                "saved": 0,
                "blocked": "unavailable",
            }
        )
    )

    class UnreapedChild:
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout):
            assert timeout == 0
            raise subprocess.TimeoutExpired("harmless-placeholder", timeout)

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: UnreapedChild())
    with pytest.raises(subprocess.TimeoutExpired):
        _run_web_policy_harness(
            ["harmless-placeholder"], result_path, "pending", "this-run", timeout=1
        )
    report = json.loads(result_path.with_suffix(".runner.json").read_text())
    assert report["observed_returncode"] == 0 and report["complete_result"] is True
    assert report["cleanup_failure_type"] == "TimeoutExpired"
    assert report["child_reaped"] is False


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
@pytest.mark.parametrize(
    ("scenario", "expected_saved", "expected_blocked"),
    [
        ("pending", 0, "enterprise policy is unavailable"),
        ("reject", 0, "enterprise policy is unavailable"),
        ("malformed", 0, "enterprise policy is unavailable"),
        ("restricted", 0, "trusted enterprise policy surface"),
        ("allow", 1, ""),
    ],
)
def test_web_client_profile_submit_obeys_loaded_policy_behavior(
    scenario: str,
    expected_saved: int,
    expected_blocked: str,
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    assert node is not None
    harness = r"""
const fs = require('node:fs');
const path = require('node:path');
// Keep source, completion and progress separate so the parent can diagnose
// where execution stopped without accepting an unobserved completion.
const scenario = process.argv[2];
const outputPath = process.argv[3];
const nonce = process.argv[4];
const progressPath = process.argv[5];
const marks = [];
const started = process.hrtime.bigint();
function milestone(stage) {
  marks.push({stage, elapsed_ms: Number((process.hrtime.bigint() - started) / 1000000n)});
  const temp = progressPath + '.tmp';
  fs.writeFileSync(temp, JSON.stringify(marks));
  fs.renameSync(temp, progressPath);
}
milestone('harness-start');
process.once('exit', () => milestone('exit-event'));
const windowsPendingFallback = process.platform === 'win32' && scenario === 'pending';
const records = new Map();
const listeners = {};
const harnessForm = {
  dataset: {},
  addEventListener: (name, callback) => { listeners[name] = callback; },
  reset: () => {},
};
const inertElement = () => ({
  appendChild: () => {},
  replaceChildren: () => {},
  style: {},
  dataset: {},
  textContent: '',
  innerHTML: '',
  className: '',
});
const elements = {
  '#profiles': inertElement(),
  '#profile-form': harnessForm,
  '#terminal-grid': inertElement(),
  '#feature-tags': inertElement(),
};
const harnessSetTimeout = scenario === 'pending'
  ? callback => {
      // Resolve the timeout branch immediately so the test exercises the
      // production fallback without leaving a timer alive.
      callback();
      return {};
    }
  : setTimeout;
const harnessClearTimeout = scenario === 'pending' ? () => {} : clearTimeout;
const harnessDocument = {
  querySelector: selector => elements[selector],
  querySelectorAll: () => [],
  createElement: inertElement,
  documentElement: {dataset: {}},
};
const sessionStorage = {
  getItem: key => records.get(key) ?? null,
  setItem: (key, value) => records.set(key, String(value)),
  removeItem: key => records.delete(key),
};
const FormData = function () {
  return {entries: () => [
    ['name', 'edge'],
    ['protocol', 'ssh'],
    ['target', 'edge.example.invalid'],
  ][Symbol.iterator]()};
};
if (!('navigator' in globalThis)) {
  Object.defineProperty(globalThis, 'navigator', {value: {}, configurable: true});
}
// Load the actual application as CommonJS, avoiding an unnecessary VM context.
Object.assign(globalThis, {
  document: harnessDocument,
  sessionStorage,
  FormData,
  setTimeout: harnessSetTimeout,
  clearTimeout: harnessClearTimeout,
});
const validPolicy = {
  active: true,
  allow_user_profiles: true,
  has_restricted_locks: scenario === 'restricted',
  locked_settings: [],
};
let fetchResult;
if (scenario === 'pending') {
  if (windowsPendingFallback) {
    // Keep this case synchronous so it exercises the unavailable-policy
    // fallback without leaving an unresolved promise behind.
    globalThis.fetch = () => {
      throw new Error('enterprise policy is unavailable');
    };
  } else {
    fetchResult = new Promise(() => {});
    globalThis.fetch = () => fetchResult;
  }
} else if (scenario === 'reject') {
  fetchResult = Promise.reject(new Error('offline'));
  globalThis.fetch = () => fetchResult;
} else {
  const body = scenario === 'malformed' ? {active: false} : validPolicy;
  fetchResult = Promise.resolve({ok: true, json: async () => body});
  globalThis.fetch = () => fetchResult;
}
milestone('require-enter');
require(path.resolve(process.argv[1]));
milestone('require-return');
const finish = () => {
  milestone('submit-enter');
  listeners.submit({preventDefault: () => {}});
  milestone('submit-return');
  const saved = JSON.parse(
    records.get('remote-ops-workspace-demo-profiles') || '[]',
  );
  const output = JSON.stringify({
    complete: true, scenario, nonce,
    saved: saved.length,
    blocked: harnessForm.dataset.enterprisePolicyBlocked || '',
  });
  milestone('result-write-enter');
  fs.writeFileSync(outputPath + '.tmp', output);
  fs.renameSync(outputPath + '.tmp', outputPath);
  milestone('result-published');
  milestone('exit-requested');
  // Let handled policy promises settle and the event loop finish naturally.
  // The parent still requires an observed zero exit within its original limit.
  process.exitCode = 0;
};
// The pending case intentionally submits before policy loading completes, so
// finish it synchronously. All other scenarios allow policy-loading promises
// to settle before submitting.
if (scenario === 'pending') {
  finish();
} else {
  setImmediate(finish);
}
    """
    output_path = tmp_path / f"web-policy-{scenario}.json"
    nonce = secrets.token_hex(16)
    command = [
        node,
        "-e",
        harness,
        str(Path("apps/web/app.js")),
        scenario,
        str(output_path),
        nonce,
        str(output_path.with_suffix(".progress.json")),
    ]
    result = _run_web_policy_harness(
        command, output_path, scenario, nonce, timeout=30 if os.name == "nt" else 10
    )
    assert result["saved"] == expected_saved
    assert expected_blocked in result["blocked"]
    report = json.loads(output_path.with_suffix(".runner.json").read_text())
    assert report["cleanup_requested"] is False
    assert report["pre_cleanup_returncode"] == report["final_returncode"] == 0
    assert report["milestones"][-2:] == ["exit-requested", "exit-event"]


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

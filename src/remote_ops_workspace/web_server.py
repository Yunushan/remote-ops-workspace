from __future__ import annotations

import http.server
import ipaddress
import json
import secrets
import socketserver
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

from . import command_safety as safe
from .enterprise_policy import load_enterprise_policy
from .models import Profile
from .paths import runtime_web_dir
from .storage import ProfileStore

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

SENSITIVE_OPTION_TOKENS = ("password", "passphrase", "secret", "token", "credential", "private_key")


class WebProfileApi:
    """Small same-origin API for the Web/PWA profile catalogue.

    It intentionally exposes no credentials, key paths, terminal execution, or
    arbitrary file access.  The caller must supply a per-launch bearer token.
    """

    def __init__(self, store: ProfileStore, token: str) -> None:
        token = str(token).strip()
        if len(token) < 24:
            raise ValueError("web API token must contain at least 24 characters")
        self.store = store
        self.token = token

    def authorized(self, authorization: str | None) -> bool:
        expected = f"Bearer {self.token}"
        return bool(authorization) and secrets.compare_digest(authorization, expected)

    def health(self) -> dict[str, object]:
        return {"api_version": 1, "status": "ok", "profile_count": len(self.store.load())}

    def profiles(self) -> list[dict[str, object]]:
        return [self._public_profile(profile) for profile in self.store.load()]

    def add_profile(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("profile payload must be a JSON object")
        forbidden = {"credential_ref", "identity_file", "password", "secret", "token"}
        profile_data = payload.get("profile", payload)
        if not isinstance(profile_data, dict):
            raise ValueError("profile must be a JSON object")
        supplied = {str(key).lower() for key in profile_data}
        blocked = sorted(forbidden & supplied)
        if blocked:
            raise ValueError(f"web API refuses secret-bearing fields: {', '.join(blocked)}")
        raw_options = profile_data.get("options", {})
        if not isinstance(raw_options, dict):
            raise ValueError("profile options must be a JSON object")
        sensitive_options = sorted(
            str(key)
            for key in raw_options
            if _is_sensitive_option_key(str(key))
        )
        if sensitive_options:
            raise ValueError(
                "web API refuses secret-bearing options: " + ", ".join(sensitive_options)
            )
        profile = Profile.from_dict(profile_data)
        replace = payload.get("replace", False)
        if not isinstance(replace, bool):
            raise ValueError("replace must be boolean")
        self.store.add(profile, replace=replace, surface="web")
        return self._public_profile(self.store.get(profile.name))

    @staticmethod
    def _public_profile(profile: Profile) -> dict[str, object]:
        return {
            "name": profile.name,
            "protocol": profile.protocol,
            "host": profile.host,
            "port": profile.port,
            "username": profile.username,
            "group": profile.group,
            "tags": profile.tags,
            "description": profile.description,
            "path": profile.path,
            "url": profile.url,
            "command": profile.command,
            "tunnels": [tunnel.to_dict() for tunnel in profile.tunnels],
            "options": {
                key: value
                for key, value in profile.options.items()
                if not _is_sensitive_option_key(key)
            },
        }


def _is_sensitive_option_key(key: str) -> bool:
    return any(token in key.lower() for token in SENSITIVE_OPTION_TOKENS)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    api: WebProfileApi | None = None
    timeout = 15

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = urlparse(self.path).path
        if path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return
        if path == "/enterprise-policy.json":
            self._send_enterprise_policy()
            return
        if path == "/api/v1/health":
            self._send_api_health()
            return
        if path == "/api/v1/profiles":
            self._send_api_profiles()
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if urlparse(self.path).path != "/api/v1/profiles":
            self.send_error(404, "Not found")
            return
        if not self._api_authorized():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 64 * 1024:
                raise ValueError("request body must be between 1 and 65536 bytes")
            content_type = self.headers.get("Content-Type", "")
            if not content_type.lower().startswith("application/json"):
                raise ValueError("Content-Type must be application/json")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            api = self._require_api()
            self._send_json(201, api.add_profile(payload))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        print(f"web: {format % args}")

    def end_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def list_directory(self, path: str):  # type: ignore[override]
        self.send_error(404, "Directory listing is disabled")
        return None

    def _send_enterprise_policy(self) -> None:
        self._send_json(200, load_enterprise_policy().to_public_dict())

    def _require_api(self) -> WebProfileApi:
        if self.api is None:
            raise ValueError("browser API is disabled; restart with --api-token")
        return self.api

    def _api_authorized(self) -> bool:
        try:
            api = self._require_api()
        except ValueError as exc:
            self._send_json(404, {"error": str(exc)})
            return False
        if not api.authorized(self.headers.get("Authorization")):
            self.send_response(401)
            self.send_header("WWW-Authenticate", "Bearer")
            self._send_json_headers(0)
            return False
        return True

    def _send_api_health(self) -> None:
        try:
            self._send_json(200, self._require_api().health())
        except ValueError as exc:
            self._send_json(404, {"error": str(exc)})

    def _send_api_profiles(self) -> None:
        if not self._api_authorized():
            return
        self._send_json(200, {"profiles": self._require_api().profiles()})

    def _send_json(self, status: int, value: object) -> None:
        payload = json.dumps(value, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self._send_json_headers(len(payload))
        self.wfile.write(payload)

    def _send_json_headers(self, length: int) -> None:
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Bounded-lifetime request handling for the local static application."""

    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128


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
    api_token: str | None = None,
    profile_store: ProfileStore | None = None,
) -> None:
    host = validate_web_bind(host, allow_public_bind=allow_public_bind)
    port = safe.port(port, "web port")
    web_dir = directory or runtime_web_dir()
    web_dir = web_dir.resolve()
    if not web_dir.exists() or not web_dir.is_dir():
        raise ValueError(f"web directory does not exist: {web_dir}")
    if api_token and not _is_loopback_host(host.lower()):
        raise ValueError("browser API requires a loopback bind host")
    handler_type = type(
        "ConfiguredQuietHandler",
        (QuietHandler,),
        {"api": WebProfileApi(profile_store or ProfileStore(), api_token) if api_token else None},
    )
    handler = partial(handler_type, directory=str(web_dir))
    with ReusableTCPServer((host, port), handler) as httpd:
        print(f"Remote Ops Web/PWA serving at http://{host}:{port}")
        if api_token:
            print("Browser profile API enabled at /api/v1/profiles (Bearer token required)")
        if not _is_loopback_host(host.lower()):
            print("warning: Web/PWA is bound to a non-loopback interface; keep it on a trusted network.")
        httpd.serve_forever()

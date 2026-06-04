from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


REDACTED = "***REDACTED***"

SENSITIVE_KEY_TOKENS = (
    "auth",
    "cookie",
    "credential",
    "pass",
    "private",
    "secret",
    "token",
)

SENSITIVE_ARG_NAMES = {
    "-N",
    "--new-passphrase",
    "--old-passphrase",
    "--passphrase",
    "--password",
    "--secret",
    "--token",
}

SENSITIVE_ASSIGNMENT_KEYS = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "key",
    "pass",
    "passwd",
    "passphrase",
    "password",
    "private_key",
    "secret",
    "token",
}

ASSIGNMENT_RE = re.compile(r"(?P<key>[A-Za-z0-9_.-]*(?:auth|cookie|credential|pass|private|secret|token|key)[A-Za-z0-9_.-]*)(?P<sep>[:=])(?P<value>[^\s,;]+)", re.IGNORECASE)
BEARER_RE = re.compile(r"\b(Bearer)\s+([A-Za-z0-9._~+/=-]+)", re.IGNORECASE)
WINDOWS_SECRET_SWITCH_RE = re.compile(r"^/(?P<key>p|pass|password|passwd|token|secret):(?P<value>.+)$", re.IGNORECASE)
URL_PASSWORD_RE = re.compile(r"(?P<prefix>[A-Za-z][A-Za-z0-9+.-]*://[^\s/@:]+):(?P<password>[^@\s]+)@")


def is_sensitive_key(key: object) -> bool:
    text = str(key).lower()
    return any(token in text for token in SENSITIVE_KEY_TOKENS)


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            redacted[key] = REDACTED if is_sensitive_key(key) else redact_value(item)
        return redacted
    if isinstance(value, list):
        return _redact_sequence(value)
    if isinstance(value, tuple):
        return tuple(_redact_sequence(list(value)))
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    text = _redact_url_password(value)
    text = URL_PASSWORD_RE.sub(r"\g<prefix>:" + REDACTED + "@", text)
    text = BEARER_RE.sub(r"\1 " + REDACTED, text)
    text = ASSIGNMENT_RE.sub(_redact_assignment_match, text)
    return text


def _redact_sequence(value: list[Any]) -> list[Any]:
    redacted: list[Any] = []
    redact_next = False
    for item in value:
        if redact_next:
            redacted.append(REDACTED)
            redact_next = False
            continue
        if isinstance(item, str):
            if item in SENSITIVE_ARG_NAMES:
                redacted.append(item)
                redact_next = True
                continue
            redacted.append(_redact_string_arg(item))
            continue
        redacted.append(redact_value(item))
    return redacted


def _redact_string_arg(value: str) -> str:
    windows_match = WINDOWS_SECRET_SWITCH_RE.fullmatch(value)
    if windows_match:
        return f"/{windows_match.group('key')}:{REDACTED}"
    if "=" in value:
        key, separator, remainder = value.partition("=")
        if _assignment_key_is_sensitive(key):
            return f"{key}{separator}{REDACTED}"
    return redact_text(value)


def _redact_assignment_match(match: re.Match[str]) -> str:
    return f"{match.group('key')}{match.group('sep')}{REDACTED}"


def _assignment_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lstrip("-/").replace("-", "_").lower()
    return normalized in SENSITIVE_ASSIGNMENT_KEYS or is_sensitive_key(normalized)


def _redact_url_password(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc or parsed.password is None:
        return value
    username = parsed.username or ""
    hostname = parsed.hostname or ""
    if not username or not hostname:
        return value
    try:
        parsed_port = parsed.port
    except ValueError:
        parsed_port = None
    port = f":{parsed_port}" if parsed_port is not None else ""
    netloc = f"{username}:{REDACTED}@{hostname}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

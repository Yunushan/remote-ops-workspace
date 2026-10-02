from __future__ import annotations

import re
import shlex
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import command_safety as safe

REDACTED = "***REDACTED***"
COMMAND_TEXT_KEYS = frozenset({"command", "command_line", "proxy_command", "remote_command"})
POSIX_SHELL_PROGRAMS = frozenset({"ash", "bash", "csh", "dash", "fish", "ksh", "sh", "tcsh", "zsh"})
POWERSHELL_PROGRAMS = frozenset({"powershell", "pwsh"})

SENSITIVE_KEY_TOKENS = (
    "auth",
    "cookie",
    "credential",
    "pass",
    "private",
    "secret",
    "token",
)

SHARE_SENSITIVE_KEY_TOKENS = (
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "identity_file",
    "key_path",
    "passphrase",
    "passwd",
    "password",
    "private_key",
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
TEXT_SECRET_ARG_RE = re.compile(
    r"(?<!\S)(?:(?:"
    + "|".join(re.escape(flag) for flag in sorted(SENSITIVE_ARG_NAMES))
    + r")\s+|(?i:/(?:p|pass|password|passwd|token|secret):))"
)

SENSITIVE_ASSIGNMENT_KEYS = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "cookie",
    "credential",
    "identity_file",
    "key",
    "key_path",
    "pass",
    "passwd",
    "passphrase",
    "password",
    "private_key",
    "secret",
    "token",
}

ASSIGNMENT_KEY_RE = re.compile(r"[A-Za-z0-9_.-]+", re.IGNORECASE)
ASSIGNMENT_SENSITIVE_TOKEN_RE = re.compile(
    r"auth|cookie|credential|pass|private|secret|token|key", re.IGNORECASE
)
BEARER_RE = re.compile(r"\b(Bearer)\s+([A-Za-z0-9._~+/=-]+)", re.IGNORECASE)
WINDOWS_SECRET_SWITCH_RE = re.compile(r"^/(?P<key>p|pass|password|passwd|token|secret):(?P<value>.+)$", re.IGNORECASE)
NONSPACE_RE = re.compile(r"\S+")
URL_SCHEME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+.-")
URL_SCHEME_LETTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
SSHPASS_COMMAND_RE = re.compile(
    r"(?P<command>\bsshpass(?:\.exe)?\b)(?P<arguments>[^;&|\r\n]*)",
    re.IGNORECASE,
)
SSHPASS_SEPARATE_PASSWORD_RE = re.compile(
    r"(?P<prefix>(?<!\S)-p(?:=|\s+))(?P<password>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s;&|]+)",
    re.IGNORECASE,
)
SSHPASS_ATTACHED_PASSWORD_RE = re.compile(
    r"(?P<prefix>(?<!\S)-p)(?P<password>[^\s=;&|]+)",
    re.IGNORECASE,
)


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lstrip("-/").replace("-", "_").lower()
    return normalized in SENSITIVE_ASSIGNMENT_KEYS or any(
        token in normalized for token in SENSITIVE_KEY_TOKENS
    )


def is_share_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lstrip("-/").replace("-", "_").lower()
    return any(token in normalized for token in SHARE_SENSITIVE_KEY_TOKENS)


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(key):
                redacted[key] = REDACTED
            elif isinstance(item, str) and str(key).replace("-", "_").lower() in COMMAND_TEXT_KEYS:
                redacted[key] = _redact_command_text(item)
            else:
                redacted[key] = redact_value(item)
        return redacted
    if isinstance(value, list):
        return _redact_sequence(value)
    if isinstance(value, tuple):
        return tuple(_redact_sequence(list(value)))
    if isinstance(value, str):
        return redact_text(value)
    return value


def _redact_command_text(value: str) -> str:
    """Apply argv redaction to command copies stored alongside launch arguments."""

    if not value.strip():
        return value
    try:
        arguments = safe.argv(value, "audit command")
    except safe.CommandSafetyError:
        # A malformed or unavailable platform parser cannot establish secret
        # boundaries. Do not retain potentially sensitive command text.
        return REDACTED
    redacted = _redact_sequence(arguments)
    return value if redacted == arguments else shlex.join(redacted)


def redact_text(value: str) -> str:
    text = _redact_url_password(value)
    text = _redact_embedded_url_passwords(text)
    text = BEARER_RE.sub(r"\1 " + REDACTED, text)
    text = _redact_assignments(text)
    text = _redact_secret_arguments(text)
    text = SSHPASS_COMMAND_RE.sub(_redact_sshpass_command, text)
    return text


def _redact_sequence(value: list[Any]) -> list[Any]:
    redacted: list[Any] = []
    redact_next = False
    shell_payload_start = _opaque_shell_payload_start(value)
    sshpass_argv = bool(value) and isinstance(value[0], str) and _is_sshpass_program(value[0])
    for index, item in enumerate(value):
        if shell_payload_start is not None and index >= shell_payload_start:
            redacted.append(REDACTED)
            continue
        if redact_next:
            redacted.append(REDACTED)
            redact_next = False
            continue
        if isinstance(item, str):
            if sshpass_argv and item == "-p":
                redacted.append(item)
                redact_next = True
                continue
            if sshpass_argv and item.startswith("-p") and len(item) > 2:
                redacted.append(f"-p{REDACTED}")
                continue
            if item in SENSITIVE_ARG_NAMES:
                redacted.append(item)
                redact_next = True
                continue
            redacted.append(_redact_string_arg(item))
            continue
        redacted.append(redact_value(item))
    return redacted


def _opaque_shell_payload_start(value: list[Any]) -> int | None:
    """Keep executable shell bodies out of audit records.

    An outer argv parser cannot establish credential boundaries inside another
    interpreter's language: quoted or concatenated option names, substitutions,
    and encoded scripts all change those boundaries. All interpreter arguments
    therefore form an opaque payload, including remote shell commands and the
    different spellings of command switches accepted by individual shells.
    """

    for program_index, item in enumerate(value):
        if not isinstance(item, str):
            continue
        program = item.replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")
        if program in POSIX_SHELL_PROGRAMS | POWERSHELL_PROGRAMS | {"cmd"}:
            return program_index + 1
    return None


def _redact_string_arg(value: str) -> str:
    windows_match = WINDOWS_SECRET_SWITCH_RE.fullmatch(value)
    if windows_match:
        return f"/{windows_match.group('key')}:{REDACTED}"
    if "=" in value and "://" not in value:
        key, separator, remainder = value.partition("=")
        if _assignment_key_is_sensitive(key):
            return f"{key}{separator}{REDACTED}"
    return redact_text(value)


def _redact_assignments(value: str) -> str:
    parts: list[str] = []
    copied_to = 0
    scan_from = 0
    # Scan each complete key once instead of backtracking over token positions.
    while match := ASSIGNMENT_KEY_RE.search(value, scan_from):
        key_end = match.end()
        scan_from = key_end
        if key_end >= len(value) or value[key_end] not in ":=":
            continue
        if ASSIGNMENT_SENSITIVE_TOKEN_RE.search(match.group()) is None:
            continue
        value_start = key_end + 1
        value_end = _secret_text_value_end(value, value_start, delimiters=",;")
        if value_end == value_start:
            continue
        parts.extend((value[copied_to:value_start], REDACTED))
        copied_to = scan_from = value_end
    if not parts:
        return value
    parts.append(value[copied_to:])
    return "".join(parts)


def _redact_secret_arguments(value: str) -> str:
    parts: list[str] = []
    copied_to = 0
    for match in TEXT_SECRET_ARG_RE.finditer(value):
        if match.start() < copied_to:
            continue
        value_start = match.end()
        value_end = _secret_text_value_end(value, value_start, delimiters=";&|")
        if value_end == value_start:
            continue
        parts.extend((value[copied_to:value_start], REDACTED))
        copied_to = value_end
    if not parts:
        return value
    parts.append(value[copied_to:])
    return "".join(parts)


def _secret_text_value_end(value: str, start: int, *, delimiters: str) -> int:
    """Consume a whole quoted token, hiding the remainder if quotes never close."""

    index = start
    quote = ""
    while index < len(value):
        character = value[index]
        if character == "\\" and quote != "'":
            index = min(index + 2, len(value))
            continue
        if quote:
            if character == quote:
                quote = ""
        elif character in "\"'":
            quote = character
        elif character.isspace() or character in delimiters:
            break
        index += 1
    return index


def _redact_embedded_url_passwords(value: str) -> str:
    parts: list[str] = []
    copied_to = 0
    consumed_to = 0
    for token_match in NONSPACE_RE.finditer(value):
        token = token_match.group()
        at_positions = [index for index, char in enumerate(token) if char == "@"]
        at_index = 0
        search_from = 0
        # Every scheme candidate ends at a distinct :// delimiter.
        while (marker := token.find("://", search_from)) != -1:
            search_from = marker + 3
            scheme_start = marker
            while scheme_start > 0 and token[scheme_start - 1] in URL_SCHEME_CHARS:
                scheme_start -= 1
            if not any(char in URL_SCHEME_LETTERS for char in token[scheme_start:marker]):
                continue
            if token_match.start() + scheme_start < consumed_to:
                continue
            username_start = marker + 3
            username_end = username_start
            while username_end < len(token) and token[username_end] not in "/@:":
                username_end += 1
            if (
                username_end == username_start
                or username_end == len(token)
                or token[username_end] != ":"
            ):
                continue
            password_start = username_end + 1
            while at_index < len(at_positions) and at_positions[at_index] < password_start:
                at_index += 1
            if at_index == len(at_positions) or at_positions[at_index] == password_start:
                continue
            password_start += token_match.start()
            password_end = token_match.start() + at_positions[at_index]
            parts.extend((value[copied_to:password_start], REDACTED))
            copied_to = password_end
            consumed_to = password_end + 1
    if not parts:
        return value
    parts.append(value[copied_to:])
    return "".join(parts)


def _redact_sshpass_command(match: re.Match[str]) -> str:
    arguments = SSHPASS_SEPARATE_PASSWORD_RE.sub(
        lambda item: f"{item.group('prefix')}{REDACTED}",
        match.group("arguments"),
    )
    arguments = SSHPASS_ATTACHED_PASSWORD_RE.sub(
        lambda item: f"{item.group('prefix')}{REDACTED}",
        arguments,
    )
    return f"{match.group('command')}{arguments}"


def _is_sshpass_program(value: str) -> bool:
    basename = value.replace("\\", "/").rsplit("/", 1)[-1].casefold()
    return basename in {"sshpass", "sshpass.exe"}


def _assignment_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lstrip("-/").replace("-", "_").lower()
    return normalized in SENSITIVE_ASSIGNMENT_KEYS or is_sensitive_key(normalized)


def _redact_url_password(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if (
        not parsed.scheme
        or parsed.scheme[0] not in URL_SCHEME_LETTERS
        or not parsed.netloc
        or parsed.password is None
    ):
        return value
    username = parsed.username or ""
    hostname = parsed.hostname or ""
    if not hostname:
        return value
    try:
        parsed_port = parsed.port
    except ValueError:
        parsed_port = None
    port = f":{parsed_port}" if parsed_port is not None else ""
    display_hostname = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{username}:{REDACTED}@{display_hostname}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

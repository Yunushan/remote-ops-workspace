from __future__ import annotations

import ctypes
import os
import shlex
from collections.abc import Iterable
from ctypes import wintypes
from typing import Any
from urllib.parse import urlparse


class CommandSafetyError(ValueError):
    pass


def clean_text(value: str | None, label: str, *, allow_empty: bool = False) -> str:
    if value is None:
        if allow_empty:
            return ""
        raise CommandSafetyError(f"{label} is required")
    text = str(value)
    if not text and not allow_empty:
        raise CommandSafetyError(f"{label} is required")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise CommandSafetyError(f"{label} contains control characters")
    return text


def host(value: str | None, label: str = "host") -> str:
    text = clean_text(value, label)
    if text.startswith("-"):
        raise CommandSafetyError(f"{label} must not start with '-'")
    if any(char.isspace() for char in text):
        raise CommandSafetyError(f"{label} must not contain whitespace")
    return text


def option_value(value: str | None, label: str) -> str:
    text = clean_text(value, label)
    if text.startswith("-"):
        raise CommandSafetyError(f"{label} must not start with '-'")
    return text


def path_arg(value: str | None, label: str = "path") -> str:
    return clean_text(value, label)


def port(value: int | None, label: str = "port") -> int:
    if value is None:
        raise CommandSafetyError(f"{label} is required")
    if not 1 <= int(value) <= 65535:
        raise CommandSafetyError(f"{label} must be between 1 and 65535")
    return int(value)


def url(value: str, allowed_schemes: Iterable[str] = ("http", "https")) -> str:
    text = clean_text(value, "url")
    if any(char.isspace() for char in text):
        raise CommandSafetyError("url must not contain whitespace")
    parsed = urlparse(text)
    schemes = {scheme.lower() for scheme in allowed_schemes}
    if parsed.scheme.lower() not in schemes:
        raise CommandSafetyError(f"url scheme must be one of: {', '.join(sorted(schemes))}")
    if not parsed.netloc:
        raise CommandSafetyError("url requires a host")
    if parsed.password is not None:
        raise CommandSafetyError("url must not contain an embedded password")
    return text


def argv(command: str, label: str = "command") -> list[str]:
    # Outer whitespace is not part of any argv item on either supported
    # command-line grammar. Trim it before CommandLineToArgvW so its special
    # leading-whitespace empty-argv[0] behavior cannot reject a valid command.
    text = clean_text(command, label).strip()
    # CommandLineToArgvW has a surprising empty-input special case: it returns
    # the current process executable. Preserve argv()'s cross-platform
    # fail-closed contract instead of silently launching the application.
    if not text.strip():
        return argv_list([], label)
    if os.name == "nt":
        parts = _windows_command_line_to_argv(text, label)
        return argv_list(parts, label)
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        raise CommandSafetyError(f"{label} is not a valid command line: {exc}") from exc
    return argv_list(parts, label)


def _windows_command_line_to_argv(command: str, label: str) -> list[str]:
    """Parse text with the same quoting rules used by native Windows programs.

    POSIX ``shlex`` treats every backslash as an escape character, corrupting
    ordinary Windows paths before they reach ``CreateProcessW``.  The shell32
    parser implements the platform contract without invoking a command shell.
    """

    try:
        win_dll: Any = getattr(ctypes, "WinDLL")
        get_last_error: Any = getattr(ctypes, "get_last_error")
        shell32 = win_dll("shell32", use_last_error=True)
        kernel32 = win_dll("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise CommandSafetyError(
            f"{label} cannot be parsed because the Windows command-line API is unavailable"
        ) from exc

    command_line_to_argv = shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    command_line_to_argv.restype = ctypes.POINTER(wintypes.LPWSTR)
    local_free = kernel32.LocalFree
    local_free.argtypes = [wintypes.HLOCAL]
    local_free.restype = wintypes.HLOCAL

    argument_count = ctypes.c_int()
    parsed = command_line_to_argv(command, ctypes.byref(argument_count))
    if not parsed:
        error_code = get_last_error()
        raise CommandSafetyError(
            f"{label} is not a valid Windows command line (error {error_code})"
        )
    try:
        return [parsed[index] for index in range(argument_count.value)]
    finally:
        local_free(ctypes.cast(parsed, wintypes.HLOCAL))


def argv_list(parts: Iterable[str], label: str = "command") -> list[str]:
    argv = [clean_text(part, f"{label} argument") for part in parts]
    if not argv:
        raise CommandSafetyError(f"{label} must not be empty")
    return argv


def shellish_text(value: str | None, label: str) -> str:
    text = clean_text(value, label)
    if "\n" in text or "\r" in text:
        raise CommandSafetyError(f"{label} must be a single line")
    return text


def display(value: str | None) -> str:
    text = clean_text(value or ":0", "display")
    if not text.startswith(":"):
        raise CommandSafetyError("display must start with ':'")
    number = text[1:]
    if "." in number:
        number, screen = number.split(".", 1)
        if not screen.isdigit():
            raise CommandSafetyError("display screen must be numeric")
    if not number.isdigit():
        raise CommandSafetyError("display number must be numeric")
    return text

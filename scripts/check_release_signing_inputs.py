"""Validate the inputs consumed by protected Windows and macOS signing jobs."""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from collections.abc import Mapping
from urllib.parse import urlsplit
from uuid import UUID

OPENSSL = "/usr/bin/openssl"
MAX_SECRET_BYTES = 48 * 1024
SIGNING_INPUTS = {
    "windows": ("ROW_WINDOWS_CERTIFICATE_BASE64", "ROW_WINDOWS_CERTIFICATE_PASSWORD", "ROW_WINDOWS_TIMESTAMP_URL"),
    "macos": ("ROW_MACOS_CERTIFICATE_BASE64", "ROW_MACOS_CERTIFICATE_PASSWORD", "ROW_MACOS_SIGN_IDENTITY",
              "ROW_MACOS_INSTALLER_SIGN_IDENTITY", "ROW_MACOS_NOTARY_KEY_BASE64", "ROW_MACOS_NOTARY_KEY_ID",
              "ROW_MACOS_NOTARY_ISSUER"),
}


def decode_secret(value: str, name: str) -> bytes:
    try:
        raw = value.encode("ascii")
        if len(raw) > MAX_SECRET_BYTES:
            raise ValueError
        contents = base64.b64decode(b"".join(raw.split()), validate=True)
        if not contents:
            raise ValueError
        return contents
    except ValueError:
        raise ValueError(f"{name} must contain non-empty base64 within the Actions secret limit") from None


def run_openssl(*options: str, contents: bytes, password: str | None = None) -> subprocess.CompletedProcess[bytes]:
    # Use the system tool directly. Only the selected bundle password is passed
    # to the child and no OpenSSL output is inherited by the workflow log.
    env = {"LC_ALL": "C"}
    if password is not None:
        env["ROW_OPENSSL_IMPORT_PASSWORD"] = password
    try:
        return subprocess.run(
            [OPENSSL, *options], input=contents, capture_output=True, env=env, timeout=15, check=False,
        )
    except OSError:
        raise ValueError("system OpenSSL is unavailable for the offline signing input check") from None
    except subprocess.TimeoutExpired:
        raise ValueError("system OpenSSL timed out checking a signing input") from None


def check_pkcs12(contents: bytes, password: str, name: str) -> None:
    # Decrypt the key bags as well as the outer MAC. Discard decoded
    # credentials inside OpenSSL so only bag metadata reaches this process.
    options = ("pkcs12", "-info", "-noenc", "-out", os.devnull, "-passin", "env:ROW_OPENSSL_IMPORT_PASSWORD")
    result = run_openssl(*options, contents=contents, password=password)
    if result.returncode != 0:
        # Native certificate exports may use older PKCS#12 encryption.
        result = run_openssl(*options, "-legacy", contents=contents, password=password)
    if result.returncode != 0:
        raise ValueError(f"{name} could not be opened with the configured password")
    bags = result.stderr.splitlines()
    if not any(line.startswith(b"MAC: ") for line in bags):
        raise ValueError(f"{name} does not have a verifiable password MAC")
    if b"Certificate bag" not in bags or not any(
        line == b"Key bag" or line.startswith(b"Shrouded Keybag: ") for line in bags
    ):
        raise ValueError(f"{name} must include a certificate and a private key")


def check_timestamp_url(value: str) -> None:
    try:
        url = urlsplit(value)
        port = url.port
        if (url.scheme in {"http", "https"} and url.hostname and url.username is None and url.password is None
                and port != 0 and not any(char.isspace() for char in value)):
            return
    except ValueError:
        pass
    raise ValueError("ROW_WINDOWS_TIMESTAMP_URL must be a credential-free HTTP or HTTPS URL")


def check_notary_key(contents: bytes) -> None:
    pem = contents.strip()
    header = (b"-----BEGIN PRIVATE KEY-----\n", b"-----BEGIN PRIVATE KEY-----\r\n")
    if not pem.startswith(header) or not pem.endswith(b"-----END PRIVATE KEY-----"):
        raise ValueError("ROW_MACOS_NOTARY_KEY_BASE64 must contain an unencrypted PKCS#8 PEM private key")
    checked = run_openssl("pkey", "-inform", "PEM", "-passin", "pass:", "-check", "-text_pub", "-noout", contents=pem)
    if checked.returncode != 0 or b"ASN1 OID: prime256v1" not in checked.stdout.splitlines():
        raise ValueError("ROW_MACOS_NOTARY_KEY_BASE64 must contain a valid P-256 private key")


def check_inputs(target: str, environment: Mapping[str, str]) -> None:
    names = SIGNING_INPUTS[target]
    missing = [name for name in names if not environment.get(name, "").strip()]
    if missing:
        raise ValueError("missing release signing inputs " + ", ".join(missing))

    bundle, password = names[:2]
    contents = decode_secret(environment[bundle], bundle)
    if target == "windows":
        check_timestamp_url(environment["ROW_WINDOWS_TIMESTAMP_URL"])
    else:
        for name in ("ROW_MACOS_SIGN_IDENTITY", "ROW_MACOS_INSTALLER_SIGN_IDENTITY"):
            if "\n" in environment[name] or "\r" in environment[name]:
                raise ValueError(f"{name} must be on one line")
        key_id = environment["ROW_MACOS_NOTARY_KEY_ID"]
        if not key_id.isascii() or not key_id.isalnum():
            raise ValueError("ROW_MACOS_NOTARY_KEY_ID must contain only ASCII letters and digits")
        issuer = environment["ROW_MACOS_NOTARY_ISSUER"]
        try:
            if str(UUID(issuer)) != issuer.lower():
                raise ValueError
        except ValueError:
            raise ValueError("ROW_MACOS_NOTARY_ISSUER must be a team issuer UUID") from None
        notary_name = "ROW_MACOS_NOTARY_KEY_BASE64"
        check_notary_key(decode_secret(environment[notary_name], notary_name))
    check_pkcs12(contents, environment[password], bundle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=SIGNING_INPUTS)
    args = parser.parse_args(argv)
    try:
        check_inputs(args.target, os.environ)
    except ValueError as exc:
        print(f"release signing inputs ({args.target}): {exc}", file=sys.stderr)
        return 1
    print(f"Offline release signing input checks passed for {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

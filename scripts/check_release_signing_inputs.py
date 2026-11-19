"""Validate the inputs consumed by protected Windows and macOS signing jobs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import ssl
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_pkcs12_keys import verify_private_keys  # noqa: E402

OPENSSL = "/usr/bin/openssl"
MAX_SECRET_BYTES = 48 * 1024
SIGNING_INPUTS = {
    "windows": ("ROW_WINDOWS_CERTIFICATE_BASE64", "ROW_WINDOWS_CERTIFICATE_PASSWORD", "ROW_WINDOWS_TIMESTAMP_URL"),
    "macos": ("ROW_MACOS_CERTIFICATE_BASE64", "ROW_MACOS_CERTIFICATE_PASSWORD", "ROW_MACOS_SIGN_IDENTITY",
              "ROW_MACOS_INSTALLER_SIGN_IDENTITY", "ROW_MACOS_NOTARY_KEY_BASE64", "ROW_MACOS_NOTARY_KEY_ID",
              "ROW_MACOS_NOTARY_ISSUER"),
}
MACOS_CERTIFICATE_ROLES = {
    "ROW_MACOS_SIGN_IDENTITY": "1.2.840.113635.100.6.1.13",
    "ROW_MACOS_INSTALLER_SIGN_IDENTITY": "1.2.840.113635.100.6.1.14",
}
CERTIFICATE_PEM = re.compile(
    rb"^-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+^-----END CERTIFICATE-----\r?$",
    re.MULTILINE,
)


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


def check_pkcs12(contents: bytes, password: str, name: str, *, key_count: int = 1) -> tuple[str, ...]:
    # Decrypt the key bags as well as the outer MAC. Discard decoded
    # credentials inside OpenSSL so only bag metadata reaches this process.
    options = ("pkcs12", "-info", "-noenc", "-out", os.devnull, "-passin", "env:ROW_OPENSSL_IMPORT_PASSWORD")
    legacy = ()
    result = run_openssl(*options, contents=contents, password=password)
    if result.returncode != 0:
        # Native certificate exports may use older PKCS#12 encryption.
        legacy = ("-legacy",)
        result = run_openssl(*options, *legacy, contents=contents, password=password)
    if result.returncode != 0:
        raise ValueError(f"{name} could not be opened with the configured password")
    bags = result.stderr.splitlines()
    if not any(line.startswith(b"MAC: ") for line in bags):
        raise ValueError(f"{name} does not have a verifiable password MAC")
    keys = sum(
        line == b"Key bag" or line.startswith(b"Shrouded Keybag: ") for line in bags
    )
    if b"Certificate bag" not in bags or keys < 1:
        raise ValueError(f"{name} must include a certificate and a private key")
    if keys < key_count:
        raise ValueError(f"{name} must include private keys for both Developer ID roles")
    return legacy


def public_signing_certificates(contents: bytes, password: str, legacy: tuple[str, ...], name: str) -> list[bytes]:
    # Have OpenSSL select certificates associated with key bags and emit only
    # public data. Repeated copies of one certificate do not add a selector.
    result = run_openssl(
        "pkcs12", "-clcerts", "-nokeys", "-passin", "env:ROW_OPENSSL_IMPORT_PASSWORD",
        *legacy, contents=contents, password=password,
    )
    if result.returncode != 0:
        raise ValueError(f"could not read public certificates from {name}")
    return list(dict.fromkeys(CERTIFICATE_PEM.findall(result.stdout.replace(b"\r\n", b"\n"))))


def certificate_validity(metadata: str) -> tuple[datetime, datetime]:
    dates = dict(re.findall(r"^(notBefore|notAfter)=(.+)$", metadata, flags=re.MULTILINE))
    first = parsedate_to_datetime(dates["notBefore"])
    last = parsedate_to_datetime(dates["notAfter"])
    if first.tzinfo is None or last.tzinfo is None:
        raise ValueError
    return first, last


def windows_signing_candidate(pem: bytes, now: datetime) -> bool:
    result = run_openssl(
        "x509", "-inform", "PEM", "-noout", "-dates", "-ext", "basicConstraints,keyUsage,extendedKeyUsage",
        contents=pem,
    )
    if result.returncode != 0:
        raise ValueError("could not read a Windows signing certificate")
    try:
        metadata = result.stdout.decode("utf-8").replace("\r\n", "\n")
        first, last = certificate_validity(metadata)
    except (KeyError, ValueError):
        raise ValueError("could not read Windows signing certificate metadata") from None
    _, *sections = re.split(
        r"^X509v3 (Basic Constraints|Key Usage|Extended Key Usage):[^\n]*\n?",
        metadata,
        flags=re.MULTILINE,
    )
    extensions = {
        name: {item.strip() for item in values.split(",")}
        for name, values in zip(sections[::2], sections[1::2], strict=True)
    }
    return (
        first <= now < last
        and "CA:FALSE" in extensions.get("Basic Constraints", {"CA:FALSE"})
        and "Digital Signature" in extensions.get("Key Usage", {"Digital Signature"})
        and not {"Code Signing", "1.3.6.1.5.5.7.3.3"}.isdisjoint(extensions.get("Extended Key Usage", {"Code Signing"}))
    )


def check_windows_signing_certificate(contents: bytes, password: str, legacy: tuple[str, ...], name: str) -> bytes:
    certificates = public_signing_certificates(contents, password, legacy, name)
    now = datetime.now(timezone.utc)
    eligible = [pem for pem in certificates if windows_signing_candidate(pem, now)]
    if not eligible:
        raise ValueError(f"{name} has no currently valid leaf certificate compatible with code signing")
    if len(eligible) > 1:
        raise ValueError(f"{name} has multiple currently valid code-signing certificates")
    return eligible[0]


def developer_id_certificate(pem: bytes) -> tuple[str, str, set[str], datetime, datetime]:
    subject_options = "sep_multiline,sname,utf8,esc_ctrl"
    result = run_openssl(
        "x509", "-inform", "PEM", "-noout", "-subject", "-nameopt", subject_options, "-dates", "-text",
        contents=pem,
    )
    if result.returncode != 0:
        raise ValueError("could not read a macOS signing certificate")
    try:
        subject, details = result.stdout.decode("utf-8").replace("\r\n", "\n").split("\nCertificate:\n", 1)
        common_names = re.findall(r"^    CN=(.+)$", subject, flags=re.MULTILINE)
        if len(common_names) != 1:
            raise ValueError
        first, last = certificate_validity(subject)
        roles = set(re.findall(r"^ {12}(1\.2\.840\.113635\.100\.6\.1\.(?:13|14)):", details, flags=re.MULTILINE))
        fingerprint = hashlib.sha1(ssl.PEM_cert_to_DER_cert(pem.decode("ascii")), usedforsecurity=False).hexdigest()
    except (KeyError, ValueError):
        raise ValueError("could not read macOS signing certificate metadata") from None
    return common_names[0], fingerprint, roles, first, last


def check_developer_id_certificates(
    contents: bytes, password: str, legacy: tuple[str, ...], environment: Mapping[str, str],
) -> list[bytes]:
    certificates = [
        (pem, *developer_id_certificate(pem))
        for pem in public_signing_certificates(contents, password, legacy, "ROW_MACOS_CERTIFICATE_BASE64")
    ]
    selected = []
    now = datetime.now(timezone.utc)
    for name, role in MACOS_CERTIFICATE_ROLES.items():
        identity = environment[name].casefold()
        by_fingerprint = re.fullmatch(r"[0-9a-f]{40}", identity) is not None
        matches = [
            (pem, roles, first, last) for pem, subject, fingerprint, roles, first, last in certificates
            if (identity == fingerprint if by_fingerprint else identity in subject.casefold())
        ]
        if len(matches) != 1:
            raise ValueError(f"{name} must select one certificate in ROW_MACOS_CERTIFICATE_BASE64")
        pem, roles, first, last = matches[0]
        if roles != {role}:
            raise ValueError(f"{name} selects a certificate with the wrong Developer ID role")
        if not first <= now < last:
            raise ValueError(f"{name} selects a certificate outside its validity period")
        selected.append(pem)
    return selected


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
        legacy = check_pkcs12(contents, environment[password], bundle)
        selected = [check_windows_signing_certificate(contents, environment[password], legacy, bundle)]
    else:
        for name in MACOS_CERTIFICATE_ROLES:
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
        legacy = check_pkcs12(contents, environment[password], bundle, key_count=len(MACOS_CERTIFICATE_ROLES))
        selected = check_developer_id_certificates(contents, environment[password], legacy, environment)
    verify_private_keys(contents, environment[password], selected, legacy=bool(legacy))


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

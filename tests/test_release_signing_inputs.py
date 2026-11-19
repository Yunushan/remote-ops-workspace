from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_release_signing_inputs as signing

P12 = b"disposable bundle fixture"
KEY = b"-----BEGIN PRIVATE KEY-----\nmocked fixture\n-----END PRIVATE KEY-----\n"
PASSWORD = "disposable-fake-password"
P12_INFO = b"MAC: sha256, Iteration 2048\nShrouded Keybag: PBES2\nCertificate bag\n"
APP_PEM = b"-----BEGIN CERTIFICATE-----\nYXBw\n-----END CERTIFICATE-----"
INSTALLER_PEM = b"-----BEGIN CERTIFICATE-----\ncGtn\n-----END CERTIFICATE-----"


def public_certificate(issuer_role: str, *, common_name: str | None = None,
                       not_before: str = "Jan 1 00:00:00 2000 GMT", not_after: str = "Jan 1 00:00:00 2099 GMT") -> bytes:
    oid = {"Application": "13", "Installer": "14"}.get(issuer_role, issuer_role)
    subject = common_name or f"Developer ID {issuer_role}: Disposable fixture"
    return (
        f"subject=\n    CN={subject}\nnotBefore={not_before}\nnotAfter={not_after}\n"
        f"Certificate:\n    Data:\n        X509v3 extensions:\n            1.2.840.113635.100.6.1.{oid}: critical\n"
    ).encode()


def windows_certificate(*extensions: str, not_before: str = "Jan 1 00:00:00 2000 GMT",
                        not_after: str = "Jan 1 00:00:00 2099 GMT") -> bytes:
    return "\n".join((f"notBefore={not_before}", f"notAfter={not_after}", *extensions, "")).encode()


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def inputs(target: str) -> dict[str, str]:
    if target == "windows":
        return {
            "ROW_WINDOWS_CERTIFICATE_BASE64": encode(P12),
            "ROW_WINDOWS_CERTIFICATE_PASSWORD": PASSWORD,
            "ROW_WINDOWS_TIMESTAMP_URL": "https://timestamp.example.invalid/api",
        }
    return {
        "ROW_MACOS_CERTIFICATE_BASE64": encode(P12),
        "ROW_MACOS_CERTIFICATE_PASSWORD": PASSWORD,
        "ROW_MACOS_SIGN_IDENTITY": "Developer ID Application: Disposable fixture",
        "ROW_MACOS_INSTALLER_SIGN_IDENTITY": "Developer ID Installer: Disposable fixture",
        "ROW_MACOS_NOTARY_KEY_BASE64": encode(KEY),
        "ROW_MACOS_NOTARY_KEY_ID": "FIXTURE123",
        "ROW_MACOS_NOTARY_ISSUER": "abcdabcd-abcd-1234-abcd-abcdabcdabcd",
    }


@pytest.mark.parametrize("target", ["windows", "macos"])
def test_only_the_selected_secret_reaches_the_system_tool(monkeypatch, target) -> None:
    values = inputs(target)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GITHUB_TOKEN", "other-secret")
    observed = []

    def run(command, *, input, capture_output, env, timeout, check):
        assert command[0] == signing.OPENSSL and capture_output and not check and timeout > 0
        observed.append(command[1])
        assert all(value not in command for value in values.values())
        if command[1] == "pkey":
            assert target == "macos" and input == KEY.strip()
            assert env == {"LC_ALL": "C"}
            return subprocess.CompletedProcess(command, 0, b"ASN1 OID: prime256v1\n", b"")
        if command[1] == "x509":
            assert env == {"LC_ALL": "C"}
            assert input in (APP_PEM, INSTALLER_PEM)
            if target == "windows":
                assert input == APP_PEM and "-ext" in command
                return subprocess.CompletedProcess(command, 0, windows_certificate(
                    "X509v3 Basic Constraints: critical\n    CA:FALSE",
                    "X509v3 Key Usage: critical\n    Digital Signature",
                    "X509v3 Extended Key Usage: \n    Code Signing",
                ), b"")
            role = "Application" if input == APP_PEM else "Installer"
            return subprocess.CompletedProcess(command, 0, public_certificate(role), b"")
        assert command[1] == "pkcs12" and input == P12
        assert "-nomacver" not in command
        assert env == {"LC_ALL": "C", "ROW_OPENSSL_IMPORT_PASSWORD": PASSWORD}
        if "-nokeys" in command:
            assert "-clcerts" in command and "-noenc" not in command
            certs = (APP_PEM, INSTALLER_PEM) if target == "macos" else (APP_PEM,)
            return subprocess.CompletedProcess(command, 0, b"\n".join(certs), b"")
        assert command[command.index("-out") + 1] == os.devnull
        if target == "macos":
            return subprocess.CompletedProcess(command, 0, b"", P12_INFO + b"Key bag\nCertificate bag\n")
        return subprocess.CompletedProcess(command, 0, b"", P12_INFO)

    monkeypatch.setattr(signing.subprocess, "run", run)
    assert signing.main([target]) == 0
    assert observed == (
        ["pkey", "pkcs12", "pkcs12", "x509", "x509"] if target == "macos" else ["pkcs12", "pkcs12", "x509"]
    )


def mock_certificate_metadata(monkeypatch, certificates):
    def run(*args, contents, **kwargs):
        if args[0] == "pkcs12":
            assert "-clcerts" in args and "-nokeys" in args
            return subprocess.CompletedProcess(args, 0, b"\n".join(certificates), b"")
        assert args[0] == "x509"
        return subprocess.CompletedProcess(args, 0, certificates[contents], b"")

    monkeypatch.setattr(signing, "run_openssl", run)


def test_developer_id_selector_accepts_fingerprint_and_unambiguous_partial_name(monkeypatch):
    values = inputs("macos")
    values["ROW_MACOS_SIGN_IDENTITY"] = hashlib.sha1(b"app", usedforsecurity=False).hexdigest().upper()
    values["ROW_MACOS_INSTALLER_SIGN_IDENTITY"] = "Developer ID Installer"
    mock_certificate_metadata(monkeypatch, {
        APP_PEM: public_certificate("Application"),
        INSTALLER_PEM: public_certificate("Installer"),
    })
    signing.check_developer_id_certificates(P12, PASSWORD, ("-legacy",), values)


@pytest.mark.parametrize(("selector", "certificates", "error"), [
    ("Developer ID Installer: Disposable fixture", {APP_PEM: public_certificate("Application")}, "select one"),
    ("Disposable fixture", {APP_PEM: public_certificate("Application"),
                            INSTALLER_PEM: public_certificate("Installer")}, "select one"),
    ("Developer ID Installer", {INSTALLER_PEM: public_certificate(
        "Application", common_name="Developer ID Installer: Wrong role",
    )}, "wrong Developer ID role"),
    ("Developer ID Installer", {INSTALLER_PEM: public_certificate(
        "Installer", not_after="Jan 1 00:00:00 2001 GMT",
    )}, "outside its validity period"),
    ("Developer ID Installer", {INSTALLER_PEM: public_certificate(
        "Installer", not_before="Jan 1 00:00:00 2098 GMT",
    )}, "outside its validity period"),
])
def test_developer_id_refuses_unusable_installer_selection(monkeypatch, selector, certificates, error):
    values = {**inputs("macos"), "ROW_MACOS_INSTALLER_SIGN_IDENTITY": selector}
    mock_certificate_metadata(monkeypatch, {APP_PEM: public_certificate("Application"), **certificates})
    with pytest.raises(ValueError, match=f"ROW_MACOS_INSTALLER_SIGN_IDENTITY.*{error}") as failure:
        signing.check_developer_id_certificates(P12, PASSWORD, (), values)
    assert selector not in str(failure.value)


def test_macos_requires_both_private_key_bags(monkeypatch):
    monkeypatch.setattr(signing, "check_notary_key", lambda _: None)
    monkeypatch.setattr(signing, "run_openssl", lambda *a, **k: subprocess.CompletedProcess(a, 0, b"", P12_INFO))
    with pytest.raises(ValueError, match="private keys for both Developer ID roles"):
        signing.check_inputs("macos", inputs("macos"))


@pytest.mark.parametrize("certificates", [
    {},
    {APP_PEM: windows_certificate("X509v3 Extended Key Usage: \n    TLS Web Server Authentication")},
    {APP_PEM: windows_certificate("X509v3 Key Usage: critical\n    Key Encipherment")},
    {APP_PEM: windows_certificate("X509v3 Basic Constraints: critical\n    CA:TRUE")},
    {APP_PEM: windows_certificate(not_after="Jan 1 00:00:00 2001 GMT")},
    {APP_PEM: windows_certificate(not_before="Jan 1 00:00:00 2098 GMT")},
])
def test_windows_refuses_pfx_without_eligible_leaf_certificate(monkeypatch, certificates):
    mock_certificate_metadata(monkeypatch, certificates)
    with pytest.raises(ValueError, match="no currently valid leaf certificate compatible with code signing"):
        signing.check_windows_signing_certificate(P12, PASSWORD, (), "ROW_WINDOWS_CERTIFICATE_BASE64")


def test_windows_refuses_ambiguous_pfx_without_automatic_selection(monkeypatch):
    mock_certificate_metadata(monkeypatch, {
        APP_PEM: windows_certificate("X509v3 Extended Key Usage: \n    Code Signing, E-mail Protection"),
        INSTALLER_PEM: windows_certificate(),
    })
    with pytest.raises(ValueError, match="multiple currently valid code-signing certificates"):
        signing.check_windows_signing_certificate(P12, PASSWORD, (), "ROW_WINDOWS_CERTIFICATE_BASE64")


def test_windows_allows_one_eligible_leaf_with_unrelated_certificate(monkeypatch):
    mock_certificate_metadata(monkeypatch, {
        APP_PEM: windows_certificate("X509v3 Extended Key Usage: \n    1.3.6.1.5.5.7.3.3"),
        INSTALLER_PEM: windows_certificate("X509v3 Extended Key Usage: \n    TLS Web Client Authentication"),
    })
    signing.check_windows_signing_certificate(P12, PASSWORD, ("-legacy",), "ROW_WINDOWS_CERTIFICATE_BASE64")


@pytest.mark.parametrize(("target", "name", "value"), [
    ("windows", "ROW_WINDOWS_CERTIFICATE_PASSWORD", ""),
    ("windows", "ROW_WINDOWS_CERTIFICATE_BASE64", "!disposable-fixture!"),
    ("windows", "ROW_WINDOWS_TIMESTAMP_URL", "https://user:fake-timestamp-secret@invalid.test/"),
    ("windows", "ROW_WINDOWS_TIMESTAMP_URL", "https://timestamp.invalid:badport/"),
    ("macos", "ROW_MACOS_NOTARY_KEY_ID", "disposable fixture"),
    ("macos", "ROW_MACOS_NOTARY_ISSUER", "private-invalid-issuer"),
    ("macos", "ROW_MACOS_INSTALLER_SIGN_IDENTITY", "two\nlines"),
    ("macos", "ROW_MACOS_NOTARY_KEY_BASE64", encode(b"not an Apple PKCS#8 key")),
])
def test_refuses_malformed_inputs_before_opening_the_bundle(monkeypatch, capsys, target, name, value):
    for key, entry in {**inputs(target), name: value}.items():
        monkeypatch.setenv(key, entry)
    monkeypatch.setattr(signing.subprocess, "run", lambda *a, **k: pytest.fail("credential parser invoked"))
    assert signing.main([target]) == 1
    result = capsys.readouterr()
    assert not result.out and name in result.err
    if value:
        assert value not in result.err


@pytest.mark.parametrize(("info", "matching_error"), [
    (b"Certificate bag\n", "password MAC"),
    (b"MAC: sha256\nCertificate bag\n", "certificate and a private key"),
    (b"MAC: sha256\nShrouded Keybag: PBES2\n", "certificate and a private key"),
])
def test_bundle_requires_integrity_and_both_credentials(monkeypatch, info, matching_error):
    monkeypatch.setattr(signing, "run_openssl",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, b"", info))
    with pytest.raises(ValueError, match=matching_error):
        signing.check_inputs("windows", inputs("windows"))


def test_tool_failure_reports_only_the_bundle_name(monkeypatch, capsys):
    for name, value in inputs("windows").items():
        monkeypatch.setenv(name, value)
    calls = []

    def failed(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, b"private-stdout", b"private-stderr")

    monkeypatch.setattr(signing.subprocess, "run", failed)
    assert signing.main(["windows"]) == 1
    result = capsys.readouterr()
    assert not result.out
    assert "ROW_WINDOWS_CERTIFICATE_BASE64 could not be opened" in result.err
    assert all(value not in result.err for value in (PASSWORD, "private-stdout", "private-stderr"))
    assert "-legacy" not in calls[0] and "-legacy" in calls[1]


@pytest.mark.skipif(
    sys.platform != "linux" or not Path(signing.OPENSSL).is_file(), reason="requires a Linux system OpenSSL",
)
def test_real_linux_credential_parser(tmp_path):
    def openssl(*arguments):
        return subprocess.run([signing.OPENSSL, *arguments], check=True, capture_output=True, timeout=30).stdout

    key = tmp_path / "disposable.pem"
    cert = tmp_path / "disposable.crt"
    openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-noenc",
            "-subj", "/CN=Disposable candidate fixture", "-days", "1", "-keyout", str(key), "-out", str(cert),
            "-addext", "basicConstraints=critical,CA:FALSE",
            "-addext", "keyUsage=critical,digitalSignature", "-addext", "extendedKeyUsage=codeSigning")
    for format_flags in ((), ("-legacy",)):
        raw = openssl("pkcs12", "-export", "-in", str(cert), "-inkey", str(key), "-passout", f"pass:{PASSWORD}",
                      *format_flags)
        for target in ("windows", "macos"):
            values = inputs(target)
            prefix = f"ROW_{target.upper()}"
            values[f"{prefix}_CERTIFICATE_BASE64"] = encode(raw)
            if target == "macos":
                values["ROW_MACOS_NOTARY_KEY_BASE64"] = encode(key.read_bytes())
            if target == "windows":
                signing.check_inputs(target, values)
            else:
                with pytest.raises(ValueError, match="private keys for both Developer ID roles"):
                    signing.check_inputs(target, values)
            values[f"{prefix}_CERTIFICATE_PASSWORD"] = "wrong-test-password"
            with pytest.raises(ValueError, match="could not be opened with the configured password"):
                signing.check_inputs(target, values)

    wrong_curve = openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-384")
    with pytest.raises(ValueError, match="valid P-256"):
        signing.check_notary_key(wrong_curve)

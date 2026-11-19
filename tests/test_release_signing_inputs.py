from __future__ import annotations

import base64
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
        assert command[1] == "pkcs12" and input == P12
        assert command[command.index("-out") + 1] == os.devnull and "-nomacver" not in command
        assert env == {"LC_ALL": "C", "ROW_OPENSSL_IMPORT_PASSWORD": PASSWORD}
        return subprocess.CompletedProcess(command, 0, b"", P12_INFO)

    monkeypatch.setattr(signing.subprocess, "run", run)
    assert signing.main([target]) == 0
    assert observed == (["pkey", "pkcs12"] if target == "macos" else ["pkcs12"])


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
            "-subj", "/CN=Disposable candidate fixture", "-days", "1", "-keyout", str(key), "-out", str(cert))
    for format_flags in ((), ("-legacy",)):
        raw = openssl("pkcs12", "-export", "-in", str(cert), "-inkey", str(key), "-passout", f"pass:{PASSWORD}",
                      *format_flags)
        for target in ("windows", "macos"):
            values = inputs(target)
            prefix = f"ROW_{target.upper()}"
            values[f"{prefix}_CERTIFICATE_BASE64"] = encode(raw)
            if target == "macos":
                values["ROW_MACOS_NOTARY_KEY_BASE64"] = encode(key.read_bytes())
            signing.check_inputs(target, values)
            values[f"{prefix}_CERTIFICATE_PASSWORD"] = "wrong-test-password"
            with pytest.raises(ValueError, match="could not be opened with the configured password"):
                signing.check_inputs(target, values)

    wrong_curve = openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-384")
    with pytest.raises(ValueError, match="valid P-256"):
        signing.check_notary_key(wrong_curve)

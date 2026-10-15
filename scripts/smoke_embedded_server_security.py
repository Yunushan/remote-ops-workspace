"""Exercise authenticated FTP/FTPS listeners using the real optional runtimes."""
from __future__ import annotations

import argparse
import ftplib
import importlib.metadata
import io
import json
import logging
import socket
import ssl
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))


def _certificate(directory: Path) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "certificate.pem", directory / "private-key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cert_path, key_path


def _expect_denied(action) -> None:
    try:
        action()
    except ftplib.error_perm:
        return
    raise AssertionError("unauthorized operation unexpectedly succeeded")


def _exercise(directory: Path, *, tls: bool) -> dict[str, object]:
    from remote_ops_workspace.embedded_ftp import create_ftp_server

    root = directory / ("ftps-root" if tls else "ftp-root")
    root.mkdir()
    (root / "proof.txt").write_bytes(b"authenticated-read-proof\n")
    (directory / "outside.txt").write_bytes(b"must-not-be-readable\n")
    environment = {"ROW_FTP_USERNAME": "audit-user", "ROW_FTP_PASSWORD": "FAKE-INTEGRATION-PASSWORD", "ROW_FTP_TLS_REQUIRED": "1" if tls else "0"}
    cert_path, key_path = _certificate(directory)
    if tls:
        environment.update(ROW_FTP_TLS_CERT=str(cert_path), ROW_FTP_TLS_KEY=str(key_path))
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        selected_port = reservation.getsockname()[1]
    server = create_ftp_server("127.0.0.1", selected_port, root, environment=environment)
    bind_host, port = server.socket.getsockname()[:2]
    assert bind_host == "127.0.0.1"
    stopped = threading.Event()
    failures = []

    def serve() -> None:
        try:
            while not stopped.is_set():
                server.ioloop.loop(timeout=0.05, blocking=False)
        except Exception as exc:
            failures.append(str(exc))
        finally:
            server.close_all()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    context = ssl.create_default_context(cafile=str(cert_path))

    def connect(*, protected: bool = tls):
        client = ftplib.FTP_TLS(context=context, timeout=5) if protected else ftplib.FTP(timeout=5)
        client.connect("localhost" if protected else "127.0.0.1", port)
        return client

    try:
        if tls:
            with connect(protected=False) as plain:
                _expect_denied(lambda: plain.login("audit-user", environment["ROW_FTP_PASSWORD"]))
        with connect() as anonymous:
            _expect_denied(lambda: anonymous.login())
        with connect() as wrong:
            _expect_denied(lambda: wrong.login("audit-user", "WRONG-FAKE-PASSWORD"))
        with connect() as client:
            client.login("audit-user", environment["ROW_FTP_PASSWORD"])
            if tls:
                _expect_denied(lambda: client.nlst())
                client.prot_p()
            passive_host, _passive_port = client.makepasv()
            assert passive_host == "127.0.0.1"
            received = io.BytesIO()
            client.retrbinary("RETR proof.txt", received.write)
            assert received.getvalue() == b"authenticated-read-proof\n"
            _expect_denied(lambda: client.retrbinary("RETR ../outside.txt", lambda _chunk: None))
            _expect_denied(lambda: client.storbinary("STOR unauthorized.txt", io.BytesIO(b"unauthorized")))
        assert not (root / "unauthorized.txt").exists()
    finally:
        stopped.set()
        thread.join(timeout=5)
    assert not thread.is_alive() and not failures, failures
    return {
        "passed": True,
        "transport": "ftps" if tls else "ftp-loopback", "listener_address": bind_host, "listener_port": port,
        "anonymous_denied": True, "wrong_password_denied": True, "authenticated_download": True,
        "root_escape_denied": True, "default_write_denied": True, "passive_bind_loopback": True,
        "plaintext_control_denied": tls, "plaintext_data_denied": tls,
        "server_closed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.runtime_dir is not None:
        sys.path.insert(0, str(args.runtime_dir.resolve()))
    from pyftpdlib.log import config_logging

    config_logging(level=logging.ERROR)
    scratch = REPOSITORY / ".tmp"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ftp-security-smoke-", dir=scratch) as temporary:
        directory = Path(temporary).resolve()
        assert directory.is_relative_to(scratch.resolve())
        probes = []
        for tls in (False, True):
            try:
                probes.append(_exercise(directory, tls=tls))
            except Exception as exc:
                probes.append({"transport": "ftps" if tls else "ftp-loopback", "passed": False, "error": f"{type(exc).__name__}: {exc}"})
    passed = all(probe["passed"] for probe in probes)
    payload = {
        "schema": "row.embedded-server-security-smoke.v1", "passed": passed,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0], "pyftpdlib": importlib.metadata.version("pyftpdlib"),
        "pyOpenSSL": importlib.metadata.version("pyOpenSSL"), "probes": probes,
        "cryptography": importlib.metadata.version("cryptography"), "cffi": importlib.metadata.version("cffi"),
        "pyasyncore": importlib.metadata.version("pyasyncore"), "pyasynchat": importlib.metadata.version("pyasynchat"),
        "limitations": ["loopback fixture; public network firewall reachability and native X server are not exercised"],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Embedded FTP/FTPS security smoke {'passed' if passed else 'failed'}: {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

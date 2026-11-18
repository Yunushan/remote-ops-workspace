"""Exercise authenticated Debian updates in a fresh, offline Docker container."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from remote_ops_workspace.moba_customizer import canonical_update_manifest_payload  # noqa: E402
from remote_ops_workspace.update_channel import (  # noqa: E402
    MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
)

PACKAGE = "remote-ops-workspace"
TARGET = "linux-x86_64"
MANAGER = ROOT / "scripts/managed_linux_update.py"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(*args: str | Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, env=env, text=True, capture_output=True, timeout=150, check=False)


def checked(*args: str | Path) -> str:
    result = command(*args)
    result.check_returncode()
    return result.stdout.strip()


def validate_container() -> None:
    if (sys.platform != "linux" or os.geteuid() != 0 or not Path("/.dockerenv").is_file()
            or {entry.name for entry in Path("/sys/class/net").iterdir()} != {"lo"}):
        raise RuntimeError("Run this drill as root in a fresh Docker container with --network none")
    if checked("/usr/bin/dpkg", "--print-architecture") != "amd64":
        raise RuntimeError("The managed Debian drill uses amd64 installers")
    query = command("/usr/bin/dpkg-query", "--show", PACKAGE)
    if query.returncode != 1 or Path("/usr/bin/row").exists():
        raise RuntimeError("The drill needs a fresh container without a prior package installation")


def validate_deb(path: Path, expected: str) -> str:
    if sha256(path) != expected:
        raise ValueError(f"Package SHA-256 mismatch for {path.name}")
    package, version, architecture = checked(
        "/usr/bin/dpkg-deb", "--show", "--showformat=${Package}\t${Version}\t${Architecture}", path,
    ).split("\t")
    if (package != PACKAGE or architecture != "amd64" or not re.fullmatch(r"\d+\.\d+\.\d+", version)
            or path.name != f"{PACKAGE}-v{version}-linux-amd64.deb"):
        raise ValueError(f"Unexpected package identity for {path.name}")
    return version


@contextmanager
def https_feed(root: Path, payloads: dict[str, bytes], now: datetime):
    tls = Ed25519PrivateKey.generate()
    identity = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (x509.CertificateBuilder().subject_name(identity).issuer_name(identity)
                   .public_key(tls.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                   .sign(tls, None))
    ca = root / "tls-root.pem"
    ca.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key = root / "tls-key.pem"
    key.write_bytes(tls.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    key.chmod(0o600)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = payloads.get(self.path)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca, key)
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            yield f"https://localhost:{server.server_port}", ca
        finally:
            server.shutdown()
            worker.join()


def stage_policy(root: Path, name: str, package: Path, version: str, minimum: str, *,
                 origin: str, now: datetime, signer: Ed25519PrivateKey, payloads: dict[str, bytes]):
    url_path = f"/{name}/manifest.json"
    package_path = f"/{name}/{package.name}"
    body = package.read_bytes()
    manifest = {
        "schema": MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
        "organization": "Disposable qualification", "channel": "test-only",
        "version": version, "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "update_url": origin + url_path,
        "artifacts": [{"target": TARGET, "file": package.name, "name": package.name,
                       "url": origin + package_path, "size_bytes": len(body),
                       "sha256": hashlib.sha256(body).hexdigest()}],
    }
    canonical = canonical_update_manifest_payload(manifest)
    manifest["signature"] = {
        "algorithm": "ed25519", "value": base64.b64encode(signer.sign(canonical)).decode(),
        "payload_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    payloads[url_path] = json.dumps(manifest).encode()
    payloads[package_path] = body
    policy = json.loads((ROOT / "configs/update-trust-policy.example.json").read_bytes())
    public_key = base64.b64encode(signer.public_key().public_bytes_raw()).decode()
    policy.update(enabled=True, manifest_url=manifest["update_url"], public_key="ed25519:" + public_key,
                  organization=manifest["organization"], channel=manifest["channel"], selected_target=TARGET,
                  approved_targets=[TARGET], allowed_origins=[origin], minimum_version=minimum)
    policy_file = root / f"{name}-policy.json"
    policy_file.write_text(json.dumps(policy), encoding="utf-8")
    stage = root / f"{name}-stage"
    stage.mkdir(mode=0o700)
    return policy_file, stage


def failing_package(candidate: Path, root: Path) -> Path:
    fault = root / candidate.name
    tree = root / "failure-package"
    checked("/usr/bin/dpkg-deb", "--raw-extract", candidate, tree)
    post_install = tree / "DEBIAN/postinst"
    post_install.unlink(missing_ok=True)
    post_install.write_text("#!/bin/sh\nexit 42\n", encoding="ascii")
    post_install.chmod(0o755)
    checked("/usr/bin/dpkg-deb", "--root-owner-group", "--build", tree, fault)
    return fault


def qualify(args, root: Path) -> dict:
    previous = validate_deb(args.previous_deb, args.previous_sha256)
    candidate = validate_deb(args.candidate_deb, args.candidate_sha256)
    if tuple(map(int, candidate.split("."))) <= tuple(map(int, previous.split("."))):
        raise ValueError("The candidate installer must be newer than the previous installer")
    broken = failing_package(args.candidate_deb, root)
    checked("/usr/bin/dpkg", "--install", args.previous_deb)
    launcher = Path("/usr/bin/row")
    previous_launcher = sha256(launcher)
    workspace = root / "workspace"
    workspace.mkdir(mode=0o700)
    sentinel = workspace / "retained-workspace.txt"
    sentinel.write_text("Retained workspace data\n", encoding="utf-8")
    original = sha256(sentinel)
    receipts = {}
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}

    def update(name, action, *arguments, phase, code=0):
        result = command(sys.executable, "-I", MANAGER, action, "--workspace", workspace, *arguments, env=env)
        receipt = json.loads(result.stdout)
        if result.returncode != code or receipt.get("phase") != phase:
            raise RuntimeError(f"{name} expected {phase} ({code}), got {result.returncode}: {receipt}")
        receipts[name] = {"exit_code": result.returncode, **receipt}
        return receipt

    signer = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    payloads: dict[str, bytes] = {}
    stages = {}
    with https_feed(root, payloads, now) as (origin, certificate):
        env["SSL_CERT_FILE"] = str(certificate)
        for name, path, version in (("previous", args.previous_deb, previous),
                                    ("candidate", args.candidate_deb, candidate), ("failing", broken, candidate)):
            policy, stage = stage_policy(root, name, path, version, previous, origin=origin,
                                         now=now, signer=signer, payloads=payloads)
            stages[name] = (policy, stage)
            is_previous = name == "previous"
            action = "stage-previous" if is_previous else "stage-candidate"
            version_args = () if is_previous else ("--version", version)
            update(name, action, "--policy", policy, "--stage", stage, *version_args, phase="authenticated-staged")

    env.pop("SSL_CERT_FILE")
    previous_policy, previous_stage = stages["previous"]
    for name in ("candidate", "failing"):
        policy, stage = stages[name]
        transaction = root / f"{name}-transaction"
        transaction.mkdir(mode=0o700)
        outcome = "applied" if name == "candidate" else "rolled-back"
        code = 0 if name == "candidate" else 1
        receipt = update(f"{name}-apply", "apply", "--version", candidate, "--policy", policy, "--stage", stage,
                         "--previous-policy", previous_policy, "--previous-stage", previous_stage,
                         "--transaction", transaction, phase=outcome, code=code)
        if receipt["previous_sha256"] != args.previous_sha256:
            raise RuntimeError("The transaction used a different rollback package")
        expected_candidate = args.candidate_sha256 if name == "candidate" else sha256(broken)
        if receipt["candidate_sha256"] != expected_candidate:
            raise RuntimeError("The transaction used a different candidate package")
        if name == "candidate":
            if checked(launcher, "--version") != f"{PACKAGE} {candidate}" or sha256(launcher) != receipt["candidate_launcher_sha256"]:
                raise RuntimeError("The installed candidate launcher does not match the transaction")
            update("explicit-rollback", "rollback", "--transaction", transaction, phase="rolled-back")
        if checked(launcher, "--version") != f"{PACKAGE} {previous}" or sha256(launcher) != previous_launcher:
            raise RuntimeError("Rollback did not restore the original launcher")
        if sha256(sentinel) != original:
            raise RuntimeError("The package transition changed the retained workspace data")

    return {"schema": "row.managed-debian-qualification.v1", "status": "passed", "target": TARGET,
            "controller_sha256": sha256(MANAGER), "previous_sha256": args.previous_sha256,
            "candidate_sha256": args.candidate_sha256, "download_server_closed_before_apply": True,
            "workspace_unchanged": True, "production_acceptance": False, "receipts": receipts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-deb", required=True, type=Path)
    parser.add_argument("--previous-sha256", required=True)
    parser.add_argument("--candidate-deb", required=True, type=Path)
    parser.add_argument("--candidate-sha256", required=True)
    args = parser.parse_args()
    validate_container()
    with TemporaryDirectory(prefix="row-managed-update-", dir="/root") as workdir:
        report = qualify(args, Path(workdir))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

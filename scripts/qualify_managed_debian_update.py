"""Exercise authenticated Debian updates in a fresh, offline Docker container."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import signal
import ssl
import subprocess
import sys
import threading
import time
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from remote_ops_workspace.moba_customizer import canonical_update_manifest_payload  # noqa: E402
from remote_ops_workspace.update_channel import (  # noqa: E402
    MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
)
from scripts.managed_debian_qualification import SCHEMA  # noqa: E402

PACKAGE = "remote-ops-workspace"
TARGET = "linux-x86_64"
MANAGER = ROOT / "scripts/managed_linux_update.py"
SERVER_MANIFEST = Path("/usr/lib/remote-ops-workspace/servers/servers-runtime.json")
ROLLBACK_BLOCKER = "row-qualification-rollback-blocker"


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
def https_feed(root: Path, payloads: dict[str, bytes], now: datetime, *, requests: list[str] | None = None):
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
            if requests is not None:
                requests.append(self.path)
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


def package_fixture(candidate: Path, root: Path, *, postinst: str | None = None,
                    unsatisfied_dependency: bool = False) -> Path:
    root.mkdir(mode=0o700)
    fault = root / candidate.name
    tree = root / "tree"
    checked("/usr/bin/dpkg-deb", "--raw-extract", candidate, tree)
    if postinst is not None:
        post_install = tree / "DEBIAN/postinst"
        post_install.unlink(missing_ok=True)
        post_install.write_text("#!/bin/sh\nset -eu\n" + postinst, encoding="ascii")
        post_install.chmod(0o755)
    if unsatisfied_dependency:
        control = tree / "DEBIAN/control"
        text = control.read_text(encoding="utf-8")
        dependency = "libc6 (>= 99999.0)"
        text, count = re.subn(r"(?m)^Depends: ([^\n]+)$", rf"Depends: \1, {dependency}", text, count=1)
        control.write_text(text if count else f"Depends: {dependency}\n{text}", encoding="utf-8")
    checked("/usr/bin/dpkg-deb", "--root-owner-group", "--build", tree, fault)
    return fault


def build_rollback_blocker(root: Path, version: str) -> Path:
    tree = root / "package"
    control = tree / "DEBIAN" / "control"
    control.parent.mkdir(parents=True)
    tree.chmod(0o755)
    control.parent.chmod(0o755)
    control.write_text(
        f"Package: {ROLLBACK_BLOCKER}\n"
        "Version: 1\nArchitecture: all\nMaintainer: Qualification <noreply@example.invalid>\n"
        f"Depends: {PACKAGE} (= {version})\n"
        "Description: Disposable rollback dependency qualification fixture\n",
        encoding="ascii",
    )
    control.chmod(0o644)
    package = root / "rollback-blocker.deb"
    checked("/usr/bin/dpkg-deb", "--root-owner-group", "--build", tree, package)
    return package


def await_condition(predicate, message: str) -> None:
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise RuntimeError(message)


def configured_and_unlocked(version: str) -> bool:
    import fcntl

    with Path("/var/lib/dpkg/lock").open("rb+") as database_lock:
        try:
            fcntl.lockf(database_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return checked("/usr/bin/dpkg-query", "--show", "--showformat=${db:Status-Status} ${Version}", PACKAGE
                       ) == f"installed {version}"


def interrupt_controller(
    command_line, env, entered: Path, resume: Path, transaction: Path, version: str, *, phase: str = "applying",
) -> int:
    journal = transaction / "managed-update.json"
    with subprocess.Popen(command_line, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
        try:
            await_condition(lambda: entered.is_file() or process.poll() is not None,
                            f"The {phase} dpkg command did not reach its pause")
            if not entered.is_file() or process.poll() is not None:
                raise RuntimeError("The controller exited before the interruption point")
            if json.loads(journal.read_bytes())["phase"] != phase:
                raise RuntimeError(f"The interrupted command did not persist phase {phase}")
            process.terminate()
            exit_code = process.wait(timeout=10)
            if exit_code != -signal.SIGTERM:
                raise RuntimeError("The controller did not exit from the controlled interruption")
        finally:
            resume.touch()
            if process.poll() is None:
                process.kill()
    # The owned controller has exited. Allow its native child to finish
    # and confirm the package database is available before retrying.
    await_condition(lambda: configured_and_unlocked(version), "dpkg did not finish the interrupted command")
    if json.loads(journal.read_bytes())["phase"] != phase:
        raise RuntimeError("The interrupted transaction journal advanced unexpectedly")
    return exit_code


def pause_script(entered: Path, resume: Path) -> str:
    return (
        f"touch {shlex.quote(str(entered))}\n"
        "for attempt in $(seq 1 300); do\n"
        f"  if [ -f {shlex.quote(str(resume))} ]; then exit 0; fi\n"
        "  sleep 0.1\ndone\nexit 43\n"
    )


@contextmanager
def pause_dpkg_rollback(root: Path):
    """Hold the real dpkg after reinstalling the byte-pinned predecessor."""
    config = Path("/etc/dpkg/dpkg.cfg.d/row-managed-rollback-qualification")
    entered = root / "rollback-entered"
    resume = root / "rollback-resume"
    hook = root / "pause-rollback"
    hook.write_text(
        "#!/bin/sh\nset -eu\n"
        f"printf 'install\\n' >> {shlex.quote(str(entered))}\n"
        + pause_script(entered, resume),
        encoding="ascii",
    )
    hook.chmod(0o700)
    stream = config.open("x", encoding="ascii")
    try:
        with stream:
            stream.write(f"post-invoke={shlex.quote(str(hook))}\n")
        yield entered, resume
    finally:
        config.unlink()


def qualify(args, root: Path) -> dict:
    previous = validate_deb(args.previous_deb, args.previous_sha256)
    candidate = validate_deb(args.candidate_deb, args.candidate_sha256)
    if tuple(map(int, candidate.split("."))) <= tuple(map(int, previous.split("."))):
        raise ValueError("The candidate installer must be newer than the previous installer")
    broken = package_fixture(args.candidate_deb, root / "failure", postinst="exit 42\n")
    blocked = package_fixture(args.candidate_deb, root / "dependency-blocked", unsatisfied_dependency=True)
    entered = root / "postinst-entered"
    resume = root / "postinst-resume"
    suspended = package_fixture(
        args.candidate_deb, root / "interruption",
        postinst=pause_script(entered, resume),
    )
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

    def argv(action, *arguments):
        return (sys.executable, "-I", MANAGER, action, "--workspace", workspace, *arguments)

    def update(name, action, *arguments, phase, code=0):
        result = command(*argv(action, *arguments), env=env)
        receipt = json.loads(result.stdout)
        if result.returncode != code or receipt.get("phase") != phase:
            raise RuntimeError(f"{name} expected {phase} ({code}), got {result.returncode}: {receipt}")
        receipts[name] = {"action": action, "exit_code": result.returncode, **receipt}
        return receipt

    def apply_arguments(policy, stage, previous_policy, previous_stage, transaction):
        return ("--version", candidate, "--policy", policy, "--stage", stage,
                "--previous-policy", previous_policy, "--previous-stage", previous_stage,
                "--transaction", transaction)

    signer = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    payloads: dict[str, bytes] = {}
    stages = {}
    packages = {"candidate": args.candidate_sha256, "failing": sha256(broken), "interrupted": sha256(suspended)}
    with https_feed(root, payloads, now) as (origin, certificate):
        env["SSL_CERT_FILE"] = str(certificate)
        for name, path, version in (("previous", args.previous_deb, previous),
                                    ("candidate", args.candidate_deb, candidate), ("failing", broken, candidate),
                                    ("interrupted", suspended, candidate),
                                    ("dependency-blocked", blocked, candidate)):
            policy, stage = stage_policy(root, name, path, version, previous, origin=origin,
                                         now=now, signer=signer, payloads=payloads)
            stages[name] = (policy, stage)
            is_previous = name == "previous"
            action = "stage-previous" if is_previous else "stage-candidate"
            version_args = () if is_previous else ("--version", version)
            update(name, action, "--policy", policy, "--stage", stage, *version_args, phase="authenticated-staged")

        previous_policy, previous_stage = stages["previous"]
        automatic_previous = root / "automatic-previous-stage"
        automatic_previous.mkdir(mode=0o700)
        for name in ("candidate", "failing"):
            policy, _ = stages[name]
            stage = root / f"automatic-{name}-stage"
            transaction = root / f"automatic-{name}-transaction"
            stage.mkdir(mode=0o700)
            transaction.mkdir(mode=0o700)
            arguments = apply_arguments(policy, stage, previous_policy, automatic_previous, transaction)
            succeeded = name == "candidate"
            receipt = update(f"automatic-{name}", "update", *arguments,
                             phase="applied" if succeeded else "rolled-back", code=0 if succeeded else 1)
            if receipt["previous_sha256"] != args.previous_sha256 or receipt["candidate_sha256"] != packages[name]:
                raise RuntimeError("Automatic update used different installer bytes")
            if succeeded:
                if checked(launcher, "--version") != f"{PACKAGE} {candidate}" or sha256(launcher) != receipt["candidate_launcher_sha256"]:
                    raise RuntimeError("Automatic update did not apply the exact candidate")
                update("automatic-explicit-rollback", "rollback", "--transaction", transaction, phase="rolled-back")
            if (checked(launcher, "--version") != f"{PACKAGE} {previous}" or sha256(launcher) != previous_launcher
                    or sha256(sentinel) != original):
                raise RuntimeError("Automatic update rollback did not preserve the original launcher and workspace")

    env.pop("SSL_CERT_FILE")
    blocked_policy, blocked_stage = stages["dependency-blocked"]
    blocked_tx = root / "dependency-blocked-transaction"
    blocked_tx.mkdir(mode=0o700)
    db = Path("/var/lib/dpkg/status")
    previous_db = sha256(db)
    blocked_args = apply_arguments(blocked_policy, blocked_stage, previous_policy, previous_stage, blocked_tx)
    refused = update("dependency-blocked-apply", "apply", *blocked_args, phase="refused", code=1)
    blocked_sha = sha256(blocked)
    if (refused.get("refusal") != "debian-upgrade-plan-refused"
            or (blocked_tx / "managed-update.json").exists()
            or sha256(blocked_tx / "candidate.deb") != blocked_sha
            or sha256(blocked_tx / "rollback.deb") != args.previous_sha256
            or sha256(db) != previous_db or sha256(launcher) != previous_launcher or sha256(sentinel) != original):
        raise RuntimeError("Dependency refusal changed the previous installation or transaction")
    receipts["dependency-blocked-apply"].update(
        candidate_sha256=blocked_sha, previous_sha256=args.previous_sha256,
        previous_installation_unchanged=True, journal_created=False,
    )
    bundled_servers = False
    for name, expected_candidate in packages.items():
        policy, stage = stages[name]
        transaction = root / f"{name}-transaction"
        transaction.mkdir(mode=0o700)
        outcome = "applied" if name == "candidate" else "rolled-back"
        code = 0 if name == "candidate" else 1
        arguments = apply_arguments(policy, stage, previous_policy, previous_stage, transaction)
        if name == "interrupted":
            interrupt_controller(argv("apply", *arguments), env, entered, resume, transaction, candidate)
            if checked(launcher, "--version") != f"{PACKAGE} {candidate}" or sha256(launcher) == previous_launcher:
                raise RuntimeError("The interrupted transaction never installed the candidate launcher")
        action = "apply" if name == "failing" else "update"
        receipt = update(f"{name}-apply", action, *arguments, phase=outcome, code=code)
        if receipt["previous_sha256"] != args.previous_sha256:
            raise RuntimeError("The transaction used a different rollback package")
        if receipt["candidate_sha256"] != expected_candidate:
            raise RuntimeError("The transaction used a different candidate package")
        if name == "candidate":
            if checked(launcher, "--version") != f"{PACKAGE} {candidate}" or sha256(launcher) != receipt["candidate_launcher_sha256"]:
                raise RuntimeError("The installed candidate launcher does not match the transaction")
            journal = transaction / "managed-update.json"
            applied_journal = journal.read_bytes()
            bundled_servers = SERVER_MANIFEST.is_file()
            changed_files = [(launcher, "launcher", "installed-launcher-digest-refused")]
            if bundled_servers:
                changed_files.append((SERVER_MANIFEST, "server-manifest", "installed-runtime-payload-refused"))
            # Keep dpkg's installed version unchanged while altering files in
            # the disposable container, then restore each before the real rollback.
            for path, label, refusal in changed_files:
                size = path.stat().st_size
                with path.open("ab") as output:
                    output.write(b"\nROW rollback qualification canary\n")
                changed = sha256(path)
                try:
                    rejected = update(
                        f"changed-{label}-rollback", "rollback", "--transaction", transaction,
                        phase="refused", code=1,
                    )
                    if (rejected.get("refusal") != refusal
                            or journal.read_bytes() != applied_journal
                            or sha256(path) != changed):
                        raise RuntimeError("Rollback refusal changed the installation or transaction")
                finally:
                    if path.is_file() and sha256(path) == changed:
                        with path.open("r+b") as output:
                            output.truncate(size)

            blocker = build_rollback_blocker(root / "rollback-blocker", candidate)
            checked("/usr/bin/dpkg", "--install", blocker)
            applied_db = sha256(db)
            rejected = update("dependency-blocked-rollback", "rollback", "--transaction", transaction,
                              phase="refused", code=1)
            if (rejected.get("refusal") != "debian-rollback-plan-refused"
                    or journal.read_bytes() != applied_journal or sha256(db) != applied_db
                    or sha256(launcher) != receipt["candidate_launcher_sha256"] or sha256(sentinel) != original):
                raise RuntimeError("Dependency refusal changed the applied installation or transaction")
            retry = update("dependency-blocked-update-retry", "update", *arguments, phase="applied")
            if retry != receipt or journal.read_bytes() != applied_journal:
                raise RuntimeError("The refused rollback changed the completed update")
            receipts["dependency-blocked-rollback"].update(
                previous_sha256=args.previous_sha256, candidate_sha256=args.candidate_sha256,
                candidate_installation_unchanged=True, journal_unchanged=True,
            )
            checked("/usr/bin/dpkg", "--remove", ROLLBACK_BLOCKER)

            with pause_dpkg_rollback(root) as (rollback_entered, rollback_resume):
                rollback_code = interrupt_controller(
                    argv("rollback", "--transaction", transaction), env, rollback_entered, rollback_resume,
                    transaction, previous, phase="rolling-back",
                )
                if sha256(launcher) != previous_launcher or sha256(sentinel) != original:
                    raise RuntimeError("Interrupted rollback did not restore the exact launcher and preserve workspace data")
                recovered = update("explicit-rollback", "rollback", "--transaction", transaction, phase="rolled-back")
                completed_journal = journal.read_bytes()
                repeated = update("repeated-rollback", "rollback", "--transaction", transaction, phase="rolled-back")
                if repeated != recovered or journal.read_bytes() != completed_journal:
                    raise RuntimeError("Repeating the completed rollback changed its transaction")
                native_invocations = rollback_entered.read_bytes().splitlines()
                if native_invocations != [b"install"]:
                    raise RuntimeError("Retrying an already restored rollback ran dpkg again")
            receipts["rollback-interruption"] = {
                "action": "rollback", "phase": "rolling-back", "exit_code": rollback_code,
                "previous_sha256": args.previous_sha256, "candidate_sha256": args.candidate_sha256,
                "previous_launcher_sha256": sha256(launcher),
                "native_rollback_invocations": len(native_invocations),
            }
        if checked(launcher, "--version") != f"{PACKAGE} {previous}" or sha256(launcher) != previous_launcher:
            raise RuntimeError("Rollback did not restore the original launcher")
        if sha256(sentinel) != original:
            raise RuntimeError("The package transition changed the retained workspace data")

    return {"schema": SCHEMA, "status": "passed", "target": TARGET,
            "controller_sha256": sha256(MANAGER), "previous_sha256": args.previous_sha256,
            "candidate_sha256": args.candidate_sha256, "download_server_closed_before_apply": True,
            "workspace_unchanged": True, "candidate_has_server_bundle": bundled_servers,
            "production_acceptance": False, "receipts": receipts}


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

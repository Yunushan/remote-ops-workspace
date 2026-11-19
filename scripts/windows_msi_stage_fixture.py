"""Serve provenance-verified MSI inputs on a disposable Windows runner."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from check_windows_private_ntfs import serve_https_fixture
from inspect_windows_msi import require
from managed_windows_msi import TARGET

from remote_ops_workspace.moba_customizer import canonical_update_manifest_payload
from remote_ops_workspace.update_channel import MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA
from remote_ops_workspace.windows_private_storage import private_stage_guard

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/managed_windows_msi.py"


def signed_input(origin, role, path, package, *, signer, minimum, settings, bodies):
    version = package["version"]
    name = package["name_on_release"]
    require(path.name == name == f"remote-ops-workspace-v{version}-{TARGET}.msi",
            "managed fixture MSI name differs from the verified release")
    size, digest = package["size_bytes"], package["sha256"]
    limit = min(settings["limits"]["asset_bytes"], settings["limits"]["total_asset_bytes"])
    require(0 < size <= limit, "managed fixture MSI exceeds the signed asset bounds")
    with path.open("rb") as stream:
        body = stream.read(size + 1)
    require(len(body) == size and hashlib.sha256(body).hexdigest() == digest,
            "managed fixture MSI differs from the verified release bytes")
    manifest_url, asset_url = f"/{role}/manifest.json", f"/{role}/{name}"
    manifest = {
        "schema": MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
        "organization": "Disposable Windows MSI qualification",
        "channel": "test-only",
        "version": version,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "update_url": origin + manifest_url,
        "artifacts": [{"target": TARGET, "name": name, "file": name, "url": origin + asset_url,
                       "size_bytes": size, "sha256": digest}],
    }
    payload = canonical_update_manifest_payload(manifest)
    manifest["signature"] = {"algorithm": "ed25519", "payload_sha256": hashlib.sha256(payload).hexdigest(),
                             "value": base64.b64encode(signer.sign(payload)).decode("ascii")}
    raw = json.dumps(manifest).encode("utf-8")
    bodies[manifest_url] = raw
    bodies[asset_url] = body
    public_key = base64.b64encode(signer.public_key().public_bytes_raw()).decode("ascii")
    policy = {**settings, "enabled": True, "manifest_url": manifest["update_url"],
              "public_key": f"ed25519:{public_key}", "organization": manifest["organization"],
              "channel": manifest["channel"], "minimum_version": minimum, "selected_target": TARGET,
              "approved_targets": [TARGET], "allowed_origins": [origin]}
    return hashlib.sha256(raw).hexdigest(), json.dumps(policy).encode("utf-8")


def run_managed_msi(home: Path, action: str, arguments: list[str], *, ca: Path | None = None) -> dict:
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in {"GH_TOKEN", "GITHUB_TOKEN", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
    env["ROW_HOME"] = str(home)
    if ca is not None:
        env["SSL_CERT_FILE"] = str(ca)
    command = [sys.executable, "-I", "-B", str(CLI), action, *arguments]
    completed = subprocess.run(
        command, cwd=home, env=env, capture_output=True, encoding="utf-8", timeout=600, check=False,
    )
    result = json.loads(completed.stdout)
    require(isinstance(result, dict) and "phase" in result, f"managed MSI {action} returned no phase")
    require(completed.returncode == 0,
            f"managed MSI {action} failed ({result['phase']}, {result.get('refusal', 'installer outcome')}, "
            f"exit {result.get('installer_exit_code', completed.returncode)})")
    return result


def update_unstaged_pair(root: Path, home: Path, previous, candidate) -> tuple[list[str], dict, dict]:
    """Download and install through the managed CLI using fixture-only feed credentials."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    settings = json.loads((ROOT / "configs/update-trust-policy.example.json").read_bytes())
    signer = Ed25519PrivateKey.generate()
    bodies: dict[str, bytes] = {}
    requested: list[str] = []
    pair: list[str] = []
    expected: dict[str, tuple[dict, str, str]] = {}
    with serve_https_fixture(root, bodies, requested) as (origin, cert_path):
        for role, (path, package) in (("previous", previous), ("candidate", candidate)):
            manifest_sha256, policy = signed_input(origin, role, path, package, signer=signer,
                                                   minimum=previous[1]["version"], settings=settings, bodies=bodies)
            policy_path = root / f"{role}-policy.json"
            stage = root / f"{role}-stage"
            with private_stage_guard(root) as guard:
                with os.fdopen(guard.create_private_file(policy_path), "wb") as stream:
                    stream.write(policy)
            expected[role] = (package, manifest_sha256, hashlib.sha256(policy).hexdigest())
            prefix = "previous-" if role == "previous" else ""
            for key, value in (("policy", str(policy_path)), ("stage", str(stage)), ("version", package["version"])):
                pair.extend((f"--{prefix}{key}", value))
        require(all(not os.path.lexists(root / f"{role}-stage") for role in expected),
                "managed MSI update requires both stage leaves to be absent")
        result = run_managed_msi(home, "update", pair, ca=cert_path)
        require(requested == list(bodies), "managed MSI fixture received unexpected HTTPS requests")

    staged = {"feed": "disposable-loopback-https", "initial_command": "update", "initial_stages_absent": True,
              "https_requests": requested, "feed_closed_before_retry": True}
    for role, (package, manifest_sha256, policy_sha256) in expected.items():
        record = result[f"{role}_stage"]
        require(record["phase"] == "authenticated-staged"
                and record["manifest_sha256"] == manifest_sha256
                and record["trust_policy_sha256"] == policy_sha256
                and record["version"] == package["version"]
                and record["selected_target"] == TARGET
                and record["selected_files"] == [package["name_on_release"]]
                and record["artifact_count"] == 1
                and record["artifact_total_bytes"] == package["size_bytes"]
                and record["whole_declared_asset_set_verified"] is True
                and record["windows_dacl_metadata_verified"] is True
                and record["install_permitted"] is False,
                f"managed MSI {role} stage evidence differs from the verified input")
        staged[role] = record
    return pair, staged, result


def require_same_inputs(result: dict, staged: dict, previous: dict, candidate: dict) -> None:
    require(result["target"] == TARGET and result["authenticode_and_timestamp_checked"] is True,
            "managed MSI command did not verify the Windows x64 platform signature and timestamp")
    for role, source in (("previous", previous), ("candidate", candidate)):
        msi = result[f"{role}_msi"]
        require(result[f"{role}_stage"] == staged[role]
                and msi["asset"] == source["name_on_release"]
                and all(msi[key] == source[key] for key in
                        ("sha256", "size_bytes", "version", "product_code", "package_code", "launcher_payload_sha256")),
                f"managed MSI command used different {role} inputs")

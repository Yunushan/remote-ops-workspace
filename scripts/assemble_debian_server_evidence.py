"""Assemble and verify Debian embedded-server release review inputs."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.moba_servers import SERVER_RELEASE_EVIDENCE_SCHEMA  # noqa: E402
from scripts.check_moba_server_release_evidence import (  # noqa: E402
    read_capture_json,
    service_inventory,
    validate_live_server_release_evidence,
    verify_packaged_debian_server_evidence,
)
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    secure_regular_file,
    sha256_file,
)
from scripts.debian_release_fixture import release_deb_version  # noqa: E402
from scripts.debian_server_notices import (  # noqa: E402
    MANIFEST,
    PAYLOAD,
    notice_path,
    notice_records,
)
from scripts.moba_debian_server_payload import ELF_TARGETS, server_payload  # noqa: E402

CAPTURES_INDEX = "captures.json"
RUNTIME_DIR = "runtimes"
RESERVED_PATHS = {RUNTIME_DIR, "evidence.json", CAPTURES_INDEX}


def copy_bound_file(
    source: Path, name: str, digest: Any, root: Path, *, relative: str | None = None,
) -> Path:
    original = bound_evidence_file(source, name, digest, "review input")
    target = root / (name if relative is None else relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copyfile(original, target)
    if sha256_file(target) != digest:
        raise ValueError(f"review input changed or conflicts with another attachment: {name}")
    return target


def copy_runtime(installed_root: Path, target: str, output: Path) -> dict[str, Any]:
    source = installed_root / PAYLOAD
    manifest, runtime_digests = server_payload(source, target)
    for name, digest in runtime_digests.items():
        copy_bound_file(source, name, digest, output, relative=f"{RUNTIME_DIR}/{name}")
    if "debian_notices" in manifest:
        for component, notice in notice_records(manifest["debian_notices"]).items():
            copy_bound_file(installed_root, notice_path(component).as_posix(), notice["sha256"], output,
                            relative=f"{RUNTIME_DIR}/notices/{component}.copyright")
    return manifest


def copy_capture_file(source: Path, reference: Any, output: Path) -> Path:
    if not isinstance(reference, dict) or not isinstance(name := reference.get("file"), str):
        raise ValueError("each client receipt and capture requires a file and SHA-256")
    relative = PurePosixPath(name)
    if not relative.parts or relative.as_posix() != name or ":" in name:
        raise ValueError(f"capture attachment must use a canonical relative path: {name}")
    if relative.parts[0].casefold() in RESERVED_PATHS:
        raise ValueError(f"capture attachment uses a reserved review path: {name}")
    return copy_bound_file(source, name, reference.get("sha256"), output)


def capture_entry(
    service: str, observation: dict[str, Any], runtime: dict[str, Any], source: Path, output: Path,
) -> dict[str, Any]:
    receipt_file = copy_capture_file(source, observation.get("receipt"), output)
    receipt = read_capture_json(receipt_file, f"{service} client receipt")
    argv = receipt.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        raise ValueError(f"{service} requires the recorded client argv")
    copy_capture_file(source, receipt.get("capture"), output)
    if service != "vnc" or "challenge" in receipt:
        copy_capture_file(source, receipt.get("challenge"), output)
    if service == "nfs":
        copy_capture_file(source, receipt.get("mount_options"), output)
        copy_capture_file(source, receipt.get("rejected_sys_mount"), output)
    return {
        "service": service,
        "runtime": {**runtime, "executable": f"{RUNTIME_DIR}/{runtime['executable']}"},
        "policy": observation.get("policy"),
        "client_test": {
            "status": "passed", "command": shlex.join(argv),
            "evidence_file": receipt_file.relative_to(output).as_posix(),
            "evidence_sha256": observation["receipt"]["sha256"],
        },
    }


def assemble(package: Path, target: str, installed_root: Path, captures: Path, output: Path) -> Path:
    if output.exists() or output.is_symlink():
        raise ValueError("output must be a new directory")
    index, error = secure_regular_file(captures, CAPTURES_INDEX, "capture index")
    if index is None:
        raise ValueError(error)
    observed = read_capture_json(index, "capture index")
    identity = capture_release_identity(observed, "capture index")
    version = release_deb_version(package.name, target)
    if (
        identity["tested_release_asset"] != {"name": package.name, "sha256": sha256_file(package)}
        or identity["release_tag"] != f"v{version}"
    ):
        raise ValueError("capture index must bind the supplied Debian asset and its exact release tag")
    observations = service_inventory(observed.get("services"), "capture index")

    with TemporaryDirectory(prefix=".server-evidence-", dir=output.parent) as temporary:
        root = Path(temporary) / "review"
        manifest = copy_runtime(installed_root, target, root)
        runtimes = service_inventory(manifest["services"], "installed runtime manifest")
        services = [
            capture_entry(service, entry, runtimes[service]["runtime"], captures, root)
            for service, entry in sorted(observations.items())
        ]
        relative_manifest = f"{RUNTIME_DIR}/{MANIFEST}"
        evidence = root / "evidence.json"
        evidence.write_text(json.dumps({
            "schema": SERVER_RELEASE_EVIDENCE_SCHEMA, "release_target": target,
            "source": observed["source"], "release_asset": observed["release_asset"],
            "runtime_manifest": {"file": relative_manifest, "sha256": sha256_file(root / relative_manifest)},
            "services": services,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = validate_live_server_release_evidence(evidence)
        if not result.passed:
            raise ValueError("client evidence did not pass validation\n" + "\n".join(result.errors))
        verify_packaged_debian_server_evidence(package, root, target)
        if sha256_file(package) != identity["tested_release_asset"]["sha256"]:
            raise ValueError("Debian asset changed during evidence assembly")
        root.rename(output)
    return output / "evidence.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deb", type=Path, required=True)
    parser.add_argument("--target", choices=ELF_TARGETS, required=True)
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = assemble(args.deb, args.target, args.installed_root, args.captures, args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Debian server evidence assembly failed: {exc}\n")
    print(f"Verified Debian server review inputs: {evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

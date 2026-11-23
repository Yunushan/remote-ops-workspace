from __future__ import annotations

import argparse
import json
import shlex
import struct
import sys
import zlib
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for location in (ROOT, SRC):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.moba_servers import (  # noqa: E402
    SERVER_DEFAULT_PORTS,
    SERVER_RUNTIME_BUNDLE_SCHEMA,
    MobaEmbeddedServerReleaseEvidenceValidation,
    validate_moba_server_release_evidence,
    verify_packaged_openssh_helpers,
)
from scripts.check_gui_visual_metrics import read_png_rgb  # noqa: E402
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    read_json_object,
    secure_regular_file,
)
from scripts.debian_release_fixture import release_deb_version  # noqa: E402
from scripts.moba_debian_server_payload import (  # noqa: E402
    verify_debian_notice_inputs,
    verify_debian_payload,
)

CLIENT_CAPTURE_SCHEMA = "row.moba-servers.live-client.v1"
CLIENTS = {
    "http": {"curl", "wget"},
    "ftp": {"curl", "lftp", "python", "python3"},
    "tftp": {"atftp", "tftp"},
    "ssh": {"plink", "ssh"},
    "sftp": {"psftp", "sftp"},
    "telnet": {"plink", "telnet"},
    "vnc": {"vncviewer", "vncsnapshot"},
    "nfs": {"mount", "mount.nfs", "mount.nfs4"},
}
NATIVE_HEADERS = {
    "linux": {b"\x7fELF"},
    "windows": {b"MZ"},
    "darwin": {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"},
}
PLATFORM_PREFIXES = {"linux": "linux-", "windows": "windows-", "darwin": "macos-"}


def read_capture_json(path: Path, label: str) -> dict[str, Any]:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError(f"{label} exceeds 1 MiB")
    try:
        return read_json_object(path, label)[1]
    except ValueError as exc:
        raise ValueError(f"{label} is invalid: {exc}") from exc


def asset(root: Path, reference: Any, label: str) -> Path:
    if not isinstance(reference, dict):
        raise ValueError(f"{label} requires a file and SHA-256")
    return bound_evidence_file(root, reference.get("file"), reference.get("sha256"), label)


def read_client_data(path: Path) -> bytes:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("client text or transfer evidence exceeds 1 MiB")
    return path.read_bytes()


def service_inventory(data: Any, label: str) -> dict[str, Any]:
    if not isinstance(data, list) or len(data) != len(SERVER_DEFAULT_PORTS):
        raise ValueError(f"{label} requires each of the eight services exactly once")
    entries = {}
    for entry in data:
        name = entry.get("service") if isinstance(entry, dict) else None
        if not isinstance(name, str) or name not in SERVER_DEFAULT_PORTS or name in entries:
            raise ValueError(f"{label} requires each of the eight services exactly once")
        entries[name] = entry
    return entries


def verify_runtime(
    root: Path, manifest_path: Path, system: str, runtime: dict[str, Any], packaged: Any
) -> None:
    if (
        not isinstance(packaged, dict)
        or packaged.get("placeholder") is not False
        or packaged.get("bundled") is not True
        or packaged.get("source") != "packaged"
        or not isinstance(packaged.get("executable"), str)
        or not isinstance(packaged.get("key"), str)
        or not packaged["key"]
        or packaged["key"] != runtime.get("key")
        or packaged.get("sha256") != runtime.get("sha256")
        or (manifest_path.parent.relative_to(root) / packaged["executable"]).as_posix()
        != runtime.get("executable")
    ):
        raise ValueError(
            "runtime manifest must bind the exact non-placeholder bundled service daemon"
        )
    path = bound_evidence_file(root, runtime["executable"], runtime["sha256"], "bundled daemon")
    with path.open("rb") as handle:
        header = handle.read(4)
    if not any(header.startswith(signature) for signature in NATIVE_HEADERS[system]):
        raise ValueError(
            "bundled daemon does not have the native executable header for its release platform"
        )


def verify_client(
    root: Path,
    service: str,
    entry: dict[str, Any],
    identity: dict[str, Any],
    capture_paths: set[Path],
) -> None:
    client, policy, runtime = (entry[key] for key in ("client_test", "policy", "runtime"))
    receipt_path = bound_evidence_file(
        root, client["evidence_file"], client["evidence_sha256"], "client receipt"
    )
    receipt = read_capture_json(receipt_path, "client receipt")
    argv = receipt.get("argv")
    endpoint = receipt.get("endpoint")
    bind_host = policy.get("host")
    if (
        receipt.get("schema") != CLIENT_CAPTURE_SCHEMA
        or receipt.get("service") != service
        or receipt.get("runtime_sha256") != runtime["sha256"]
        or receipt.get("release_asset_sha256") != identity["tested_release_asset"]["sha256"]
        or receipt.get("source_head_sha") != identity["source_head_sha"]
        or receipt.get("workflow_run_url") != identity["workflow_run_url"]
        or type(receipt.get("run_attempt")) is not int
        or receipt["run_attempt"] != identity["run_attempt"]
        or not isinstance(endpoint, dict)
        or not isinstance(bind_host, str)
        or bind_host not in ("0.0.0.0", "::", endpoint.get("host"))
        or type(endpoint.get("port")) is not int
        or endpoint.get("port") != policy.get("port")
        or not isinstance(endpoint.get("host"), str)
        or not endpoint["host"]
        or not 1 <= endpoint["port"] <= 65535
        or type(receipt.get("exit_code")) is not int
        or receipt["exit_code"] != 0
        or not isinstance(argv, list)
        or len(argv) < 2
        or not all(isinstance(arg, str) and arg and "\0" not in arg for arg in argv)
        or PurePosixPath(argv[0].replace("\\", "/")).name.lower().removesuffix(".exe")
        not in CLIENTS[service]
        or client["command"] != shlex.join(argv)
    ):
        raise ValueError(
            "client receipt must bind a successful protocol client, endpoint, bundled daemon and tested package"
        )
    capture = asset(root, receipt.get("capture"), "client data capture")
    if capture == receipt_path or capture in capture_paths:
        raise ValueError("each service requires its own client data capture")
    capture_paths.add(capture)
    if service == "vnc":
        if capture.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("VNC client screenshot exceeds 16 MiB")
        try:
            image = read_png_rgb(capture, max_pixels=4_194_304)
        except (struct.error, zlib.error) as exc:
            raise ValueError("VNC client screenshot must be a valid PNG") from exc
        if min(image.width, image.height) < 64 or all(
            pixel == image.pixels[0] for pixel in image.pixels
        ):
            raise ValueError(
                "VNC client screenshot must show a visible framebuffer of at least 64 by 64 pixels"
            )
        return
    challenge = asset(root, receipt.get("challenge"), "server challenge data")
    if challenge == capture or challenge == receipt_path:
        raise ValueError("server challenge must be independent of its client capture")
    expected, observed = read_client_data(challenge), read_client_data(capture)
    if len(expected.strip()) < 16:
        raise ValueError("server challenge must contain at least 16 non-padding bytes")
    if service == "telnet":
        if (
            b"login:" not in observed.lower()
            or b"password:" not in observed.lower()
            or expected.strip() not in observed.splitlines()
        ):
            raise ValueError(
                "Telnet transcript must show the login prompts and authenticated command output"
            )
    elif observed != expected:
        raise ValueError("the real client data differs from the server challenge")
    if service == "nfs":
        options = read_client_data(
            asset(root, receipt.get("mount_options"), "NFS client mount options")
        )
        rejection = read_client_data(
            asset(root, receipt.get("rejected_sys_mount"), "NFS sec=sys client rejection")
        )
        option_values = set(options.strip().split()[-1].split(b",")) if options.strip() else set()
        if (
            not {b"sec=krb5p", b"proto=tcp"} <= option_values
            or not {b"vers=4.1", b"vers=4.2", b"vers=4.0", b"vers=4"} & option_values
            or not any(
                message in rejection.lower()
                for message in (
                    b"operation not permitted",
                    b"permission denied",
                    b"access denied",
                    b"wrong security",
                )
            )
        ):
            raise ValueError(
                "NFS capture must show a TCP NFSv4 Kerberos-privacy mount and rejection of sec=sys"
            )


def validate_live_server_release_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobaEmbeddedServerReleaseEvidenceValidation:
    root = (assets_dir if assets_dir is not None else evidence_path.parent).absolute()
    summary: dict[str, Any] = {"live_client_proof_count": 0}
    try:
        relative = evidence_path.absolute().relative_to(root).as_posix()
        path, error = secure_regular_file(root, relative, "server release evidence")
        if path is None:
            raise ValueError(error)
        evidence = read_capture_json(path, "server release evidence")
        summary.update(capture_release_identity(evidence, "embedded server evidence"))
        manifest_path = asset(root, evidence.get("runtime_manifest"), "runtime manifest")
        manifest = read_capture_json(manifest_path, "runtime manifest")
        target, system = evidence.get("release_target"), manifest.get("system")
        if (
            manifest.get("schema") != SERVER_RUNTIME_BUNDLE_SCHEMA
            or manifest.get("release_target") != target
            or not isinstance(system, str)
            or system not in PLATFORM_PREFIXES
            or not isinstance(target, str)
            or not target.startswith(PLATFORM_PREFIXES[system])
        ):
            raise ValueError("runtime manifest must match the release target and native platform")
        entries = service_inventory(evidence.get("services"), "release evidence")
        runtimes = service_inventory(manifest.get("services"), "runtime manifest")
        if "debian_notices" in manifest:
            if system != "linux":
                raise ValueError("Debian server notice evidence requires a Linux target")
            verify_debian_notice_inputs(manifest_path.parent, manifest["debian_notices"])
        if "openssh_helpers" in manifest:
            if system != "linux":
                raise ValueError("package-owned OpenSSH helper evidence requires a Linux target")
            verify_packaged_openssh_helpers(manifest_path.parent, manifest["openssh_helpers"])
        capture_paths: set[Path] = set()
        for service, entry in entries.items():
            try:
                verify_runtime(
                    root, manifest_path, system, entry["runtime"], runtimes[service].get("runtime")
                )
                verify_client(root, service, entry, summary, capture_paths)
            except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
                raise ValueError(f"{service} live evidence: {exc}") from exc
            summary["live_client_proof_count"] += 1
    except (OSError, ValueError) as exc:
        return MobaEmbeddedServerReleaseEvidenceValidation(
            str(evidence_path), str(root), False, [str(exc)], [], summary
        )
    result = validate_moba_server_release_evidence(evidence_path, assets_dir=root)
    result.summary.update(summary)
    return result


def verify_packaged_debian_server_evidence(package: Path, root: Path, target: str) -> None:
    evidence = read_capture_json(root / "evidence.json", "server release evidence")
    source = evidence.get("source")
    if not isinstance(source, dict) or source.get("release_tag") != f"v{release_deb_version(package.name, target)}":
        raise ValueError("the Debian server package must match the reviewed release tag")
    manifest = asset(root, evidence.get("runtime_manifest"), "reviewed server runtime manifest")
    verify_debian_payload(package, manifest, target)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify MobaXterm-style embedded server release evidence."
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = validate_live_server_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba server release evidence passed")
    else:
        for error in result.errors:
            print(f"moba server release evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

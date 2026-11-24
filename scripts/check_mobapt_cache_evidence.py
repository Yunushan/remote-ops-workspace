from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for location in (ROOT, SRC):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.command_safety import argv_list  # noqa: E402
from remote_ops_workspace.moba_mobapt import (  # noqa: E402
    MobAptCacheEvidenceValidation,
    validate_mobapt_cache_evidence,
)
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    read_json_object,
    secure_regular_file,
)
from scripts.debian_release_fixture import (  # noqa: E402
    ROW_EXECUTABLE,
    release_deb_version,
    validate_native_debian_probe,
)

EXECUTION_SCHEMA = "row.mobapt.offline-execution.v1"
NATIVE_PROBE_SCHEMA = "row.mobapt.native-cache-verify.v1"
NATIVE_PROBE_PATH = "evidence/row-native-cache-verify.json"
NATIVE_PROBE_ARGV = [
    "/usr/bin/row", "mobapt", "cache-verify", "--evidence", "evidence.json", "--assets-dir", ".", "--json",
]


def check_runtime_and_cache(root: Path, data: dict[str, Any]) -> tuple[set[str], dict[str, dict[str, Any]]]:
    runtime, cache = data["runtime"], data["package_cache"]
    manifest = bound_evidence_file(root, runtime["manifest"], runtime["manifest_sha256"], "runtime manifest")
    index = bound_evidence_file(root, cache["index"], cache["index_sha256"], "package index")
    _, manifest_data = read_json_object(manifest, "runtime manifest")
    _, index_data = read_json_object(index, "package index")
    rows = cache["packages"]
    if (index_data.get("schema") != "row.mobapt.package-index.v1"
            or manifest_data.get("packages") != rows or index_data.get("packages") != rows):
        raise ValueError("runtime manifest, package index, and evidence must list the same packages")
    runtime_metadata = index_data.get("runtime")
    if not isinstance(runtime_metadata, dict) or runtime_metadata.get("release_target") != data["release_target"]:
        raise ValueError("package index release target must match the evidence")
    packages = {item["name"]: item for item in rows}
    if len(packages) != len(rows):
        raise ValueError("release cache package names must be unique")
    for row in rows:
        if row.get("synthetic") is not False or row.get("source") != "supplied":
            raise ValueError("release evidence requires real supplied package archives")
        bound_evidence_file(root, row["archive"], row["sha256"], "offline package archive")

    runtime_info = manifest_data.get("runtime")
    binaries = runtime_info.get("binaries") if isinstance(runtime_info, dict) else None
    if not isinstance(binaries, list) or not binaries:
        raise ValueError("release evidence requires at least one bundled runtime executable")
    paths: set[str] = set()
    for binary in binaries:
        if (not isinstance(binary, dict) or binary.get("shim") is not False
                or binary.get("source") not in ("supplied", "host-path")):
            raise ValueError("release evidence requires real runtime binaries without shims")
        path = binary.get("path")
        bound_evidence_file(root, path, binary.get("sha256"), "bundled runtime executable")
        paths.add(path)
    if len(paths) != len(binaries):
        raise ValueError("bundled runtime executable paths must be unique")
    return paths, packages


def native_install_argv(package: str) -> list[str]:
    return [ROW_EXECUTABLE, "mobapt", "install", package, "--offline", "--execute", "--json"]


def check_native_install_output(stdout: str, package: dict[str, Any]) -> None:
    try:
        result = json.loads(stdout)
        plan = result["plan"]
        command = plan["command"]
        archive = PurePosixPath(command[-1])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("native MobApt install receipt requires a JSON execution result") from exc
    relative = PurePosixPath(package["archive"])
    if (
        result.get("executed") is not True or result.get("ok") is not True
        or type(result.get("returncode")) is not int or result["returncode"] != 0
        or plan.get("action") != "install" or plan.get("package") != package["name"]
        or plan.get("cached_package_version") != package["version"]
        or plan.get("cached_archive_sha256") != package["sha256"]
        or command[:-1] != [
            "/usr/bin/apt", "-o", "Dir::Etc::sourcelist=", "-o", "Dir::Etc::sourceparts=", "install", "--",
        ]
        or not archive.is_absolute() or archive.parts[-len(relative.parts):] != relative.parts
    ):
        raise ValueError("native MobApt install receipt must show an executed offline install of the verified package")


def execution_receipt(
    root: Path, test: dict[str, Any], kind: str, runtime_sha: str, archive_sha: str,
) -> dict[str, Any]:
    proof = bound_evidence_file(root, test["evidence_file"], test["evidence_sha256"], f"{kind} receipt")
    try:
        _, receipt = read_json_object(proof, f"{kind} receipt")
    except ValueError as exc:
        raise ValueError(f"{kind} receipt must be structured offline execution evidence") from exc
    if (receipt.get("schema") != EXECUTION_SCHEMA or receipt.get("kind") != kind
            or receipt.get("network_disabled") is not True
            or type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0
            or receipt.get("runtime_manifest_sha256") != runtime_sha
            or receipt.get("package") != test["package"]
            or receipt.get("package_archive_sha256") != archive_sha):
        raise ValueError(f"{kind} receipt must record successful offline execution for the bound runtime and package")
    arguments = receipt.get("argv")
    if not isinstance(arguments, list) or not arguments or not all(isinstance(value, str) for value in arguments):
        raise ValueError(f"{kind} receipt requires the executed argument list")
    argv_list(arguments, f"{kind} receipt argv")
    if shlex.join(arguments) != test["command"]:
        raise ValueError(f"{kind} receipt argv differs from the recorded command")
    stdout, stderr = receipt.get("stdout"), receipt.get("stderr")
    if not isinstance(stdout, str) or not isinstance(stderr, str) or (kind == "terminal-probe" and not stdout.strip()):
        raise ValueError(f"{kind} receipt requires captured output")
    return receipt


def validate_mobapt_cache_execution(
    evidence_path: Path, *, assets_dir: Path | None, require_release_source: bool,
) -> MobAptCacheEvidenceValidation:
    root = assets_dir if assets_dir is not None else evidence_path.parent
    try:
        relative = evidence_path.absolute().relative_to(root.absolute()).as_posix()
        evidence_file, error = secure_regular_file(root, relative, "release cache evidence")
        if evidence_file is None:
            raise ValueError(error)
        result = validate_mobapt_cache_evidence(evidence_file, assets_dir=root)
        if not result.passed:
            return result
        _, data = read_json_object(evidence_file, "release cache evidence")
        paths, packages = check_runtime_and_cache(root, data)
        runtime_sha = data["runtime"]["manifest_sha256"]
        installs = {record["package"]: record for record in data["install_tests"]}
        if installs.keys() != packages.keys() or len(installs) != len(data["install_tests"]):
            raise ValueError("each cached package requires one offline installation receipt")
        for name, record in installs.items():
            package = packages[name]
            receipt = execution_receipt(root, record, "offline-install", runtime_sha, package["sha256"])
            if receipt["argv"] == native_install_argv(name):
                check_native_install_output(receipt["stdout"], package)
            elif "release_asset" in data:
                raise ValueError("native Debian evidence requires installation through the installed row command")
            elif package["archive"] not in receipt["argv"]:
                raise ValueError("offline install receipt argv must name the verified package archive")
        terminal = data["terminal_probe"]
        name = terminal.get("package")
        if not isinstance(name, str) or name not in packages:
            raise ValueError("terminal probe must name a verified installed package")
        receipt = execution_receipt(root, terminal, "terminal-probe", runtime_sha, packages[name]["sha256"])
        if receipt["argv"][0] not in paths:
            raise ValueError("terminal probe must invoke a verified bundled runtime executable")
        if "release_asset" in data:
            result.summary["tested_release_asset"] = validate_native_debian_probe(
                root, evidence_file, data, result.summary,
                schema=NATIVE_PROBE_SCHEMA, receipt_path=NATIVE_PROBE_PATH, argv=NATIVE_PROBE_ARGV,
            )
        if require_release_source:
            if "tested_release_asset" not in result.summary:
                raise ValueError("strict MobApt evidence requires a native Debian release asset probe")
            identity = capture_release_identity(data, "MobApt release evidence")
            version = release_deb_version(identity["tested_release_asset"]["name"], data["release_target"])
            if identity["release_tag"] != f"v{version}":
                raise ValueError("tested Debian package version must match the exact MobApt release tag")
            result.summary.update(identity)
    except (KeyError, OSError, ValueError) as exc:
        return MobAptCacheEvidenceValidation(str(evidence_path), str(root), False, [str(exc)], [], {})
    result.summary["offline_execution_receipts_verified"] = True
    return result


def validate_mobapt_offline_execution(
    evidence_path: Path, *, assets_dir: Path | None = None,
) -> MobAptCacheEvidenceValidation:
    return validate_mobapt_cache_execution(evidence_path, assets_dir=assets_dir, require_release_source=False)


def validate_mobapt_release_cache_evidence(
    evidence_path: Path, *, assets_dir: Path | None = None,
) -> MobAptCacheEvidenceValidation:
    return validate_mobapt_cache_execution(evidence_path, assets_dir=assets_dir, require_release_source=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify MobApt-style offline package cache release evidence.")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--local-execution", action="store_true", help="qualify offline execution without release identity")
    args = parser.parse_args()

    validator = validate_mobapt_offline_execution if args.local_execution else validate_mobapt_release_cache_evidence
    result = validator(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("mobapt cache evidence passed")
    else:
        for error in result.errors:
            print(f"mobapt cache evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

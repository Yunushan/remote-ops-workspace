"""Install and verify the exact Debian release asset used by a parity capture."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from tempfile import TemporaryFile
from typing import Any

from scripts.check_release_license_compliance import (
    read_json_object,
    secure_regular_file,
    sha256_file,
    valid_sha256,
)

DEBIAN_TARGETS = {"amd64": "linux-x86_64", "arm64": "linux-arm64", "i386": "linux-i386", "armhf": "linux-armhf"}
PRODUCT_PACKAGE = "remote-ops-workspace"
ROW_EXECUTABLE = "/usr/bin/row"
PROCESS_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "SHELL": "/bin/sh", "TERM": "dumb"}


def unpack_deb_inputs(package: Path, name: str, architecture: str, outputs: dict[str, Path]) -> dict[str, str]:
    fields = subprocess.check_output(
        ["dpkg-deb", "--field", str(package), "Package", "Version", "Architecture"], text=True, timeout=30,
    )
    package_name, version, package_arch = [line.partition(": ")[2] for line in fields.splitlines()]
    if package_name != name or not version or package_arch != architecture:
        raise ValueError(f"expected the Debian {architecture} {name} package")
    with TemporaryFile() as payload:
        subprocess.run(["dpkg-deb", "--fsys-tarfile", str(package)], stdout=payload, check=True, timeout=30)
        payload.seek(0)
        with tarfile.open(fileobj=payload, mode="r:") as archive:
            remaining = dict(outputs)
            for member in archive:
                key = member.name.removeprefix("./")
                if key not in outputs:
                    continue
                if key not in remaining or not member.isfile() or not 0 < member.size <= 4 * 1024 * 1024:
                    raise ValueError(f"invalid Debian package member: {key}")
                with archive.extractfile(member) as stream, remaining.pop(key).open("xb") as destination:
                    shutil.copyfileobj(stream, destination)
            if remaining:
                raise ValueError(f"Debian {name} package lacks {', '.join(remaining)}")
    return {"version": version, "architecture": architecture, "sha256": sha256_file(package)}


def release_deb_version(name: str, target: str) -> str:
    match = re.fullmatch(r"remote-ops-workspace-v(\d+\.\d+\.\d+)-linux-(amd64|arm64|i386|armhf)\.deb", name)
    if match is None or DEBIAN_TARGETS[match[2]] != target:
        raise ValueError("tested release asset must be the native Debian package for the capture target")
    return match[1]


def actions_source(tag: str) -> dict[str, Any] | None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None
    if os.environ.get("GITHUB_REF") != f"refs/tags/{tag}":
        raise ValueError("release capture must run from the tested Debian package's GitHub release tag")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    return {
        "repository": repository, "release_tag": tag, "head_sha": os.environ.get("GITHUB_SHA", ""),
        "workflow_run_url": f"https://github.com/{repository}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        "run_attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
    }


def run_debian_command(
    arguments: list[str], cwd: Path, *, check: bool = True, env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments, cwd=cwd, env=PROCESS_ENV if env is None else env, stdin=subprocess.DEVNULL,
        capture_output=True, encoding="utf-8", errors="replace", timeout=120, check=check,
    )


def install_release_deb(root: Path, installer: Path, target: str) -> tuple[dict[str, str], dict[str, Any] | None]:
    architecture = run_debian_command(["dpkg", "--print-architecture"], root).stdout.strip()
    if DEBIAN_TARGETS.get(architecture) != target:
        raise ValueError(f"Debian architecture {architecture} does not match the capture target")
    version = release_deb_version(installer.name, target)
    source = actions_source(f"v{version}")
    package = installer.resolve(strict=True)
    digest = sha256_file(package)
    row = Path(ROW_EXECUTABLE)
    status = ["dpkg-query", "--show", "--showformat=${Status}\n${Version}", "--", PRODUCT_PACKAGE]
    if row.exists() or row.is_symlink() or run_debian_command(status, root, check=False).returncode != 1:
        raise ValueError("native Debian capture requires a clean image without a preinstalled row command")
    fields = run_debian_command(["dpkg-deb", "--field", str(package), "Package", "Version", "Architecture"], root).stdout
    if fields != f"Package: {PRODUCT_PACKAGE}\nVersion: {version}\nArchitecture: {architecture}\n":
        raise ValueError("tested Debian asset metadata differs from the release package name, version or architecture")
    run_debian_command(["dpkg", "--install", "--", str(package)], root)
    if run_debian_command(status, root).stdout != f"install ok installed\n{version}" or sha256_file(package) != digest:
        raise ValueError("native Debian capture did not install the exact expected release package")
    files = run_debian_command(["dpkg-query", "--listfiles", "--", PRODUCT_PACKAGE], root).stdout.splitlines()
    if not row.is_file() or ROW_EXECUTABLE not in files:
        raise ValueError("installed Debian release package does not own /usr/bin/row")
    return {"name": installer.name, "sha256": digest}, source


def capture_native_debian_probe(
    root: Path, asset: dict[str, str], target: str, *, schema: str, receipt_path: str, argv: list[str],
    env: dict[str, str] | None = None,
) -> None:
    evidence = root / "evidence.json"
    digest = sha256_file(evidence)
    proof = run_debian_command(argv, root, env=env)
    if sha256_file(evidence) != digest:
        raise ValueError("packaged row changed the evidence during verification")
    path = root / receipt_path
    path.write_text(json.dumps({
        "schema": schema, "argv": proof.args, "exit_code": proof.returncode,
        "stderr": proof.stderr, "output": json.loads(proof.stdout),
        "installed_version": release_deb_version(asset["name"], target),
        "evidence_sha256": digest, "release_asset_sha256": asset["sha256"],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_native_debian_probe(
    root: Path, evidence: Path, data: dict[str, Any], expected_summary: dict[str, Any], *,
    schema: str, receipt_path: str, argv: list[str],
) -> dict[str, str]:
    asset = data.get("release_asset")
    if not isinstance(asset, dict) or not isinstance(asset.get("name"), str) or not valid_sha256(asset.get("sha256")):
        raise ValueError("native CLI proof requires a Debian release asset name and SHA-256")
    name, digest = asset["name"], asset["sha256"]
    version = release_deb_version(name, data["release_target"])
    path, error = secure_regular_file(root, receipt_path, "native CLI proof receipt")
    if path is None:
        raise ValueError(error)
    _, receipt = read_json_object(path, "native CLI proof receipt")
    if (
        receipt.get("schema") != schema or receipt.get("argv") != argv
        or type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0
        or receipt.get("release_asset_sha256") != digest or receipt.get("installed_version") != version
        or receipt.get("evidence_sha256") != sha256_file(evidence)
    ):
        raise ValueError("native CLI proof must verify the exact evidence with the installed Debian release asset")
    output = receipt.get("output")
    if (
        not isinstance(output, dict) or output.get("passed") is not True or output.get("errors") != []
        or output.get("summary") != expected_summary or not isinstance(receipt.get("stderr"), str)
    ):
        raise ValueError("native CLI output must match the evidence result")
    return {"name": name, "sha256": digest}

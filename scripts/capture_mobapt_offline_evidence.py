from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_mobapt_cache_evidence import (  # noqa: E402
    DEBIAN_TARGETS,
    EXECUTION_SCHEMA,
    NATIVE_PROBE_ARGV,
    NATIVE_PROBE_PATH,
    NATIVE_PROBE_SCHEMA,
    check_runtime_and_cache,
    release_deb_version,
    validate_mobapt_cache_evidence,
    validate_mobapt_offline_execution,
    validate_mobapt_release_cache_evidence,
)
from scripts.check_release_license_compliance import (  # noqa: E402
    read_json_object,
    secure_regular_file,
    sha256_file,
)
from scripts.isolated_linux_fixture import require_offline_container  # noqa: E402

RUNTIME = "bin/bash"
PRODUCT_PACKAGE = "remote-ops-workspace"
PROCESS_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "SHELL": "/bin/sh", "TERM": "dumb"}


def run(arguments: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments, cwd=cwd, env=PROCESS_ENV, stdin=subprocess.DEVNULL,
        capture_output=True, encoding="utf-8", errors="replace", timeout=120, check=check,
    )


def package_status(root: Path, name: str) -> str | None:
    result = run(["dpkg-query", "--show", "--showformat=${Status}\n${Version}", "--", name], root, check=False)
    if result.returncode == 1:
        return None
    result.check_returncode()
    return result.stdout


def install_packages(root: Path, packages: dict[str, dict[str, Any]]) -> subprocess.CompletedProcess[str]:
    archives = []
    for name, package in packages.items():
        archive = package["archive"]
        if Path(archive).suffix != ".deb":
            raise ValueError(f"{name} must be supplied as a Debian package archive")
        if package_status(root, name) is not None:
            raise ValueError(f"{name} already exists in the container package database")
        expected = f"Package: {name}\nVersion: {package['version']}\n"
        if run(["dpkg-deb", "--field", archive, "Package", "Version"], root).stdout != expected:
            raise ValueError(f"{name} package name or version differs from the cache manifest")
        archives.append(archive)

    result = run(["dpkg", "--install", "--", *archives], root)
    for name, package in packages.items():
        if package_status(root, name) != f"install ok installed\n{package['version']}":
            raise ValueError(f"{name} did not install at the cached version")
    return result


def terminal_probe(root: Path, package: str, executable: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    installed_paths = run(["dpkg-query", "--listfiles", "--", package], root).stdout.splitlines()
    if not Path(executable).is_absolute() or executable not in installed_paths or not Path(executable).is_file():
        raise ValueError(f"terminal probe executable must be installed by {package}")
    argv = [
        RUNTIME, "--noprofile", "--norc", "-c", 'test -t 0 && test -t 1 && exec "$@"',
        "mobapt-terminal-probe", executable, *arguments,
    ]
    captured = run(
        ["script", "--quiet", "--return", "--echo", "never", "--command", f"exec {shlex.join(argv)}", "/dev/null"],
        root,
    )
    if not captured.stdout.strip():
        raise ValueError("terminal probe produced no output")
    return subprocess.CompletedProcess(argv, captured.returncode, captured.stdout, captured.stderr)


def write_json(path: Path, content: dict[str, Any]) -> None:
    path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_receipt(
    root: Path, kind: str, package: dict[str, Any], manifest_sha: str, process: subprocess.CompletedProcess[str],
) -> dict[str, Any]:
    name = package["name"]
    path = root / "evidence" / f"{name}-{kind}.json"
    write_json(path, {
        "schema": EXECUTION_SCHEMA, "kind": kind, "network_disabled": True,
        "package": name, "package_archive_sha256": package["sha256"], "runtime_manifest_sha256": manifest_sha,
        "argv": process.args, "exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
    })
    return {
        "package": name, "command": shlex.join(process.args), "status": "passed",
        "evidence_file": path.relative_to(root).as_posix(), "evidence_sha256": sha256_file(path),
    }


def actions_source(tag: str) -> dict[str, Any] | None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None
    if os.environ.get("GITHUB_REF") != f"refs/tags/{tag}":
        raise ValueError("MobApt release capture must run from the tested Debian package's GitHub release tag")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    return {
        "repository": repository, "release_tag": tag, "head_sha": os.environ.get("GITHUB_SHA", ""),
        "workflow_run_url": f"https://github.com/{repository}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}",
        "run_attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
    }


def capture_native_probe(root: Path, data: dict[str, Any], installer: Path, architecture: str) -> bool:
    version = release_deb_version(installer.name, data["release_target"])
    source = actions_source(f"v{version}")
    package = installer.resolve(strict=True)
    digest = sha256_file(package)
    row = Path(NATIVE_PROBE_ARGV[0])
    if row.exists() or row.is_symlink() or package_status(root, PRODUCT_PACKAGE) is not None:
        raise ValueError("native MobApt probe requires a clean image without a preinstalled row command")
    fields = run(["dpkg-deb", "--field", str(package), "Package", "Version", "Architecture"], root).stdout
    if fields != f"Package: {PRODUCT_PACKAGE}\nVersion: {version}\nArchitecture: {architecture}\n":
        raise ValueError("tested Debian asset metadata differs from the release package name, version or architecture")
    run(["dpkg", "--install", "--", str(package)], root)
    if package_status(root, PRODUCT_PACKAGE) != f"install ok installed\n{version}" or sha256_file(package) != digest:
        raise ValueError("native MobApt installer did not install the exact expected Debian package")
    if str(row) not in run(["dpkg-query", "--listfiles", "--", PRODUCT_PACKAGE], root).stdout.splitlines():
        raise ValueError("installed Debian release package does not own /usr/bin/row")

    data["release_asset"] = {"name": installer.name, "sha256": digest}
    if source is not None:
        data["source"] = source
    evidence = root / "evidence.json"
    write_json(evidence, data)
    evidence_digest = sha256_file(evidence)
    proof = run(NATIVE_PROBE_ARGV, root)
    if sha256_file(evidence) != evidence_digest:
        raise ValueError("packaged row changed the cache evidence during verification")
    write_json(root / NATIVE_PROBE_PATH, {
        "schema": NATIVE_PROBE_SCHEMA, "argv": proof.args, "exit_code": proof.returncode,
        "stderr": proof.stderr, "output": json.loads(proof.stdout), "installed_version": version,
        "evidence_sha256": evidence_digest, "release_asset_sha256": digest,
    })
    return source is not None


def capture(
    bundle: Path, output: Path, package: str, executable: str, arguments: list[str], *, release_deb: Path | None = None,
) -> None:
    require_offline_container()
    evidence, error = secure_regular_file(bundle, "mobapt-cache-evidence.json", "MobApt assembly evidence")
    if evidence is None:
        raise ValueError(error)
    validated = validate_mobapt_cache_evidence(evidence, assets_dir=bundle)
    if not validated.passed:
        raise ValueError(f"invalid MobApt assembly: {validated.errors}")
    _, data = read_json_object(evidence, "MobApt assembly evidence")
    paths, packages = check_runtime_and_cache(bundle, data)
    if RUNTIME not in paths or package not in packages:
        raise ValueError("assembly must include bundled Bash and the selected probe package")
    architecture = run(["dpkg", "--print-architecture"], bundle).stdout.strip()
    if DEBIAN_TARGETS.get(architecture) != data["release_target"]:
        raise ValueError(f"assembly release target does not match Debian architecture {architecture}")
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(bundle.resolve()):
        raise ValueError("output must be a new directory outside the assembly bundle")

    with TemporaryDirectory(prefix=".mobapt-capture-", dir=output.parent) as staging:
        root = Path(staging) / "capture"
        (root / "evidence").mkdir(parents=True)
        files = paths | {item["archive"] for item in packages.values()}
        files.update({data["runtime"]["manifest"], data["package_cache"]["index"]})
        for relative in sorted(files):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundle / relative, target)
        check_runtime_and_cache(root, data)

        installation = install_packages(root, packages)
        terminal = terminal_probe(root, package, executable, arguments)
        manifest_sha = data["runtime"]["manifest_sha256"]
        data["install_tests"] = [
            write_receipt(root, "offline-install", row, manifest_sha, installation) for row in packages.values()
        ]
        data["terminal_probe"] = write_receipt(root, "terminal-probe", packages[package], manifest_sha, terminal)
        validate = validate_mobapt_offline_execution
        if release_deb is None:
            write_json(root / "evidence.json", data)
        elif capture_native_probe(root, data, release_deb, architecture):
            validate = validate_mobapt_release_cache_evidence
        result = validate(root / "evidence.json", assets_dir=root)
        if not result.passed:
            raise ValueError(f"offline execution evidence failed validation: {result.errors}")
        root.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture real offline MobApt package installation and terminal evidence.")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--release-deb", type=Path, help="install and smoke-test the exact Debian release candidate")
    parser.add_argument("--probe-package", required=True)
    parser.add_argument("--probe-executable", required=True)
    parser.add_argument("--probe-arg", action="append", default=[])
    args = parser.parse_args()
    try:
        capture(args.bundle, args.out, args.probe_package, args.probe_executable, args.probe_arg, release_deb=args.release_deb)
    except subprocess.CalledProcessError as exc:
        print(f"MobApt offline capture: {exc}\n{exc.stdout or ''}{exc.stderr or ''}", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"MobApt offline capture: {exc}", file=sys.stderr)
        return 1
    print(f"MobApt offline evidence passed: {args.out / 'evidence.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

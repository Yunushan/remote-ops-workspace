from __future__ import annotations

import argparse
import json
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
    EXECUTION_SCHEMA,
    INSTALLED_CACHE,
    NATIVE_PROBE_ARGV,
    NATIVE_PROBE_PATH,
    NATIVE_PROBE_SCHEMA,
    check_native_install_output,
    check_runtime_and_cache,
    native_install_argv,
    validate_mobapt_cache_evidence,
    validate_mobapt_offline_execution,
    validate_mobapt_release_cache_evidence,
)
from scripts.check_release_license_compliance import (  # noqa: E402
    read_json_object,
    secure_regular_file,
    sha256_file,
)
from scripts.debian_release_fixture import (  # noqa: E402
    DEBIAN_TARGETS,
    PROCESS_ENV,
    PRODUCT_PACKAGE,
    capture_native_debian_probe,
    install_release_deb,
)
from scripts.debian_release_fixture import run_debian_command as run  # noqa: E402
from scripts.isolated_linux_fixture import require_offline_container  # noqa: E402

RUNTIME = "bin/bash"


def package_status(root: Path, name: str) -> str | None:
    result = run(["dpkg-query", "--show", "--showformat=${Status}\n${Version}", "--", name], root, check=False)
    if result.returncode == 1:
        return None
    result.check_returncode()
    return result.stdout


def install_packages(
    root: Path, packages: dict[str, dict[str, Any]], *, native: bool, installed_cache: bool,
) -> dict[str, subprocess.CompletedProcess[str]]:
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

    if native:
        results = {}
        env = dict(PROCESS_ENV)
        if not installed_cache:
            env["ROW_MOBAPT_RUNTIME_DIR"] = str(root.resolve())
        for name, package in packages.items():
            result = run(native_install_argv(name), root, env=env)
            check_native_install_output(result.stdout, package, installed_cache=installed_cache)
            results[name] = result
    else:
        result = run(["dpkg", "--install", "--", *archives], root)
        results = dict.fromkeys(packages, result)
    for name, package in packages.items():
        if package_status(root, name) != f"install ok installed\n{package['version']}":
            raise ValueError(f"{name} did not install at the cached version")
    return results


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


def capture(
    bundle: Path | None, output: Path, package: str, executable: str, arguments: list[str], *,
    release_deb: Path | None = None,
) -> None:
    require_offline_container()
    installed_cache = bundle is None
    if installed_cache and release_deb is None:
        raise ValueError("a Debian release asset is required when no external MobApt bundle is supplied")
    assembly = Path(INSTALLED_CACHE) if bundle is None else bundle
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(assembly.resolve()):
        raise ValueError("output must be a new directory outside the assembly bundle")

    cwd = output.parent.resolve(strict=True)
    architecture = run(["dpkg", "--print-architecture"], cwd).stdout.strip()
    target = DEBIAN_TARGETS.get(architecture)
    if target is None:
        raise ValueError(f"unsupported Debian architecture {architecture}")
    native_release = None
    if installed_cache and release_deb is not None:
        native_release = install_release_deb(cwd, release_deb, target)

    evidence, error = secure_regular_file(assembly, "mobapt-cache-evidence.json", "MobApt assembly evidence")
    if evidence is None:
        raise ValueError(error)
    validated = validate_mobapt_cache_evidence(evidence, assets_dir=assembly)
    if not validated.passed:
        raise ValueError(f"invalid MobApt assembly: {validated.errors}")
    _, data = read_json_object(evidence, "MobApt assembly evidence")
    paths, packages = check_runtime_and_cache(assembly, data)
    if RUNTIME not in paths or package not in packages:
        raise ValueError("assembly must include bundled Bash and the selected probe package")
    if target != data["release_target"]:
        raise ValueError(f"assembly release target does not match Debian architecture {architecture}")
    files = paths | {item["archive"] for item in packages.values()}
    files.update({data["runtime"]["manifest"], data["package_cache"]["index"]})
    if installed_cache:
        owned = set(run(["dpkg-query", "--listfiles", "--", PRODUCT_PACKAGE], cwd).stdout.splitlines())
        required = {str(assembly / name) for name in files} | {str(evidence)}
        if not required <= owned:
            raise ValueError("the tested Debian package must own every MobApt cache input")
        data["installed_cache"] = True

    with TemporaryDirectory(prefix=".mobapt-capture-", dir=output.parent) as staging:
        root = Path(staging) / "capture"
        (root / "evidence").mkdir(parents=True)
        for relative in sorted(files):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(assembly / relative, destination)
        check_runtime_and_cache(root, data)

        if release_deb is not None:
            if native_release is None:
                native_release = install_release_deb(root, release_deb, target)
            asset, source = native_release
            data["release_asset"] = asset
            if source is not None:
                data["source"] = source

        installations = install_packages(
            root, packages, native=release_deb is not None, installed_cache=installed_cache,
        )
        terminal = terminal_probe(root, package, executable, arguments)
        manifest_sha = data["runtime"]["manifest_sha256"]
        data["install_tests"] = [
            write_receipt(root, "offline-install", row, manifest_sha, installations[name])
            for name, row in packages.items()
        ]
        data["terminal_probe"] = write_receipt(root, "terminal-probe", packages[package], manifest_sha, terminal)
        validate = validate_mobapt_offline_execution
        write_json(root / "evidence.json", data)
        if release_deb is not None:
            capture_native_debian_probe(root, asset, target, schema=NATIVE_PROBE_SCHEMA,
                                        receipt_path=NATIVE_PROBE_PATH, argv=NATIVE_PROBE_ARGV)
            if source is not None:
                validate = validate_mobapt_release_cache_evidence
        result = validate(root / "evidence.json", assets_dir=root)
        if not result.passed:
            raise ValueError(f"offline execution evidence failed validation: {result.errors}")
        root.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture real offline MobApt package installation and terminal evidence.")
    parser.add_argument("--bundle", type=Path, help="external assembly for rehearsal; omit to use the installed cache")
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

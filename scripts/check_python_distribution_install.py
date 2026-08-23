from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCHEMA = "row.python-distribution-install-evidence.v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install and smoke the built wheel and sdist in isolated virtual environments."
    )
    parser.add_argument("--dist-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    return parser.parse_args(argv)


def find_distribution_artifacts(dist_dir: Path) -> list[tuple[str, Path]]:
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise ValueError(f"expected exactly one wheel in {dist_dir}, found {len(wheels)}")
    if len(sdists) != 1:
        raise ValueError(f"expected exactly one sdist in {dist_dir}, found {len(sdists)}")
    return [("wheel", wheels[0]), ("sdist", sdists[0])]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def venv_python(environment: Path) -> Path:
    return (
        environment / "Scripts" / "python.exe"
        if os.name == "nt"
        else environment / "bin" / "python"
    )


def stage_distribution_artifact(artifact: Path, root: Path) -> Path:
    """Copy a build artifact into the isolated smoke root.

    Windows build helpers can create output files with a producer-token-only ACL.
    A virtual-environment child process may then be unable to read the original
    path even though the bytes are valid.  Creating a new file under the smoke
    root makes the access boundary deterministic while the result continues to
    hash and report the original artifact.
    """

    staging = root / "artifacts" / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    source = artifact.resolve(strict=True)
    # Wheel and sdist installers parse the basename, so uniqueness belongs in
    # the parent directory rather than being prefixed to the artifact itself.
    staged = staging / source.name
    shutil.copyfile(source, staged)
    return staged


def run_checked(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        tail = "\n".join(output.splitlines()[-20:])
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {' '.join(command)}\n{tail}"
        )
    return result


def project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(r"(?ms)^\[project\]\s*(?P<body>.*?)(?=^\[|\Z)", text)
    version = re.search(
        r'^version\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$',
        project.group("body") if project else "",
        re.MULTILINE,
    )
    if version is None:
        raise ValueError("pyproject.toml [project] table must declare version")
    return version.group("version")


def smoke_distribution(
    kind: str,
    artifact: Path,
    *,
    expected_version: str,
    timeout_seconds: int,
    root: Path,
) -> dict[str, Any]:
    environment = root / kind
    staged_artifact = stage_distribution_artifact(artifact, root)
    command_env = os.environ.copy()
    command_env.pop("PYTHONPATH", None)
    command_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    command_env["PIP_NO_CACHE_DIR"] = "1"
    command_env["ROW_HOME"] = str(root / f"{kind}-row-home")
    run_checked(
        [sys.executable, "-m", "venv", str(environment)],
        cwd=ROOT,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    python = venv_python(environment)

    run_checked(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-cache-dir",
            str(staged_artifact.resolve()),
        ],
        cwd=root,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    run_checked(
        [str(python), "-m", "pip", "check"],
        cwd=root,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    probe_source = (
        "import importlib.metadata as metadata, json, pathlib, platform, sys; "
        "import remote_ops_workspace as package; "
        "from remote_ops_workspace.features import feature_manifest_path; "
        "from remote_ops_workspace.paths import runtime_web_dir; "
        "manifest = feature_manifest_path(); web = runtime_web_dir(); "
        "assert manifest.is_file(), manifest; assert web.is_dir(), web; "
        "print(json.dumps({'distribution_version': metadata.version('remote-ops-workspace'), "
        "'package_version': package.__version__, 'python_version': platform.python_version(), "
        "'releaselevel': sys.version_info.releaselevel, "
        "'feature_manifest': str(manifest), 'web_dir': str(web)}, sort_keys=True))"
    )
    probe = run_checked(
        [str(python), "-I", "-c", probe_source],
        cwd=root,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    probe_payload = json.loads(probe.stdout.strip())
    for key in ("distribution_version", "package_version"):
        if probe_payload.get(key) != expected_version:
            raise RuntimeError(
                f"{kind} installed {key}={probe_payload.get(key)!r}, expected {expected_version!r}"
            )
    feature_smoke = run_checked(
        [
            str(python),
            "-I",
            "-m",
            "remote_ops_workspace",
            "features",
            "--coverage",
            "--json",
        ],
        cwd=root,
        env=command_env,
        timeout_seconds=timeout_seconds,
    )
    coverage_payload = json.loads(feature_smoke.stdout)
    required_sections = {
        "adapter_ready_coverage",
        "evidence_summary",
        "feature_family_mapping",
        "platform_verified_readiness",
        "production_parity_coverage",
    }
    missing_sections = sorted(required_sections - set(coverage_payload))
    if missing_sections:
        raise RuntimeError(
            f"{kind} feature coverage smoke missing sections: {', '.join(missing_sections)}"
        )
    return {
        "kind": kind,
        "filename": artifact.name,
        "bytes": artifact.stat().st_size,
        "sha256": sha256_file(artifact),
        "probe": probe_payload,
        "feature_coverage_sha256": hashlib.sha256(
            feature_smoke.stdout.encode("utf-8")
        ).hexdigest(),
        "passed": True,
    }


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    expected_version = project_version()
    results: list[dict[str, Any]] = []
    try:
        artifacts = find_distribution_artifacts(args.dist_dir)
        temporary_parent = ROOT / ".tmp"
        temporary_parent.mkdir(parents=True, exist_ok=True)
        root = temporary_parent / f"row-python-dist-smoke-{uuid.uuid4().hex}"
        try:
            for kind, artifact in artifacts:
                results.append(
                    smoke_distribution(
                        kind,
                        artifact,
                        expected_version=expected_version,
                        timeout_seconds=args.timeout_seconds,
                        root=root,
                    )
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)
        payload = {
            "schema": EVIDENCE_SCHEMA,
            "expected_project_version": expected_version,
            "producer_python": {
                "executable": sys.executable,
                "version": sys.version,
            },
            "artifacts": results,
            "passed": True,
        }
        write_evidence(args.out, payload)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        payload = {
            "schema": EVIDENCE_SCHEMA,
            "expected_project_version": expected_version,
            "artifacts": results,
            "passed": False,
            "error": str(exc),
        }
        write_evidence(args.out, payload)
        print(f"Python distribution install: {exc}", file=sys.stderr)
        return 1
    print(
        "Python distribution install passed: "
        + ", ".join(result["filename"] for result in results)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

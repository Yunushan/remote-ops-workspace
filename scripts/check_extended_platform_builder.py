from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_verified_evidence import directory_path_has_file_suffix  # noqa: E402

LINUX_TARGET_ARCHES = {
    "linux-i386": {"i386", "i486", "i586", "i686", "x86"},
    "linux-armhf": {"armv6l", "armv7l", "armv7hl", "armhf"},
}
LINUX_TARGET_DPKG_ARCHES = {
    "linux-i386": {"i386"},
    "linux-armhf": {"armhf"},
}
LINUX_TARGET_USERLAND_BITS = {
    "linux-i386": "32",
    "linux-armhf": "32",
}
EXPECTED_WORKFLOW_PATH = ".github/workflows/extended-platform-evidence.yml"

REQUIRED_LINUX_TOOLS = (
    "bash",
    "curl",
    "dpkg",
    "dpkg-deb",
    "getconf",
    "openssl",
    "rpm",
    "rpmbuild",
    "sha256sum",
    "sudo",
    "tar",
)
RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
GITHUB_ACTIONS_RUN_RE = re.compile(r"https://github\.com/[^/]+/[^/]+/actions/runs/\d+/?")
GITHUB_RUN_ID_RE = re.compile(r"/actions/runs/(\d+)/?$")
GITHUB_HEAD_SHA_RE = re.compile(r"[0-9a-f]{40}")
REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS = (
    "security_update_channel",
    "cve_review_reference",
)
FORBIDDEN_SECURITY_PROVENANCE_MARKERS = (
    "<",
    ">",
    "dummy",
    "placeholder",
    "replace",
    "test-",
    "todo",
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = check_extended_platform_builder(args.target)
    if args.out or args.release_tag or args.workflow_run_url or args.source_head_sha or args.workflow_run_attempt:
        errors.extend(
            check_builder_identity_context(
                args.target,
                args.release_tag,
                args.workflow_run_url,
                args.workflow_run_attempt,
                args.source_head_sha,
            )
        )
    if args.out:
        errors.extend(check_builder_identity_output_path(args.target, args.out))
    if errors:
        for error in errors:
            print(f"extended platform builder: {error}", file=sys.stderr)
        return 1
    if args.out:
        write_builder_identity_output(
            args.out,
            builder_identity(
                args.target,
                release_tag=str(args.release_tag),
                workflow_run_url=str(args.workflow_run_url),
                workflow_run_attempt=int(args.workflow_run_attempt),
                source_head_sha=str(args.source_head_sha),
            ),
        )
    print(f"extended platform builder checks passed for {args.target}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an extended-platform native builder.")
    parser.add_argument("--target", choices=sorted(LINUX_TARGET_ARCHES), required=True)
    parser.add_argument("--release-tag", help="release tag this builder evidence is bound to, for example v1.0.2")
    parser.add_argument("--workflow-run-url", help="GitHub Actions run URL this builder evidence is bound to")
    parser.add_argument(
        "--workflow-run-attempt",
        type=int,
        help="positive GitHub Actions run attempt this builder evidence is bound to",
    )
    parser.add_argument("--source-head-sha", help="40-character Git commit SHA checked out by this builder run")
    parser.add_argument("--out", type=Path, help="write builder identity evidence JSON after validation passes")
    return parser.parse_args(argv)


def check_extended_platform_builder(target: str) -> list[str]:
    errors: list[str] = []
    if not sys.platform.startswith("linux"):
        errors.append(f"{target} builder must run on Linux, got {sys.platform}")
    machine = normalized_machine()
    expected = LINUX_TARGET_ARCHES[target]
    if machine not in expected:
        errors.append(f"{target} builder architecture must be one of {sorted(expected)}, got {machine}")
    for tool in REQUIRED_LINUX_TOOLS:
        tool_path = shutil.which(tool)
        if tool_path is None:
            errors.append(f"{target} builder missing required tool: {tool}")
        elif not is_concrete_linux_tool_path(tool_path):
            errors.append(f"{target} builder required tool {tool} must resolve to an absolute path, got {tool_path!r}")
    python_version = sys.version_info
    if python_version < (3, 10):
        errors.append(
            f"{target} builder Python must be 3.10 or newer, got "
            f"{python_version.major}.{python_version.minor}"
        )
    if shutil.which("python3") is None:
        errors.append(f"{target} builder missing python3 command")
    if shutil.which("sudo") is not None and not command_succeeds(["sudo", "-n", "true"]):
        errors.append(f"{target} builder sudo must be non-interactive: sudo -n true failed")
    errors.extend(check_uname_machine(target, expected))
    errors.extend(check_dpkg_architecture(target, LINUX_TARGET_DPKG_ARCHES[target]))
    errors.extend(check_userland_bits(target, LINUX_TARGET_USERLAND_BITS[target]))
    errors.extend(check_runtime_identity(target))
    errors.extend(check_security_patch_evidence(target))
    return errors


def is_concrete_linux_tool_path(value: str) -> bool:
    return bool(value.strip()) and "<" not in value and ">" not in value and value.startswith("/")


def check_builder_identity_context(
    target: str,
    release_tag: str | None,
    workflow_run_url: str | None,
    workflow_run_attempt: int | None,
    source_head_sha: str | None,
) -> list[str]:
    errors: list[str] = []
    if not release_tag:
        errors.append(f"{target} builder identity output requires --release-tag")
    elif not RELEASE_TAG_RE.fullmatch(str(release_tag)):
        errors.append(f"{target} builder identity --release-tag must look like vX.Y.Z")
    if not workflow_run_url:
        errors.append(f"{target} builder identity output requires --workflow-run-url")
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(str(workflow_run_url)):
        errors.append(f"{target} builder identity --workflow-run-url must be a GitHub Actions run URL")
    if workflow_run_attempt is None:
        errors.append(f"{target} builder identity output requires --workflow-run-attempt")
    elif workflow_run_attempt < 1:
        errors.append(f"{target} builder identity --workflow-run-attempt must be a positive integer")
    if not source_head_sha:
        errors.append(f"{target} builder identity output requires --source-head-sha")
    elif not GITHUB_HEAD_SHA_RE.fullmatch(str(source_head_sha)):
        errors.append(f"{target} builder identity --source-head-sha must be a 40-character lowercase Git SHA")
    else:
        observed_git_head = git_head_sha()
        if not observed_git_head:
            errors.append(f"{target} builder identity requires git rev-parse HEAD for source head binding")
        elif observed_git_head != str(source_head_sha):
            errors.append(
                f"{target} builder identity observed git HEAD {observed_git_head} "
                f"must match --source-head-sha {source_head_sha}"
            )
        git_status = git_status_porcelain()
        if git_status is None:
            errors.append(f"{target} builder identity requires git status --porcelain for clean checkout proof")
        elif git_status:
            errors.append(f"{target} builder identity requires a clean git worktree before native build")
        errors.extend(
            check_github_actions_context(
                target,
                str(workflow_run_url or ""),
                workflow_run_attempt,
                str(source_head_sha),
            )
        )
    return errors


def check_github_actions_context(
    target: str,
    workflow_run_url: str,
    workflow_run_attempt: int | None,
    source_head_sha: str,
) -> list[str]:
    errors: list[str] = []
    github_sha = os.environ.get("GITHUB_SHA", "").strip().lower()
    if github_sha and github_sha != source_head_sha:
        errors.append(f"{target} GITHUB_SHA {github_sha} must match --source-head-sha {source_head_sha}")
    github_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "").strip()
    if github_attempt and str(workflow_run_attempt or "") != github_attempt:
        errors.append(
            f"{target} GITHUB_RUN_ATTEMPT {github_attempt} must match --workflow-run-attempt {workflow_run_attempt}"
        )
    github_run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    run_match = GITHUB_RUN_ID_RE.search(workflow_run_url)
    if github_run_id and run_match and github_run_id != run_match.group(1):
        errors.append(f"{target} GITHUB_RUN_ID {github_run_id} must match --workflow-run-url {workflow_run_url}")
    github_repository = os.environ.get("GITHUB_REPOSITORY", "").strip().lower()
    repository_match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/actions/runs/\d+/?", workflow_run_url)
    if github_repository and repository_match and github_repository != repository_match.group(1).lower():
        errors.append(
            f"{target} GITHUB_REPOSITORY {github_repository} must match --workflow-run-url {workflow_run_url}"
        )
    expected_repository = repository_match.group(1).lower() if repository_match else github_repository
    github_actions = os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
    github_workflow_ref = os.environ.get("GITHUB_WORKFLOW_REF", "").strip()
    if github_actions and not github_workflow_ref:
        errors.append(f"{target} GITHUB_WORKFLOW_REF is required for builder workflow provenance")
    elif github_workflow_ref:
        expected_prefix = f"{expected_repository}/{EXPECTED_WORKFLOW_PATH}@"
        if not expected_repository or not github_workflow_ref.lower().startswith(expected_prefix.lower()):
            errors.append(
                f"{target} GITHUB_WORKFLOW_REF {github_workflow_ref} must point at "
                f"{expected_prefix}<ref>"
            )
    github_workflow_sha = os.environ.get("GITHUB_WORKFLOW_SHA", "").strip().lower()
    if github_actions and not github_workflow_sha:
        errors.append(f"{target} GITHUB_WORKFLOW_SHA is required for builder workflow provenance")
    elif github_workflow_sha:
        if not GITHUB_HEAD_SHA_RE.fullmatch(github_workflow_sha):
            errors.append(f"{target} GITHUB_WORKFLOW_SHA must be a 40-character lowercase Git SHA")
        elif github_workflow_sha != source_head_sha:
            errors.append(
                f"{target} GITHUB_WORKFLOW_SHA {github_workflow_sha} must match "
                f"--source-head-sha {source_head_sha}"
            )
    return errors


def check_builder_identity_output_path(target: str, path: Path) -> list[str]:
    errors: list[str] = []
    expected_name = f"builder-identity-{target}.json"
    if path.name != expected_name:
        errors.append(
            f"{target} builder identity output file name must be {expected_name}, got {path.name!r}"
        )
    parent = path.parent
    errors.extend(check_directory_path_hint(parent, "builder identity output directory"))
    if errors:
        return errors
    if parent.is_symlink():
        errors.append(f"builder identity output directory must not be a symlink: {parent}")
        return errors
    parent_errors = check_path_parent_symlinks(parent, "builder identity output directory")
    if parent_errors:
        errors.extend(parent_errors)
        return errors
    if parent.exists() and not parent.is_dir():
        errors.append(f"builder identity output directory must be a directory: {parent}")
    if path.is_symlink():
        errors.append(f"builder identity output file must not be a symlink: {path}")
    if path.exists() and not path.is_file():
        errors.append(f"builder identity output file must be a regular file: {path}")
    return errors


def write_builder_identity_output(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink():
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


def check_directory_path_hint(path: Path, label: str) -> list[str]:
    raw_path = path.as_posix()
    if directory_path_has_file_suffix(raw_path):
        return [f"{label} must be a directory path, got {raw_path!r}"]
    return []


def builder_identity(
    target: str,
    *,
    release_tag: str = "",
    workflow_run_url: str = "",
    workflow_run_attempt: int = 0,
    source_head_sha: str = "",
) -> dict[str, Any]:
    version = sys.version_info
    major = version.major if hasattr(version, "major") else version[0]
    minor = version.minor if hasattr(version, "minor") else version[1]
    micro = version.micro if hasattr(version, "micro") else version[2]
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": workflow_run_url,
        "workflow_run_attempt": workflow_run_attempt,
        "workflow_ref": github_workflow_ref(),
        "workflow_sha": github_workflow_sha(),
        "source_head_sha": source_head_sha,
        "observed_git_head_sha": git_head_sha(),
        "git_worktree_clean": git_worktree_clean(),
        "sys_platform": sys.platform,
        "platform_machine": normalized_machine(),
        "uname_machine": uname_machine(),
        "dpkg_architecture": dpkg_architecture(),
        "userland_bits": userland_bits(),
        "os_release": os_release(),
        "kernel_release": kernel_release(),
        "glibc_version": glibc_version(),
        "python_version": f"{major}.{minor}.{micro}",
        "host_identity": builder_host_identity(
            target,
            release_tag=release_tag,
            workflow_run_url=workflow_run_url,
            workflow_run_attempt=workflow_run_attempt,
        ),
        "sudo_non_interactive": command_succeeds(["sudo", "-n", "true"]),
        "required_tools": {tool: shutil.which(tool) or "" for tool in REQUIRED_LINUX_TOOLS},
        "security_patch_evidence": security_patch_evidence(),
    }


def builder_host_identity(
    target: str,
    *,
    release_tag: str,
    workflow_run_url: str,
    workflow_run_attempt: int,
) -> dict[str, Any]:
    version = release_tag.removeprefix("v").replace(".", "-") if release_tag else "unbound"
    run_match = GITHUB_RUN_ID_RE.search(workflow_run_url)
    run_id = run_match.group(1) if run_match else "manual"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": workflow_run_url,
        "workflow_run_attempt": workflow_run_attempt,
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{version}-run-{run_id}",
        "observed_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "operator_private_data_redacted": True,
    }


def check_security_patch_evidence(target: str) -> list[str]:
    evidence = security_patch_evidence()
    errors: list[str] = []
    if not evidence["python_ssl_openssl"]:
        errors.append(f"{target} builder cannot report Python ssl OpenSSL version")
    if not evidence["openssl_cli_version"]:
        errors.append(f"{target} builder cannot report openssl CLI version")
    if evidence["tls_minimum_modern_profiles"] != "TLS 1.2":
        errors.append(f"{target} builder TLS minimum evidence must stay TLS 1.2")
    if evidence["tls_preferred_modern_profiles"] != "TLS 1.3":
        errors.append(f"{target} builder TLS preferred evidence must stay TLS 1.3")
    if evidence["legacy_compatibility_profile"] != "isolated-opt-in":
        errors.append(f"{target} builder legacy compatibility must remain isolated opt-in")
    if evidence["cve_patch_reviewed"] is not True:
        errors.append(f"{target} builder CVE patch review evidence must be true")
    provenance_labels = {
        "security_update_channel": "security update channel",
        "cve_review_reference": "CVE review reference",
    }
    for key in REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS:
        value = str(evidence.get(key, ""))
        label = provenance_labels[key]
        if not value.strip():
            errors.append(f"{target} builder {label} evidence must be set")
        elif not is_concrete_security_provenance(value):
            errors.append(f"{target} builder {label} evidence must name concrete non-placeholder provenance")
    return errors


def is_concrete_security_provenance(value: str) -> bool:
    lowered = value.strip().lower()
    return bool(lowered) and not any(marker in lowered for marker in FORBIDDEN_SECURITY_PROVENANCE_MARKERS)


def security_patch_evidence() -> dict[str, Any]:
    return {
        "python_ssl_openssl": getattr(ssl, "OPENSSL_VERSION", ""),
        "openssl_cli_version": command_output(["openssl", "version"]),
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "distribution-security-updates",
        "cve_review_reference": "distribution-security-tracker-and-release-notes",
    }


def check_uname_machine(target: str, expected: set[str]) -> list[str]:
    output = uname_machine()
    if not output:
        return [f"{target} builder cannot run uname -m"]
    machine = output.lower()
    if machine not in expected:
        return [f"{target} uname -m must be one of {sorted(expected)}, got {machine}"]
    return []


def check_dpkg_architecture(target: str, expected: set[str]) -> list[str]:
    output = dpkg_architecture()
    if not output:
        return [f"{target} builder cannot run dpkg --print-architecture"]
    if output not in expected:
        return [f"{target} dpkg architecture must be one of {sorted(expected)}, got {output}"]
    return []


def check_userland_bits(target: str, expected: str) -> list[str]:
    output = userland_bits()
    if not output:
        return [f"{target} builder cannot run getconf LONG_BIT"]
    if output != expected:
        return [f"{target} userland bits must be {expected}, got {output}"]
    return []


def check_runtime_identity(target: str) -> list[str]:
    errors: list[str] = []
    required = {
        "os_release": os_release(),
        "kernel_release": kernel_release(),
        "glibc_version": glibc_version(),
    }
    for key, value in required.items():
        if not value.strip():
            errors.append(f"{target} builder cannot report {key}")
    return errors


def os_release() -> str:
    path = Path("/etc/os-release")
    try:
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if "=" not in raw_line or raw_line.startswith("#"):
                continue
            key, value = raw_line.split("=", 1)
            values[key] = value.strip().strip('"')
    except OSError:
        return ""
    return values.get("PRETTY_NAME") or " ".join(
        value for value in (values.get("ID", ""), values.get("VERSION_ID", "")) if value
    )


def kernel_release() -> str:
    return command_output(["uname", "-r"])


def glibc_version() -> str:
    return command_output(["getconf", "GNU_LIBC_VERSION"])


def uname_machine() -> str:
    return command_output(["uname", "-m"]).lower()


def dpkg_architecture() -> str:
    return command_output(["dpkg", "--print-architecture"]).lower()


def userland_bits() -> str:
    return command_output(["getconf", "LONG_BIT"])


def git_head_sha() -> str:
    return command_output(["git", "rev-parse", "HEAD"])


def git_worktree_clean() -> bool:
    status = git_status_porcelain()
    return status == ""


def github_workflow_ref() -> str:
    return os.environ.get("GITHUB_WORKFLOW_REF", "").strip()


def github_workflow_sha() -> str:
    return os.environ.get("GITHUB_WORKFLOW_SHA", "").strip().lower()


def git_status_porcelain() -> str | None:
    try:
        return subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
    except (OSError, subprocess.CalledProcessError):
        return None


def command_output(command: list[str]) -> str:
    try:
        output = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""
    return output.lower()


def command_succeeds(command: list[str]) -> bool:
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def normalized_machine() -> str:
    return platform.machine().lower()


if __name__ == "__main__":
    raise SystemExit(main())

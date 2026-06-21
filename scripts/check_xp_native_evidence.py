from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from check_platform_promotion_artifacts import (  # noqa: E402
    check_platform_promotion_artifacts,
    expand_version,
    promotion_entries,
    required_artifacts,
    version_from_tag,
)
from check_platform_promotion_artifacts import (  # noqa: E402
    read_json as read_promotion_json,
)

CONTRACT_PATH = ROOT / "configs" / "xp_native_evidence_contract.json"
PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
PROMOTION_TARGETS = {"windows-xp-native-x86", "windows-xp-native-x64"}
REQUIRED_FORBIDDEN_EVIDENCE_PATTERNS = {
    "TODO",
    "placeholder",
    "replace with real",
    "template evidence",
    "<artifact-dir>",
    "<evidence-dir>",
    "<evidence.json>",
    "<replace-with-real-sha256>",
    "BEGIN PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
    "password=",
    "passwd=",
    "secret=",
    "token=",
}
HOST_IDENTITY_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
HOST_IDENTITY_RUN_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{7,127}$")
OBSERVED_AT_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REQUIRED_HOST_IDENTITY_FIELDS = {
    "schema_version",
    "target",
    "release_tag",
    "host_label",
    "evidence_run_id",
    "observed_at_utc",
    "operator_private_data_redacted",
    "os",
    "toolchain",
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    contract = read_json(CONTRACT_PATH)
    if args.contract or args.evidence is None:
        errors = check_contract(contract)
    else:
        errors = check_xp_native_evidence(
            args.evidence,
            assets_dir=args.assets_dir,
            evidence_dir=args.evidence_dir,
            contract=contract,
        )
    if errors:
        for error in errors:
            print(f"XP native evidence: {error}", file=sys.stderr)
        return 1
    print("XP native evidence checks passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate imported Windows XP native evidence.")
    parser.add_argument("--contract", action="store_true", help="validate the XP evidence contract")
    parser.add_argument("--evidence", type=Path, help="XP native evidence JSON file")
    parser.add_argument("--assets-dir", type=Path, help="optional directory containing XP native artifacts")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="optional directory containing smoke evidence files referenced by the XP evidence JSON",
    )
    return parser.parse_args(argv)


def check_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != 1:
        errors.append("configs/xp_native_evidence_contract.json schema_version must be 1")
    targets = contract.get("targets")
    if not isinstance(targets, dict):
        return [*errors, "XP native evidence contract targets must be an object"]
    if set(targets) != PROMOTION_TARGETS:
        errors.append(
            "XP native evidence contract targets must exactly match "
            f"{sorted(PROMOTION_TARGETS)}, got {sorted(targets)}"
        )
    else:
        x86 = targets.get("windows-xp-native-x86", {})
        x64 = targets.get("windows-xp-native-x64", {})
        if not isinstance(x86, dict) or x86.get("minimum_service_pack") != "SP3":
            errors.append("XP x86 native evidence contract must require Windows XP SP3")
        if not isinstance(x64, dict) or x64.get("minimum_service_pack") != "SP2":
            errors.append("XP x64 native evidence contract must require Windows XP Professional x64 SP2")
        if not isinstance(x64, dict) or x64.get("required_edition") != "Professional x64 Edition":
            errors.append("XP x64 native evidence contract must require Professional x64 Edition")
    smoke_ids = contract.get("required_smoke_ids")
    if not isinstance(smoke_ids, list) or len(smoke_ids) < 6:
        errors.append("XP native evidence contract must list required_smoke_ids")
    if contract.get("required_smoke_evidence_file") is not True:
        errors.append("XP native evidence contract must require smoke evidence files")
    smoke_fields = contract.get("required_smoke_result_fields")
    required_smoke_fields = {"id", "passed", "command", "evidence_file", "evidence_sha256"}
    if not isinstance(smoke_fields, list) or not required_smoke_fields.issubset(
        {str(item) for item in smoke_fields}
    ):
        errors.append(
            "XP native evidence contract must require smoke result id, passed, command, "
            "evidence_file, and evidence_sha256 fields"
        )
    command_bindings = contract.get("required_smoke_command_bindings")
    required_command_bindings = {
        "scripts/xp_smoke_runner.cmd",
        "--target <target>",
        "--release-tag <release_tag>",
        "--smoke-id <smoke_id>",
        "--evidence-file <evidence_file>",
        "--proof-file xp-smoke-proof/<smoke_id>.txt",
    }
    if not isinstance(command_bindings, list) or not required_command_bindings.issubset(
        {str(item) for item in command_bindings}
    ):
        errors.append(
            "XP native evidence contract must require tracked runner, target, release-tag, "
            "smoke-id, evidence-file, and proof-file bindings"
        )
    command_prefix = str(contract.get("required_smoke_command_prefix", ""))
    if command_prefix != "scripts/xp_smoke_runner.cmd":
        errors.append("XP native evidence contract must require scripts/xp_smoke_runner.cmd")
    else:
        runner_path = ROOT / command_prefix
        if not runner_path.is_file():
            errors.append("XP native smoke runner script is missing: scripts/xp_smoke_runner.cmd")
        else:
            try:
                runner_text = runner_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append("XP native smoke runner script must be UTF-8 text")
            else:
                for snippet in ("--target", "--release-tag", "--smoke-id", "--evidence-file", "--proof-file"):
                    if snippet not in runner_text:
                        errors.append(f"XP native smoke runner script must handle {snippet}")
    smoke_root = str(contract.get("smoke_evidence_root", ""))
    if "evidence JSON directory" not in smoke_root:
        errors.append("XP native evidence contract must document smoke evidence file resolution")
    if contract.get("required_smoke_evidence_file_pattern") != "xp-smoke-evidence/<smoke_id>.txt":
        errors.append(
            "XP native evidence contract must require smoke evidence files under "
            "xp-smoke-evidence/<smoke_id>.txt"
        )
    binding_lines = contract.get("required_smoke_evidence_binding_lines")
    required_binding_lines = {
        "xp smoke target: <target>",
        "xp smoke release: <release_tag>",
        "xp smoke id: <smoke_id>",
    }
    if not isinstance(binding_lines, list) or not required_binding_lines.issubset(
        {str(item) for item in binding_lines}
    ):
        errors.append(
            "XP native evidence contract must require smoke evidence target, release-tag and smoke-id binding lines"
        )
    security_lines = contract.get("required_security_smoke_evidence_lines")
    required_security_lines = {
        "legacy_crypto_profile_scoped": {
            "legacy compatibility profile: isolated-opt-in",
            "legacy crypto scope: profile-only",
            "weak crypto global default: false",
        },
        "modern_defaults_unchanged": {
            "modern TLS minimum: TLS 1.2",
            "modern TLS preferred: TLS 1.3",
            "modern defaults unchanged: true",
            "weak crypto global default: false",
        },
    }
    if not isinstance(security_lines, dict):
        errors.append("XP native evidence contract must define required_security_smoke_evidence_lines")
    else:
        for smoke_id, required_lines in sorted(required_security_lines.items()):
            actual_lines = security_lines.get(smoke_id)
            if not isinstance(actual_lines, list) or not required_lines.issubset(
                {str(item) for item in actual_lines}
            ):
                errors.append(
                    "XP native evidence contract required_security_smoke_evidence_lines "
                    f"missing {smoke_id} proof lines"
                )
    host_identity_fields = contract.get("required_host_identity_fields")
    if not isinstance(host_identity_fields, list) or not REQUIRED_HOST_IDENTITY_FIELDS.issubset(
        {str(item) for item in host_identity_fields}
    ):
        errors.append("XP native evidence contract must require sanitized host identity fields")
    host_identity_policy = str(contract.get("host_identity_policy", ""))
    if "sanitized" not in host_identity_policy or "Do not record" not in host_identity_policy:
        errors.append("XP native evidence contract must document sanitized host identity policy")
    if contract.get("required_artifact_list_exact") is not True:
        errors.append("XP native evidence contract must require exact artifact lists")
    if contract.get("artifact_validation_tag_must_match_release_tag") is not True:
        errors.append("XP native evidence contract must require artifact validation tag matching")
    for key in ("required_security_flags", "required_toolchain_flags"):
        value = contract.get(key)
        if not isinstance(value, dict) or not value:
            errors.append(f"XP native evidence contract must define {key}")
    patch_evidence = contract.get("required_security_patch_evidence")
    if not isinstance(patch_evidence, dict) or not patch_evidence:
        errors.append("XP native evidence contract must define required_security_patch_evidence")
    forbidden = contract.get("forbidden_evidence_patterns")
    if not isinstance(forbidden, list) or not forbidden:
        errors.append("XP native evidence contract must define forbidden_evidence_patterns")
    else:
        missing_patterns = sorted(REQUIRED_FORBIDDEN_EVIDENCE_PATTERNS - {str(item) for item in forbidden})
        if missing_patterns:
            errors.append(
                "XP native evidence contract forbidden_evidence_patterns missing required entries: "
                f"{missing_patterns}"
            )
    return errors


def check_xp_native_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
    evidence_dir: Path | None = None,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    contract_data = contract or read_json(CONTRACT_PATH)
    errors: list[str] = []
    if not evidence_path.is_file():
        return [f"evidence file missing: {evidence_path}"]
    try:
        raw_text = evidence_path.read_text(encoding="utf-8")
        evidence = json.loads(raw_text)
    except UnicodeDecodeError:
        return [f"evidence file must be UTF-8 JSON: {evidence_path}"]
    except json.JSONDecodeError as exc:
        return [f"evidence file is not valid JSON: {exc}"]
    if not isinstance(evidence, dict):
        return ["evidence file must contain a JSON object"]

    errors.extend(check_forbidden_patterns(raw_text, contract_data))
    target = str(evidence.get("target", ""))
    target_contract = target_contract_for(contract_data, target, errors)
    if target_contract is None:
        return errors
    if evidence.get("schema_version") != 1:
        errors.append("XP native evidence schema_version must be 1")
    release_tag = str(evidence.get("release_tag", ""))
    if not re.fullmatch(r"v\d+\.\d+\.\d+", release_tag):
        errors.append(f"XP native evidence release_tag must look like vX.Y.Z, got {release_tag!r}")

    errors.extend(check_os(target, evidence.get("os"), target_contract))
    errors.extend(check_toolchain(target, evidence.get("toolchain"), contract_data))
    errors.extend(
        check_host_identity(
            target,
            release_tag,
            evidence.get("host_identity"),
            evidence.get("os"),
            evidence.get("toolchain"),
            target_contract,
            contract_data,
        )
    )
    errors.extend(check_security(target, evidence.get("security"), contract_data))
    evidence_root = (evidence_dir or evidence_path.parent).resolve()
    errors.extend(check_smoke_results(target, release_tag, evidence.get("smoke_results"), contract_data, evidence_root))
    errors.extend(check_artifact_validation_record(target, evidence.get("artifact_validation"), release_tag))
    errors.extend(check_artifact_names(target, evidence.get("artifacts"), target_contract, release_tag))
    if assets_dir is not None and release_tag:
        errors.extend(
            check_platform_promotion_artifacts(
                target=target,
                assets_dir=assets_dir,
                tag=release_tag,
            )
        )
    return errors


def check_os(target: str, raw_os: Any, target_contract: dict[str, Any]) -> list[str]:
    if not isinstance(raw_os, dict):
        return [f"{target} evidence os must be an object"]
    errors: list[str] = []
    for key in ("name", "architecture"):
        expected = target_contract.get(key if key != "name" else "os_name")
        if raw_os.get(key) != expected:
            errors.append(f"{target} evidence os.{key} must be {expected!r}, got {raw_os.get(key)!r}")
    expected_edition = str(target_contract.get("required_edition", ""))
    if expected_edition and raw_os.get("edition") != expected_edition:
        errors.append(f"{target} evidence os.edition must be {expected_edition!r}, got {raw_os.get('edition')!r}")
    service_pack = str(raw_os.get("service_pack", ""))
    expected_service_pack = str(target_contract.get("minimum_service_pack", ""))
    if expected_service_pack and expected_service_pack not in service_pack:
        errors.append(
            f"{target} evidence os.service_pack must include {expected_service_pack!r}, got {service_pack!r}"
        )
    return errors


def check_toolchain(target: str, raw_toolchain: Any, contract: dict[str, Any]) -> list[str]:
    if not isinstance(raw_toolchain, dict):
        return [f"{target} evidence toolchain must be an object"]
    errors: list[str] = []
    required_flags = contract.get("required_toolchain_flags", {})
    for key, expected in required_flags.items():
        if raw_toolchain.get(key) is not expected:
            errors.append(f"{target} evidence toolchain.{key} must be {expected!r}")
    description = str(raw_toolchain.get("description", ""))
    if len(description.strip()) < 12:
        errors.append(f"{target} evidence toolchain.description must describe the XP-capable toolchain")
    return errors


def check_host_identity(
    target: str,
    release_tag: str,
    raw_identity: Any,
    raw_os: Any,
    raw_toolchain: Any,
    target_contract: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    if not isinstance(raw_identity, dict):
        return [f"{target} evidence host_identity must be an object"]
    errors: list[str] = []
    required_fields = {str(item) for item in contract.get("required_host_identity_fields", [])}
    missing = sorted(required_fields - set(raw_identity))
    if missing:
        errors.append(f"{target} evidence host_identity missing required fields: {missing}")
    if raw_identity.get("schema_version") != 1:
        errors.append(f"{target} evidence host_identity.schema_version must be 1")
    if raw_identity.get("target") != target:
        errors.append(f"{target} evidence host_identity.target must be {target}")
    if raw_identity.get("release_tag") != release_tag:
        errors.append(f"{target} evidence host_identity.release_tag must match evidence release_tag {release_tag}")

    host_label = str(raw_identity.get("host_label", "")).strip()
    if not HOST_IDENTITY_LABEL_RE.fullmatch(host_label):
        errors.append(
            f"{target} evidence host_identity.host_label must be a sanitized lab label, got {host_label!r}"
        )
    evidence_run_id = str(raw_identity.get("evidence_run_id", "")).strip()
    if not HOST_IDENTITY_RUN_RE.fullmatch(evidence_run_id):
        errors.append(
            f"{target} evidence host_identity.evidence_run_id must be a sanitized concrete run id, "
            f"got {evidence_run_id!r}"
        )
    observed_at = str(raw_identity.get("observed_at_utc", "")).strip()
    if not OBSERVED_AT_UTC_RE.fullmatch(observed_at):
        errors.append(
            f"{target} evidence host_identity.observed_at_utc must be UTC ISO-8601 seconds ending in Z, "
            f"got {observed_at!r}"
        )
    if raw_identity.get("operator_private_data_redacted") is not True:
        errors.append(f"{target} evidence host_identity.operator_private_data_redacted must be true")

    expected_os = normalized_host_os(raw_os)
    identity_os = raw_identity.get("os")
    if not isinstance(identity_os, dict):
        errors.append(f"{target} evidence host_identity.os must be an object")
    elif identity_os != expected_os:
        errors.append(f"{target} evidence host_identity.os must match evidence os")
    else:
        errors.extend(check_os(target, identity_os, target_contract))

    expected_toolchain = normalized_host_toolchain(raw_toolchain)
    identity_toolchain = raw_identity.get("toolchain")
    if not isinstance(identity_toolchain, dict):
        errors.append(f"{target} evidence host_identity.toolchain must be an object")
    elif identity_toolchain != expected_toolchain:
        errors.append(f"{target} evidence host_identity.toolchain must match evidence toolchain identity")
    else:
        errors.extend(check_toolchain(target, identity_toolchain, contract))
    return errors


def normalized_host_os(raw_os: Any) -> dict[str, Any]:
    if not isinstance(raw_os, dict):
        return {}
    keys = ("name", "architecture", "service_pack", "edition")
    return {key: raw_os[key] for key in keys if key in raw_os}


def normalized_host_toolchain(raw_toolchain: Any) -> dict[str, Any]:
    if not isinstance(raw_toolchain, dict):
        return {}
    keys = ("separate_legacy_toolchain", "current_python_pyqt6_stack", "description")
    return {key: raw_toolchain[key] for key in keys if key in raw_toolchain}


def check_security(target: str, raw_security: Any, contract: dict[str, Any]) -> list[str]:
    if not isinstance(raw_security, dict):
        return [f"{target} evidence security must be an object"]
    errors: list[str] = []
    required_flags = contract.get("required_security_flags", {})
    for key, expected in required_flags.items():
        if raw_security.get(key) is not expected:
            errors.append(f"{target} evidence security.{key} must be {expected!r}")
    patch_evidence = raw_security.get("patch_evidence")
    if not isinstance(patch_evidence, dict):
        errors.append(f"{target} evidence security.patch_evidence must be an object")
        return errors
    required_patch_evidence = contract.get("required_security_patch_evidence", {})
    if isinstance(required_patch_evidence, dict):
        for key, expected in required_patch_evidence.items():
            if patch_evidence.get(key) != expected:
                errors.append(f"{target} evidence security.patch_evidence.{key} must be {expected!r}")
    return errors


def check_smoke_results(
    target: str,
    release_tag: str,
    raw_results: Any,
    contract: dict[str, Any],
    evidence_root: Path,
) -> list[str]:
    if not isinstance(raw_results, list):
        return [f"{target} evidence smoke_results must be a list"]
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    smoke_ids: list[str] = []
    for item in raw_results:
        if not isinstance(item, dict):
            errors.append(f"{target} smoke result entries must be objects")
            continue
        smoke_id = str(item.get("id", ""))
        if not smoke_id:
            errors.append(f"{target} smoke result entry missing id")
            continue
        smoke_ids.append(smoke_id)
        by_id[smoke_id] = item
    required = {str(item) for item in contract.get("required_smoke_ids", [])}
    actual = set(smoke_ids)
    missing = sorted(required - set(by_id))
    if missing:
        errors.append(f"{target} evidence missing smoke results: {missing}")
    unexpected = sorted(actual - required)
    if unexpected:
        errors.append(f"{target} evidence contains unexpected smoke results: {unexpected}")
    duplicates = sorted(smoke_id for smoke_id in actual if smoke_ids.count(smoke_id) > 1)
    if duplicates:
        errors.append(f"{target} evidence contains duplicate smoke results: {duplicates}")
    for smoke_id in sorted(required & set(by_id)):
        item = by_id[smoke_id]
        if item.get("passed") is not True:
            errors.append(f"{target} smoke result {smoke_id} must have passed=true")
        evidence_sha = str(item.get("evidence_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", evidence_sha):
            errors.append(f"{target} smoke result {smoke_id} missing evidence_sha256")
        errors.extend(check_smoke_command(target, release_tag, smoke_id, item, contract))
        errors.extend(check_smoke_evidence_file(target, release_tag, smoke_id, item, evidence_root, contract))
    return errors


def check_smoke_command(
    target: str,
    release_tag: str,
    smoke_id: str,
    item: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    command = str(item.get("command", "")).strip()
    if not command:
        return [f"{target} smoke result {smoke_id} missing command provenance"]
    if "<" in command or ">" in command:
        return [f"{target} smoke result {smoke_id} command must be concrete, got {command!r}"]
    errors: list[str] = []
    command_prefix = str(contract.get("required_smoke_command_prefix", ""))
    if command_prefix and not command.startswith(f"{command_prefix} "):
        errors.append(
            f"{target} smoke result {smoke_id} command must start with {command_prefix!r}, got {command!r}"
        )
    evidence_file = str(item.get("evidence_file", "")).strip()
    errors.extend(
        check_smoke_command_binding(
            target,
            release_tag,
            smoke_id,
            command,
            evidence_file=evidence_file,
            label=f"{target} smoke result {smoke_id} command",
        )
    )
    return errors


def check_smoke_command_binding(
    target: str,
    release_tag: str,
    smoke_id: str,
    command: str,
    *,
    evidence_file: str | None = None,
    label: str,
) -> list[str]:
    expected_values = {
        "--target": target,
        "--release-tag": release_tag,
        "--smoke-id": smoke_id,
        "--proof-file": f"xp-smoke-proof/{smoke_id}.txt",
    }
    if evidence_file is not None:
        expected_values["--evidence-file"] = evidence_file
    errors: list[str] = []
    for flag, expected in expected_values.items():
        values = re.findall(rf"(?:^|\s){re.escape(flag)}\s+(\S+)(?=\s|$)", command)
        if values != [expected]:
            errors.append(f"{label} must include exactly one {flag} {expected}, got {values}")
    return errors


def check_smoke_evidence_file(
    target: str,
    release_tag: str,
    smoke_id: str,
    item: dict[str, Any],
    evidence_root: Path,
    contract: dict[str, Any],
) -> list[str]:
    if contract.get("required_smoke_evidence_file") is not True:
        return []
    raw_file = str(item.get("evidence_file", ""))
    if not raw_file:
        return [f"{target} smoke result {smoke_id} missing evidence_file"]
    expected_file = f"xp-smoke-evidence/{smoke_id}.txt"
    if raw_file != expected_file:
        return [f"{target} smoke result {smoke_id} evidence_file must be {expected_file}"]
    evidence_file = Path(raw_file)
    if evidence_file.is_absolute():
        return [f"{target} smoke result {smoke_id} evidence_file must be relative"]
    resolved = (evidence_root / evidence_file).resolve()
    try:
        resolved.relative_to(evidence_root)
    except ValueError:
        return [f"{target} smoke result {smoke_id} evidence_file must stay inside evidence directory"]
    if not resolved.is_file():
        return [f"{target} smoke result {smoke_id} evidence_file missing: {raw_file}"]
    data = resolved.read_bytes()
    if not data:
        return [f"{target} smoke result {smoke_id} evidence_file must not be empty: {raw_file}"]
    expected_sha = str(item.get("evidence_sha256", ""))
    actual_sha = hashlib.sha256(data).hexdigest()
    errors: list[str] = []
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha) and actual_sha != expected_sha:
        errors.append(f"{target} smoke result {smoke_id} evidence_file SHA-256 mismatch: {raw_file}")
    errors.extend(check_forbidden_patterns_bytes(data, contract, label=f"{smoke_id} evidence_file"))
    errors.extend(check_smoke_evidence_binding(target, release_tag, smoke_id, data))
    errors.extend(check_security_smoke_evidence_lines(target, smoke_id, data, contract))
    return errors


def check_smoke_evidence_binding(target: str, release_tag: str, smoke_id: str, data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{target} smoke result {smoke_id} evidence_file must be UTF-8 text for binding validation: {exc}"]
    targets = sorted(
        {
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.strip().startswith("xp smoke target:")
        }
    )
    smoke_ids = sorted(
        {
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.strip().startswith("xp smoke id:")
        }
    )
    release_tags = sorted(
        {
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.strip().startswith("xp smoke release:")
        }
    )
    errors: list[str] = []
    if targets != [target]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file target binding must be {[target]}, got {targets}"
        )
    if release_tags != [release_tag]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file release binding must be {[release_tag]}, got {release_tags}"
        )
    if smoke_ids != [smoke_id]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file smoke-id binding must be {[smoke_id]}, got {smoke_ids}"
        )
    return errors


def check_security_smoke_evidence_lines(
    target: str,
    smoke_id: str,
    data: bytes,
    contract: dict[str, Any],
) -> list[str]:
    required = contract.get("required_security_smoke_evidence_lines")
    if not isinstance(required, dict):
        return []
    raw_lines = required.get(smoke_id)
    if not isinstance(raw_lines, list):
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{target} smoke result {smoke_id} evidence_file must be UTF-8 text for security proof: {exc}"]
    normalized_lines = {line.strip().lower() for line in text.splitlines() if line.strip()}
    errors: list[str] = []
    for line in raw_lines:
        expected = str(line).strip()
        if expected.lower() not in normalized_lines:
            errors.append(
                f"{target} smoke result {smoke_id} evidence_file missing security proof line: {expected}"
            )
    return errors


def check_artifact_validation_record(target: str, raw_record: Any, release_tag: str) -> list[str]:
    if not isinstance(raw_record, dict):
        return [f"{target} evidence artifact_validation must be an object"]
    errors: list[str] = []
    if raw_record.get("passed") is not True:
        errors.append(f"{target} evidence artifact_validation.passed must be true")
    command = str(raw_record.get("command", ""))
    expected = f"python scripts/check_platform_promotion_artifacts.py --target {target} "
    if not command.startswith(expected):
        errors.append(f"{target} evidence artifact_validation.command must start with {expected!r}")
    tags = re.findall(r"(?:^|\s)--tag\s+(\S+)(?=\s|$)", command)
    if tags != [release_tag]:
        errors.append(
            f"{target} evidence artifact_validation.command must include exactly one --tag {release_tag}, got {tags}"
        )
    asset_dirs = re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command)
    if len(asset_dirs) != 1:
        errors.append(
            f"{target} evidence artifact_validation.command must include exactly one --assets-dir, got {asset_dirs}"
        )
    elif "<" in asset_dirs[0] or ">" in asset_dirs[0]:
        errors.append(f"{target} evidence artifact_validation.command --assets-dir must be concrete, got {asset_dirs[0]!r}")
    else:
        errors.extend(check_artifact_validation_assets_dir(target, release_tag, asset_dirs[0]))
    return errors


def check_artifact_validation_assets_dir(target: str, release_tag: str, raw_path: str) -> list[str]:
    path = raw_path.strip()
    errors: list[str] = []
    if any(char in path for char in "*?"):
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must not contain wildcards, got {raw_path!r}"
        )
    if "\\" in path:
        parsed_path = PureWindowsPath(path)
        parts = parsed_path.parts
        is_absolute = parsed_path.is_absolute() or bool(parsed_path.drive)
    else:
        parsed_path = PurePosixPath(path)
        parts = parsed_path.parts
        is_absolute = parsed_path.is_absolute()
    if is_absolute:
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must be workspace-relative, got {raw_path!r}"
        )
    if any(part == ".." for part in parts):
        errors.append(f"{target} evidence artifact_validation.command --assets-dir must not traverse directories")
    normalized_parts = tuple(part for part in parts if part not in ("", "."))
    if target not in normalized_parts:
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must include target path segment {target!r}, got {raw_path!r}"
        )
    if release_tag not in normalized_parts:
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must include release_tag path segment {release_tag!r}, got {raw_path!r}"
        )
    if path.endswith(".json"):
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must be a directory path, got {raw_path!r}"
        )
    return errors


def check_artifact_names(
    target: str,
    raw_artifacts: Any,
    target_contract: dict[str, Any],
    release_tag: str,
) -> list[str]:
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        return [f"{target} evidence artifacts must be a non-empty list"]
    required_target = str(target_contract.get("required_artifact_target", ""))
    errors: list[str] = []
    artifact_names = [Path(str(artifact)).name for artifact in raw_artifacts]
    for artifact in raw_artifacts:
        artifact_name = str(artifact)
        if required_target not in artifact_name:
            errors.append(f"{target} evidence artifact name must include {required_target}: {artifact_name}")
    expected_artifacts = expected_artifact_names(target, release_tag, errors)
    if expected_artifacts:
        artifact_set = set(artifact_names)
        duplicate_artifacts = sorted(name for name in artifact_set if artifact_names.count(name) > 1)
        if duplicate_artifacts:
            errors.append(f"{target} evidence artifacts contain duplicate names: {duplicate_artifacts}")
        missing = sorted(expected_artifacts - artifact_set)
        if missing:
            errors.append(f"{target} evidence artifacts missing expected names: {missing}")
        unexpected = sorted(artifact_set - expected_artifacts)
        if unexpected:
            errors.append(f"{target} evidence artifacts contain unexpected names: {unexpected}")
    return errors


def expected_artifact_names(target: str, release_tag: str, errors: list[str]) -> set[str]:
    version_errors: list[str] = []
    version = version_from_tag(release_tag, version_errors)
    if version_errors:
        return set()
    promotion = read_promotion_json(PROMOTION_PATH)
    entries = promotion_entries(promotion, errors)
    entry = entries.get(target)
    if entry is None:
        errors.append(f"XP native evidence promotion config missing target: {target}")
        return set()
    return {expand_version(name, version) for name in required_artifacts(entry)}


def check_forbidden_patterns(raw_text: str, contract: dict[str, Any]) -> list[str]:
    return check_forbidden_patterns_text(raw_text, contract, label="XP native evidence")


def check_forbidden_patterns_text(raw_text: str, contract: dict[str, Any], *, label: str) -> list[str]:
    normalized = raw_text.lower()
    errors: list[str] = []
    for pattern in contract.get("forbidden_evidence_patterns", []):
        needle = str(pattern)
        if needle.lower() in normalized:
            errors.append(f"{label} contains forbidden sensitive pattern: {needle}")
    return errors


def check_forbidden_patterns_bytes(raw_data: bytes, contract: dict[str, Any], *, label: str) -> list[str]:
    normalized = raw_data.lower()
    errors: list[str] = []
    for pattern in contract.get("forbidden_evidence_patterns", []):
        needle = str(pattern).encode("utf-8").lower()
        if needle in normalized:
            errors.append(f"{label} contains forbidden sensitive pattern: {pattern}")
    return errors


def target_contract_for(
    contract: dict[str, Any],
    target: str,
    errors: list[str],
) -> dict[str, Any] | None:
    targets = contract.get("targets")
    if not isinstance(targets, dict):
        errors.append("XP native evidence contract targets must be an object")
        return None
    raw_target = targets.get(target)
    if not isinstance(raw_target, dict):
        errors.append(f"unknown XP native evidence target: {target}")
        return None
    return raw_target


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())

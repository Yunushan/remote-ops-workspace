from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
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
    smoke_ids = contract.get("required_smoke_ids")
    if not isinstance(smoke_ids, list) or len(smoke_ids) < 6:
        errors.append("XP native evidence contract must list required_smoke_ids")
    if contract.get("required_smoke_evidence_file") is not True:
        errors.append("XP native evidence contract must require smoke evidence files")
    smoke_root = str(contract.get("smoke_evidence_root", ""))
    if "evidence JSON directory" not in smoke_root:
        errors.append("XP native evidence contract must document smoke evidence file resolution")
    if contract.get("required_artifact_list_exact") is not True:
        errors.append("XP native evidence contract must require exact artifact lists")
    if contract.get("artifact_validation_tag_must_match_release_tag") is not True:
        errors.append("XP native evidence contract must require artifact validation tag matching")
    for key in ("required_security_flags", "required_toolchain_flags"):
        value = contract.get(key)
        if not isinstance(value, dict) or not value:
            errors.append(f"XP native evidence contract must define {key}")
    forbidden = contract.get("forbidden_evidence_patterns")
    if not isinstance(forbidden, list) or not forbidden:
        errors.append("XP native evidence contract must define forbidden_evidence_patterns")
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
    errors.extend(check_security(target, evidence.get("security"), contract_data))
    evidence_root = (evidence_dir or evidence_path.parent).resolve()
    errors.extend(check_smoke_results(target, evidence.get("smoke_results"), contract_data, evidence_root))
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


def check_security(target: str, raw_security: Any, contract: dict[str, Any]) -> list[str]:
    if not isinstance(raw_security, dict):
        return [f"{target} evidence security must be an object"]
    errors: list[str] = []
    required_flags = contract.get("required_security_flags", {})
    for key, expected in required_flags.items():
        if raw_security.get(key) is not expected:
            errors.append(f"{target} evidence security.{key} must be {expected!r}")
    return errors


def check_smoke_results(
    target: str,
    raw_results: Any,
    contract: dict[str, Any],
    evidence_root: Path,
) -> list[str]:
    if not isinstance(raw_results, list):
        return [f"{target} evidence smoke_results must be a list"]
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            errors.append(f"{target} smoke result entries must be objects")
            continue
        smoke_id = str(item.get("id", ""))
        if smoke_id:
            by_id[smoke_id] = item
    required = {str(item) for item in contract.get("required_smoke_ids", [])}
    missing = sorted(required - set(by_id))
    if missing:
        errors.append(f"{target} evidence missing smoke results: {missing}")
    for smoke_id in sorted(required & set(by_id)):
        item = by_id[smoke_id]
        if item.get("passed") is not True:
            errors.append(f"{target} smoke result {smoke_id} must have passed=true")
        evidence_sha = str(item.get("evidence_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", evidence_sha):
            errors.append(f"{target} smoke result {smoke_id} missing evidence_sha256")
        errors.extend(check_smoke_evidence_file(target, smoke_id, item, evidence_root, contract))
    return errors


def check_smoke_evidence_file(
    target: str,
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

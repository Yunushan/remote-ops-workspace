from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.gui_designs import GUI_DESIGN_PRESETS  # noqa: E402

CRITERIA_PATH = ROOT / "configs" / "gui_parity_criteria.json"
PREVIEW_MANIFEST_PATH = ROOT / "artifacts" / "gui-design-previews" / "preview-manifest.json"
PRODUCT_STYLE_PRESETS = {"mobaxterm", "securecrt", "termius", "remmina", "mremoteng"}
PROHIBITED_SAMPLE_TOKENS = {"yunus", "yunushan", "yunus-pc", "yunus-home"}
MIN_EVIDENCE_FILES_PER_REQUIREMENT = 2
PACKAGE_SOURCE_PREFIX = "src/remote_ops_workspace/"
GUI_PRIVACY_EVIDENCE_PATHS = (
    "configs/gui_visual_metrics.json",
    "docs/GUI_DESIGN.md",
    "scripts/render_gui_design_previews.py",
    "scripts/check_gui_visual_metrics.py",
    "scripts/check_real_gui_render.py",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check product-style GUI/UX parity criteria.")
    parser.add_argument("--json", action="store_true", help="Print the generated parity report as JSON.")
    args = parser.parse_args([] if argv is None else argv)

    errors = check_gui_parity()
    if errors:
        for error in errors:
            print(f"GUI parity: {error}", file=sys.stderr)
        return 1
    criteria = load_json(CRITERIA_PATH)
    report = gui_parity_report(criteria)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_parity_report(report))
    return 0


def check_gui_parity() -> list[str]:
    errors: list[str] = []
    try:
        criteria = load_json(CRITERIA_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {display(CRITERIA_PATH)}: {exc}"]
    try:
        preview_manifest = load_json(PREVIEW_MANIFEST_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {display(PREVIEW_MANIFEST_PATH)}: {exc}"]

    errors.extend(check_criteria_shape(criteria))
    errors.extend(check_preview_manifest_coverage(criteria, preview_manifest))
    errors.extend(check_requirement_evidence(criteria))
    errors.extend(check_dimension_coverage(criteria))
    errors.extend(check_no_user_specific_samples(criteria))
    errors.extend(check_parity_target(criteria))
    return errors


def check_criteria_shape(criteria: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if criteria.get("schema_version") != 1:
        errors.append("configs/gui_parity_criteria.json schema_version must be 1")
    if float(criteria.get("target_percent", 0)) != 100.0:
        errors.append("GUI parity target_percent must be 100")
    dimensions = criteria.get("required_dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        errors.append("GUI parity required_dimensions must be a non-empty list")
    else:
        seen_dimensions: set[str] = set()
        for dimension in dimensions:
            if not isinstance(dimension, str) or not dimension:
                errors.append("GUI parity required_dimensions entries must be non-empty strings")
                continue
            if dimension in seen_dimensions:
                errors.append(f"GUI parity duplicate required_dimension: {dimension}")
            seen_dimensions.add(dimension)
    presets = criteria.get("presets")
    if not isinstance(presets, dict):
        return [*errors, "GUI parity presets must be an object"]
    expected_ids = PRODUCT_STYLE_PRESETS
    found_ids = set(presets)
    if found_ids != expected_ids:
        errors.append(f"GUI parity presets {sorted(found_ids)} must equal {sorted(expected_ids)}")
    for preset_id, preset_data in presets.items():
        if not isinstance(preset_data, dict):
            errors.append(f"{preset_id} parity entry must be an object")
            continue
        basis = preset_data.get("reference_basis")
        if not isinstance(basis, list) or not basis or not all(isinstance(item, str) and item for item in basis):
            errors.append(f"{preset_id} must have non-empty reference_basis list")
        requirements = preset_data.get("requirements")
        if not isinstance(requirements, list) or not requirements:
            errors.append(f"{preset_id} must have non-empty requirements list")
            continue
        dimension_coverage = preset_data.get("dimension_coverage")
        if not isinstance(dimension_coverage, dict) or not dimension_coverage:
            errors.append(f"{preset_id} must have non-empty dimension_coverage object")
        seen: set[str] = set()
        for requirement in requirements:
            if not isinstance(requirement, dict):
                errors.append(f"{preset_id} requirement must be an object")
                continue
            requirement_id = str(requirement.get("id", ""))
            if not requirement_id:
                errors.append(f"{preset_id} requirement missing id")
            if requirement_id in seen:
                errors.append(f"{preset_id} duplicate requirement id: {requirement_id}")
            seen.add(requirement_id)
            if not str(requirement.get("description", "")):
                errors.append(f"{requirement_id} missing description")
            source_tokens = requirement.get("source_tokens")
            if not isinstance(source_tokens, dict) or not source_tokens:
                errors.append(f"{requirement_id} missing source_tokens evidence")
            elif len(source_tokens) < MIN_EVIDENCE_FILES_PER_REQUIREMENT:
                errors.append(
                    f"{requirement_id} must include at least "
                    f"{MIN_EVIDENCE_FILES_PER_REQUIREMENT} evidence files"
                )
            elif not has_non_package_evidence_source(source_tokens):
                errors.append(f"{requirement_id} must include non-package evidence outside {PACKAGE_SOURCE_PREFIX}")
    return errors


def check_preview_manifest_coverage(criteria: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    configured = set(criteria.get("presets", {}))
    preset_ids = {preset.id for preset in GUI_DESIGN_PRESETS}
    missing_from_designs = sorted(configured - preset_ids)
    if missing_from_designs:
        errors.append(f"GUI parity criteria reference unknown design presets: {missing_from_designs}")
    manifest_presets = manifest.get("presets", [])
    if not isinstance(manifest_presets, list):
        return [*errors, "preview manifest presets must be a list"]
    manifest_ids = {str(item.get("id", "")) for item in manifest_presets if isinstance(item, dict)}
    missing_from_manifest = sorted(configured - manifest_ids)
    if missing_from_manifest:
        errors.append(f"GUI parity presets missing from preview manifest: {missing_from_manifest}")
    return errors


def check_requirement_evidence(criteria: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for preset_id, preset_data in criteria.get("presets", {}).items():
        for requirement in preset_data.get("requirements", []):
            requirement_id = str(requirement.get("id", f"{preset_id}.unknown"))
            source_tokens = requirement.get("source_tokens", {})
            if not isinstance(source_tokens, dict):
                continue
            for rel_path, tokens in source_tokens.items():
                path = ROOT / str(rel_path)
                if not path.is_file():
                    errors.append(f"{requirement_id} evidence file missing: {rel_path}")
                    continue
                text = path.read_text(encoding="utf-8")
                if not isinstance(tokens, list) or not tokens:
                    errors.append(f"{requirement_id} evidence tokens for {rel_path} must be a non-empty list")
                    continue
                for token in tokens:
                    if not isinstance(token, str) or not token:
                        errors.append(f"{requirement_id} has invalid token in {rel_path}")
                    elif token not in text:
                        errors.append(f"{requirement_id} missing token in {rel_path}: {token}")
    return errors


def check_dimension_coverage(criteria: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dimensions = required_dimensions(criteria)
    presets = criteria.get("presets", {})
    if not dimensions or not isinstance(presets, dict):
        return errors
    expected_dimensions = set(dimensions)
    for preset_id, preset_data in presets.items():
        if not isinstance(preset_data, dict):
            continue
        requirements = preset_data.get("requirements", [])
        requirement_map = {
            str(requirement.get("id", "")): requirement
            for requirement in requirements
            if isinstance(requirement, dict)
        }
        dimension_coverage = preset_data.get("dimension_coverage", {})
        if not isinstance(dimension_coverage, dict):
            continue
        found_dimensions = set(dimension_coverage)
        missing_dimensions = sorted(expected_dimensions - found_dimensions)
        unknown_dimensions = sorted(found_dimensions - expected_dimensions)
        if missing_dimensions:
            errors.append(f"{preset_id} dimension_coverage missing dimensions: {missing_dimensions}")
        if unknown_dimensions:
            errors.append(f"{preset_id} dimension_coverage has unknown dimensions: {unknown_dimensions}")
        for dimension in dimensions:
            requirement_ids = dimension_coverage.get(dimension)
            if not isinstance(requirement_ids, list) or not requirement_ids:
                errors.append(f"{preset_id}.{dimension} must map to a non-empty requirement-id list")
                continue
            for requirement_id in requirement_ids:
                if not isinstance(requirement_id, str) or not requirement_id:
                    errors.append(f"{preset_id}.{dimension} has invalid requirement id")
                    continue
                requirement = requirement_map.get(requirement_id)
                if requirement is None:
                    errors.append(
                        f"{preset_id}.{dimension} references unknown requirement id: {requirement_id}"
                    )
                elif not requirement_satisfied(requirement):
                    errors.append(
                        f"{preset_id}.{dimension} references unsatisfied requirement id: {requirement_id}"
                    )
    return errors


def check_no_user_specific_samples(criteria: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(
        check_text_for_prohibited_sample_tokens(
            "GUI parity criteria",
            json.dumps(criteria, sort_keys=True),
        )
    )
    for rel_path in GUI_PRIVACY_EVIDENCE_PATHS:
        path = resolve_privacy_evidence_path(rel_path)
        if not path.is_file():
            errors.append(f"GUI privacy evidence file missing: {rel_path}")
            continue
        errors.extend(check_text_for_prohibited_sample_tokens(display(path), path.read_text(encoding="utf-8")))
    return errors


def resolve_privacy_evidence_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


def check_text_for_prohibited_sample_tokens(label: str, text: str) -> list[str]:
    lowered = text.lower()
    return [
        f"{label} must not include user-specific sample token: {token}"
        for token in sorted(PROHIBITED_SAMPLE_TOKENS)
        if token in lowered
    ]


def check_parity_target(criteria: dict[str, Any]) -> list[str]:
    report = gui_parity_report(criteria)
    errors: list[str] = []
    target = float(report["target_percent"])
    for row in [report["overall"], *report["presets"]]:
        if float(row["current_percent"]) < target:
            label = row.get("preset_id", "overall")
            errors.append(
                f"{label} GUI parity is {row['current_percent']}%, expected {row['target_percent']}%"
            )
        if int(row.get("dimension_count", 0)) and float(row["dimension_percent"]) < target:
            label = row.get("preset_id", "overall")
            errors.append(
                f"{label} GUI parity dimensions are {row['dimension_percent']}%, "
                f"expected {row['target_percent']}%"
            )
    return errors


def gui_parity_report(criteria: dict[str, Any]) -> dict[str, Any]:
    target = float(criteria.get("target_percent", 100))
    dimensions = required_dimensions(criteria)
    presets = criteria.get("presets", {})
    rows: list[dict[str, Any]] = []
    total_count = 0
    total_met = 0
    total_dimension_count = 0
    total_dimensions_met = 0
    if isinstance(presets, dict):
        for preset_id in sorted(presets):
            preset_data = presets[preset_id]
            requirements = preset_data.get("requirements", []) if isinstance(preset_data, dict) else []
            count = len(requirements) if isinstance(requirements, list) else 0
            met = sum(1 for requirement in requirements if requirement_satisfied(requirement)) if isinstance(requirements, list) else 0
            dimension_count, dimensions_met = dimension_counts(preset_data, dimensions)
            rows.append(parity_row(preset_id, count, met, target, dimension_count, dimensions_met))
            total_count += count
            total_met += met
            total_dimension_count += dimension_count
            total_dimensions_met += dimensions_met
    return {
        "schema_version": 1,
        "target_percent": round(target, 1),
        "required_dimensions": dimensions,
        "overall": parity_row(
            "overall",
            total_count,
            total_met,
            target,
            total_dimension_count,
            total_dimensions_met,
        ),
        "presets": rows,
    }


def parity_row(
    preset_id: str,
    requirement_count: int,
    requirements_met: int,
    target_percent: float,
    dimension_count: int = 0,
    dimensions_met: int = 0,
) -> dict[str, Any]:
    current = (requirements_met / requirement_count * 100.0) if requirement_count else 0.0
    gap = max(target_percent - current, 0.0)
    dimension_current = (dimensions_met / dimension_count * 100.0) if dimension_count else 0.0
    dimension_gap = max(target_percent - dimension_current, 0.0) if dimension_count else 0.0
    return {
        "preset_id": preset_id,
        "requirements_met": requirements_met,
        "requirement_count": requirement_count,
        "current_percent": round(current, 1),
        "target_percent": round(target_percent, 1),
        "gap_percent": round(gap, 1),
        "dimensions_met": dimensions_met,
        "dimension_count": dimension_count,
        "dimension_percent": round(dimension_current, 1),
        "dimension_gap_percent": round(dimension_gap, 1),
    }


def dimension_counts(preset_data: Any, dimensions: list[str]) -> tuple[int, int]:
    if not isinstance(preset_data, dict):
        return len(dimensions), 0
    requirements = preset_data.get("requirements", [])
    requirement_map = {
        str(requirement.get("id", "")): requirement
        for requirement in requirements
        if isinstance(requirement, dict)
    }
    dimension_coverage = preset_data.get("dimension_coverage", {})
    if not isinstance(dimension_coverage, dict):
        return len(dimensions), 0
    dimensions_met = 0
    for dimension in dimensions:
        requirement_ids = dimension_coverage.get(dimension)
        if not isinstance(requirement_ids, list) or not requirement_ids:
            continue
        dimension_met = True
        for requirement_id in requirement_ids:
            if not isinstance(requirement_id, str) or not requirement_id:
                dimension_met = False
                break
            requirement = requirement_map.get(requirement_id)
            if requirement is None or not requirement_satisfied(requirement):
                dimension_met = False
                break
        if dimension_met:
            dimensions_met += 1
    return len(dimensions), dimensions_met


def requirement_satisfied(requirement: Any) -> bool:
    if not isinstance(requirement, dict):
        return False
    source_tokens = requirement.get("source_tokens")
    if not isinstance(source_tokens, dict) or not source_tokens:
        return False
    if len(source_tokens) < MIN_EVIDENCE_FILES_PER_REQUIREMENT:
        return False
    if not has_non_package_evidence_source(source_tokens):
        return False
    for rel_path, tokens in source_tokens.items():
        path = ROOT / str(rel_path)
        if not path.is_file():
            return False
        if not isinstance(tokens, list) or not tokens:
            return False
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if not isinstance(token, str) or not token or token not in text:
                return False
    return True


def has_non_package_evidence_source(source_tokens: dict[str, Any]) -> bool:
    return any(not str(rel_path).startswith(PACKAGE_SOURCE_PREFIX) for rel_path in source_tokens)


def format_parity_report(report: dict[str, Any]) -> str:
    overall = report["overall"]
    lines = [
        (
            "GUI parity criteria passed: "
            f"{overall['requirements_met']}/{overall['requirement_count']} requirements tracked"
        ),
        (
            "GUI parity coverage: "
            f"{overall['current_percent']:.1f}% target {overall['target_percent']:.1f}% "
            f"({overall['gap_percent']:.1f}% gap)"
        ),
        (
            "GUI parity dimensions: "
            f"{overall['dimension_percent']:.1f}% target {overall['target_percent']:.1f}% "
            f"({overall['dimension_gap_percent']:.1f}% gap)"
        ),
    ]
    for row in report["presets"]:
        lines.append(
            f"  {row['preset_id']:<10} {row['current_percent']:.1f}% "
            f"({row['requirements_met']}/{row['requirement_count']} requirements), "
            f"{row['dimension_percent']:.1f}% dimensions "
            f"({row['dimensions_met']}/{row['dimension_count']})"
        )
    return "\n".join(lines)


def required_dimensions(criteria: dict[str, Any]) -> list[str]:
    dimensions = criteria.get("required_dimensions", [])
    if not isinstance(dimensions, list):
        return []
    return [dimension for dimension in dimensions if isinstance(dimension, str) and dimension]


def count_requirements(criteria: dict[str, Any]) -> int:
    presets = criteria.get("presets", {})
    if not isinstance(presets, dict):
        return 0
    return sum(len(preset.get("requirements", [])) for preset in presets.values() if isinstance(preset, dict))


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{display(path)} must contain a JSON object")
    return data


def display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

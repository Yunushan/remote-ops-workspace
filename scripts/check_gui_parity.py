from __future__ import annotations

import argparse
import importlib.util
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
METRICS_PATH = ROOT / "configs" / "gui_visual_metrics.json"
PREVIEW_MANIFEST_PATH = ROOT / "artifacts" / "gui-design-previews" / "preview-manifest.json"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
PRODUCT_STYLE_PRESETS = {"mobaxterm", "securecrt", "termius", "remmina", "mremoteng"}
PROHIBITED_SAMPLE_TOKENS = {"yunus", "yunushan", "yunus-pc", "yunus-home"}
MIN_EVIDENCE_FILES_PER_REQUIREMENT = 2
MIN_REFERENCE_VIEW_REGIONS = 3
MIN_REFERENCE_VIEW_ANCHORS = 1
PACKAGE_SOURCE_PREFIX = "src/remote_ops_workspace/"
GUI_PRIVACY_EVIDENCE_PATHS = (
    "configs/gui_visual_metrics.json",
    "docs/GUI_DESIGN.md",
    "docs/VERIFYING.md",
    "scripts/render_gui_design_previews.py",
    "scripts/check_gui_visual_metrics.py",
    "scripts/check_real_gui_render.py",
    "scripts/check_real_gui_render_artifact.py",
    "scripts/verify.py",
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
    try:
        visual_metrics = load_json(METRICS_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {display(METRICS_PATH)}: {exc}"]

    errors.extend(check_criteria_shape(criteria))
    errors.extend(check_preview_manifest_coverage(criteria, preview_manifest))
    errors.extend(check_requirement_evidence(criteria))
    errors.extend(check_dimension_coverage(criteria))
    errors.extend(check_reference_view_coverage(criteria, visual_metrics, preview_manifest))
    errors.extend(check_live_render_proof_contract(criteria))
    errors.extend(check_no_user_specific_samples(criteria))
    errors.extend(check_parity_target(criteria, visual_metrics, preview_manifest))
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
        reference_views = preset_data.get("reference_views")
        if not isinstance(reference_views, list) or not reference_views:
            errors.append(f"{preset_id} must have non-empty reference_views list")
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


def check_reference_view_coverage(
    criteria: dict[str, Any],
    visual_metrics: dict[str, Any] | None = None,
    preview_manifest: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    dimensions = set(required_dimensions(criteria))
    presets = criteria.get("presets", {})
    if not dimensions or not isinstance(presets, dict):
        return errors
    metrics = visual_metrics if isinstance(visual_metrics, dict) else load_json(METRICS_PATH)
    manifest = preview_manifest if isinstance(preview_manifest, dict) else load_json(PREVIEW_MANIFEST_PATH)
    live_contract_source = (ROOT / "scripts" / "check_real_gui_render.py").read_text(encoding="utf-8")
    live_contract_summaries = load_live_contract_summaries()
    for preset_id, preset_data in presets.items():
        if not isinstance(preset_data, dict):
            continue
        reference_views = preset_data.get("reference_views", [])
        if not isinstance(reference_views, list):
            continue
        seen_ids: set[str] = set()
        covered_dimensions: set[str] = set()
        for view in reference_views:
            if not isinstance(view, dict):
                errors.append(f"{preset_id} reference view must be an object")
                continue
            view_id = str(view.get("id", ""))
            if not view_id:
                errors.append(f"{preset_id} reference view missing id")
            elif view_id in seen_ids:
                errors.append(f"{preset_id} duplicate reference view id: {view_id}")
            elif not view_id.startswith(f"{preset_id}."):
                errors.append(f"{preset_id} reference view id must start with {preset_id}.: {view_id}")
            seen_ids.add(view_id)
            for field in ("label", "state", "basis", "static_contract", "live_contract", "contract_check"):
                if not str(view.get(field, "")):
                    errors.append(f"{view_id or preset_id} reference view missing {field}")
            static_preview = str(view.get("static_preview", ""))
            if not static_preview:
                errors.append(f"{view_id or preset_id} reference view missing static_preview")
            elif not (ROOT / static_preview).is_file():
                errors.append(f"{view_id or preset_id} reference view static_preview missing: {static_preview}")
            view_dimensions = view.get("dimensions")
            if not isinstance(view_dimensions, list) or not view_dimensions:
                errors.append(f"{view_id or preset_id} reference view dimensions must be a non-empty list")
                continue
            actual_dimensions = {str(dimension) for dimension in view_dimensions if isinstance(dimension, str)}
            unknown_dimensions = sorted(actual_dimensions - dimensions)
            if unknown_dimensions:
                errors.append(f"{view_id or preset_id} reference view dimensions are unknown: {unknown_dimensions}")
            covered_dimensions.update(actual_dimensions & dimensions)
            errors.extend(check_reference_view_policy(view_id or preset_id, view))
            errors.extend(check_reference_view_dimension_evidence(view_id or preset_id, view, actual_dimensions))
            errors.extend(
                check_reference_view_contract_evidence(
                    preset_id,
                    view,
                    manifest,
                    live_contract_source,
                    live_contract_summaries,
                )
            )
            errors.extend(check_reference_view_visual_evidence(preset_id, view, metrics, manifest))
        missing_dimensions = sorted(dimensions - covered_dimensions)
        if missing_dimensions:
            errors.append(f"{preset_id} reference_views missing dimensions: {missing_dimensions}")
    return errors


def check_reference_view_policy(view_id: str, view: dict[str, Any]) -> list[str]:
    policy = view.get("reference_policy")
    if not isinstance(policy, dict):
        return [f"{view_id} reference view must include reference_policy object"]
    errors: list[str] = []
    if policy.get("approval_scope") != "user-approved-product-style-reference":
        errors.append(
            f"{view_id} reference_policy approval_scope must be user-approved-product-style-reference"
        )
    required_true_fields = (
        "sanitized",
        "synthetic_sample_data",
        "no_user_specific_data",
        "no_credentials",
        "independent_implementation",
        "no_proprietary_assets",
    )
    for field in required_true_fields:
        if policy.get(field) is not True:
            errors.append(f"{view_id} reference_policy {field} must be true")
    note = str(policy.get("note", ""))
    if not note:
        errors.append(f"{view_id} reference_policy note must be non-empty")
    return errors


def check_reference_view_dimension_evidence(
    view_id: str,
    view: dict[str, Any],
    view_dimensions: set[str],
) -> list[str]:
    evidence = view.get("dimension_evidence")
    if not isinstance(evidence, dict):
        return [f"{view_id} reference view must include dimension_evidence object"]
    errors: list[str] = []
    evidence_dimensions = {str(key) for key in evidence}
    missing_dimensions = sorted(view_dimensions - evidence_dimensions)
    unknown_dimensions = sorted(evidence_dimensions - view_dimensions)
    if missing_dimensions:
        errors.append(f"{view_id} dimension_evidence missing dimensions: {missing_dimensions}")
    if unknown_dimensions:
        errors.append(f"{view_id} dimension_evidence has unknown dimensions: {unknown_dimensions}")

    visual_evidence = view.get("visual_evidence", {})
    live_evidence = view.get("live_evidence", {})
    visual_sets = {
        "region_ids": set(str(value) for value in visual_evidence.get("region_ids", []) if isinstance(value, str))
        if isinstance(visual_evidence, dict)
        else set(),
        "color_anchor_ids": set(
            str(value) for value in visual_evidence.get("color_anchor_ids", []) if isinstance(value, str)
        )
        if isinstance(visual_evidence, dict)
        else set(),
        "line_anchor_ids": set(
            str(value) for value in visual_evidence.get("line_anchor_ids", []) if isinstance(value, str)
        )
        if isinstance(visual_evidence, dict)
        else set(),
        "topology_ids": set(str(value) for value in visual_evidence.get("topology_ids", []) if isinstance(value, str))
        if isinstance(visual_evidence, dict)
        else set(),
    }
    live_sets = {
        "live_route_keys": set(
            str(value) for value in live_evidence.get("required_route_keys", []) if isinstance(value, str)
        )
        if isinstance(live_evidence, dict)
        else set(),
        "live_widget_objects": set(
            str(value) for value in live_evidence.get("required_widget_objects", []) if isinstance(value, str)
        )
        if isinstance(live_evidence, dict)
        else set(),
    }
    allowed_keys = {*visual_sets, *live_sets}
    for dimension in sorted(view_dimensions & evidence_dimensions):
        entry = evidence.get(dimension)
        if not isinstance(entry, dict):
            errors.append(f"{view_id} dimension_evidence {dimension} must be an object")
            continue
        unknown_keys = sorted(str(key) for key in entry if str(key) not in allowed_keys)
        if unknown_keys:
            errors.append(f"{view_id} dimension_evidence {dimension} has unknown evidence keys: {unknown_keys}")
        evidence_count = 0
        for key, allowed_values in {**visual_sets, **live_sets}.items():
            values = entry.get(key, [])
            if values in (None, []):
                continue
            if not isinstance(values, list):
                errors.append(f"{view_id} dimension_evidence {dimension}.{key} must be a list")
                continue
            actual_values = {str(value) for value in values if isinstance(value, str) and value}
            evidence_count += len(actual_values)
            unknown_values = sorted(actual_values - allowed_values)
            if unknown_values:
                errors.append(
                    f"{view_id} dimension_evidence {dimension}.{key} references unclaimed evidence: "
                    f"{unknown_values}"
                )
        if evidence_count == 0:
            errors.append(f"{view_id} dimension_evidence {dimension} must reference measured or live evidence")
    return errors


def check_reference_view_contract_evidence(
    preset_id: str,
    view: dict[str, Any],
    preview_manifest: dict[str, Any],
    live_contract_source: str,
    live_contract_summaries: dict[str, Any],
) -> list[str]:
    view_id = str(view.get("id", preset_id))
    static_contract = str(view.get("static_contract", ""))
    live_contract = str(view.get("live_contract", ""))
    contract_check = str(view.get("contract_check", ""))
    errors: list[str] = []
    preset_entry = preview_manifest_entry(preview_manifest, preset_id)
    if preset_entry is None:
        errors.append(f"{view_id} static_contract preset missing from preview manifest: {preset_id}")
    elif not isinstance(preset_entry.get(static_contract), dict) or not preset_entry.get(static_contract):
        errors.append(f"{view_id} static_contract missing from preview manifest preset {preset_id}: {static_contract}")
    if live_contract not in live_contract_source:
        errors.append(f"{view_id} live_contract missing from real GUI render checker: {live_contract}")
    if contract_check not in live_contract_source:
        errors.append(f"{view_id} contract_check missing from real GUI render checker: {contract_check}")
    summary = live_contract_summaries.get(preset_id)
    route: dict[str, Any] = {}
    if not isinstance(summary, dict):
        errors.append(f"{view_id} live_contract preset missing from real GUI render manifest summary: {preset_id}")
    else:
        route_candidate = summary.get(live_contract)
        if not isinstance(route_candidate, dict) or not route_candidate:
            errors.append(f"{view_id} live_contract missing from real GUI render manifest summary: {live_contract}")
        else:
            route = route_candidate
        checks = summary.get("contract_checks", [])
        if not isinstance(checks, list) or contract_check not in checks:
            errors.append(f"{view_id} contract_check missing from live manifest contract_checks: {contract_check}")
    errors.extend(check_reference_view_live_evidence(view_id, view, summary, route))
    return errors


def check_reference_view_live_evidence(
    view_id: str,
    view: dict[str, Any],
    live_contract_summary: Any,
    route: dict[str, Any],
) -> list[str]:
    evidence = view.get("live_evidence")
    if not isinstance(evidence, dict):
        return [f"{view_id} reference view must include live_evidence object"]
    errors: list[str] = []
    live_contract = str(view.get("live_contract", ""))
    summary_route = str(evidence.get("summary_route", ""))
    if summary_route != live_contract:
        errors.append(f"{view_id} live_evidence summary_route must equal live_contract: {live_contract}")
    required_route_keys = evidence.get("required_route_keys")
    if not isinstance(required_route_keys, list) or not required_route_keys:
        errors.append(f"{view_id} live_evidence required_route_keys must be a non-empty list")
    else:
        missing_route_keys = [
            str(key)
            for key in required_route_keys
            if not isinstance(key, str) or not key or route.get(key) in (None, "", [], {})
        ]
        if missing_route_keys:
            errors.append(f"{view_id} live_evidence required_route_keys missing from live route: {missing_route_keys}")
    required_widget_objects = evidence.get("required_widget_objects")
    if not isinstance(required_widget_objects, list) or not required_widget_objects:
        errors.append(f"{view_id} live_evidence required_widget_objects must be a non-empty list")
    elif isinstance(live_contract_summary, dict):
        known_objects = set()
        for key in ("required_widgets", "present_widgets"):
            widgets = live_contract_summary.get(key, {})
            if isinstance(widgets, dict):
                known_objects.update(str(widget) for widget in widgets)
        known_objects.update(
            str(value)
            for key, value in route.items()
            if isinstance(key, str) and key.endswith("_object") and isinstance(value, str) and value
        )
        missing_widgets = [
            str(widget)
            for widget in required_widget_objects
            if not isinstance(widget, str) or not widget or widget not in known_objects
        ]
        if missing_widgets:
            errors.append(
                f"{view_id} live_evidence required_widget_objects missing from live manifest: {missing_widgets}"
            )
    return errors


def check_reference_view_visual_evidence(
    preset_id: str,
    view: dict[str, Any],
    visual_metrics: dict[str, Any],
    preview_manifest: dict[str, Any],
) -> list[str]:
    view_id = str(view.get("id", preset_id))
    raw_evidence = view.get("visual_evidence")
    if not isinstance(raw_evidence, dict):
        return [f"{view_id} reference view must include visual_evidence object"]

    collection = str(raw_evidence.get("metrics_collection", ""))
    if collection not in {"presets", "state_previews"}:
        return [f"{view_id} visual_evidence metrics_collection is unsupported: {collection!r}"]
    metrics_id = str(raw_evidence.get("metrics_id", ""))
    metrics_collection = visual_metrics.get(collection, {})
    if not isinstance(metrics_collection, dict) or metrics_id not in metrics_collection:
        return [f"{view_id} visual_evidence metrics_id missing from {collection}: {metrics_id}"]
    if collection == "presets" and metrics_id != preset_id:
        return [f"{view_id} visual_evidence preset metrics_id must be {preset_id}"]
    if collection == "state_previews" and not metrics_id.startswith(f"{preset_id}-"):
        return [f"{view_id} visual_evidence state metrics_id must start with {preset_id}-"]

    manifest_image = reference_view_manifest_image(preview_manifest, collection, metrics_id)
    if not isinstance(manifest_image, dict):
        return [f"{view_id} visual_evidence metrics image missing from preview manifest: {collection}.{metrics_id}"]
    manifest_image_path = str(manifest_image.get("path", ""))
    static_preview_name = Path(str(view.get("static_preview", ""))).name
    if not manifest_image_path:
        return [f"{view_id} visual_evidence preview manifest image path is empty"]
    if static_preview_name != manifest_image_path:
        return [
            f"{view_id} visual_evidence static_preview {static_preview_name} "
            f"must match metrics image {manifest_image_path}"
        ]

    metric_data = metrics_collection[metrics_id]
    if not isinstance(metric_data, dict):
        return [f"{view_id} visual_evidence metrics data must be an object"]
    errors: list[str] = []
    metric_ids = {
        "region_ids": {str(item.get("id", "")) for item in metric_data.get("regions", []) if isinstance(item, dict)},
        "color_anchor_ids": {
            str(item.get("id", ""))
            for item in metric_data.get("color_anchors", [])
            if isinstance(item, dict)
        },
        "line_anchor_ids": {
            str(item.get("id", ""))
            for item in metric_data.get("line_anchors", [])
            if isinstance(item, dict)
        },
        "topology_ids": {
            str(item.get("id", ""))
            for item in metric_data.get("topology", [])
            if isinstance(item, dict)
        },
    }
    minimums = {
        "region_ids": MIN_REFERENCE_VIEW_REGIONS,
        "color_anchor_ids": MIN_REFERENCE_VIEW_ANCHORS,
        "line_anchor_ids": MIN_REFERENCE_VIEW_ANCHORS,
        "topology_ids": MIN_REFERENCE_VIEW_ANCHORS,
    }
    for key, minimum in minimums.items():
        values = raw_evidence.get(key)
        if not isinstance(values, list) or len(values) < minimum:
            errors.append(f"{view_id} visual_evidence {key} must include at least {minimum} measured ids")
            continue
        actual_ids = {str(value) for value in values if isinstance(value, str) and value}
        unknown = sorted(actual_ids - metric_ids[key])
        if unknown:
            errors.append(f"{view_id} visual_evidence {key} references unknown measured ids: {unknown}")
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


def check_live_render_proof_contract(
    criteria: dict[str, Any],
    *,
    workflow_text: str | None = None,
    verifier_source: str | None = None,
    docs: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    presets = criteria.get("presets", {})
    if not isinstance(presets, dict) or not PRODUCT_STYLE_PRESETS <= set(presets):
        return errors

    workflow = workflow_text if workflow_text is not None else CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    gui_render_block = workflow_job_block(workflow, "gui-render")
    if not gui_render_block:
        errors.append("GUI parity live render proof missing ci gui-render job")
    else:
        required_workflow_snippets = {
            'QT_QPA_PLATFORM: "offscreen"': "offscreen Qt platform",
            '".[desktop,security,dev]"': "desktop extra installation",
            "timeout-minutes: 15": "bounded live GUI render job timeout",
            "timeout-minutes: 8": "bounded live GUI render smoke step timeout",
            "python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 240": (
                "strict bounded PyQt6 live render command"
            ),
            "--out-dir artifacts/gui-real": "live GUI screenshot artifact directory",
            "Validate real GUI render artifact": "live GUI artifact validation step",
            "python scripts/check_real_gui_render_artifact.py --artifact-dir artifacts/gui-real": (
                "live GUI artifact validator command"
            ),
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7": "live GUI screenshot artifact upload",
            "name: gui-real-render": "stable live GUI artifact name",
            "if-no-files-found: error": "artifact failure on missing screenshots",
        }
        for snippet, label in required_workflow_snippets.items():
            if snippet not in gui_render_block:
                errors.append(f"GUI parity live render proof missing {label}: {snippet}")
        if "--preset " in gui_render_block:
            errors.append("GUI parity live render proof must capture all product-style presets without --preset")

    verifier = verifier_source if verifier_source is not None else (ROOT / "scripts" / "verify.py").read_text(
        encoding="utf-8"
    )
    required_verifier_snippets = {
        "--require-real-gui": "strict local verifier option",
        "require_real_gui": "strict local verifier wiring",
        '"--require-pyqt6"': "strict local PyQt6 render forwarding",
        "scripts/check_real_gui_render_artifact.py": "live render artifact validator",
        "real GUI render artifact validator contract": "live render artifact validator contract step",
    }
    for snippet, label in required_verifier_snippets.items():
        if snippet not in verifier:
            errors.append(f"GUI parity live render proof missing {label}: {snippet}")

    doc_sources = docs if docs is not None else {
        "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
        "docs/VERIFYING.md": (ROOT / "docs" / "VERIFYING.md").read_text(encoding="utf-8"),
        "docs/GUI_DESIGN.md": (ROOT / "docs" / "GUI_DESIGN.md").read_text(encoding="utf-8"),
    }
    required_doc_snippets = {
        "README.md": ("python scripts/verify.py --require-real-gui",),
        "docs/VERIFYING.md": (
            "python scripts/verify.py --require-real-gui",
            "python scripts/check_real_gui_render_artifact.py --artifact-dir",
            "--require-pyqt6",
            "--timeout-seconds",
            "real GUI render smoke",
        ),
        "docs/GUI_DESIGN.md": (
            "python scripts/verify.py --require-real-gui",
            "python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 240",
            "python scripts/check_real_gui_render_artifact.py --artifact-dir",
            "artifacts/gui-real",
            "all-preset gate",
        ),
    }
    for doc_path, snippets in required_doc_snippets.items():
        text = doc_sources.get(doc_path, "")
        for snippet in snippets:
            if snippet not in text:
                errors.append(f"GUI parity live render proof docs missing {doc_path}: {snippet}")
    return errors


def workflow_job_block(workflow: str, job_name: str) -> str:
    marker = f"  {job_name}:\n"
    start = workflow.find(marker)
    if start < 0:
        return ""
    tail = workflow[start + len(marker):]
    next_job = len(tail)
    for index in range(1, len(tail)):
        if tail[index - 1] == "\n" and tail.startswith("  ", index) and not tail.startswith("    ", index):
            next_job = index - 1
            break
    return tail[:next_job]


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


def check_parity_target(
    criteria: dict[str, Any],
    visual_metrics: dict[str, Any] | None = None,
    preview_manifest: dict[str, Any] | None = None,
    workflow_text: str | None = None,
    verifier_source: str | None = None,
    docs: dict[str, str] | None = None,
) -> list[str]:
    report = gui_parity_report(
        criteria,
        visual_metrics,
        preview_manifest,
        workflow_text=workflow_text,
        verifier_source=verifier_source,
        docs=docs,
    )
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
        if int(row.get("reference_dimension_count", 0)) and float(row["reference_dimension_percent"]) < target:
            label = row.get("preset_id", "overall")
            errors.append(
                f"{label} GUI reference-view dimensions are {row['reference_dimension_percent']}%, "
                f"expected {row['target_percent']}%"
            )
        if int(row.get("reference_visual_count", 0)) and float(row["reference_visual_percent"]) < target:
            label = row.get("preset_id", "overall")
            errors.append(
                f"{label} GUI reference-view measured visual evidence is {row['reference_visual_percent']}%, "
                f"expected {row['target_percent']}%"
            )
        if int(row.get("reference_contract_count", 0)) and float(row["reference_contract_percent"]) < target:
            label = row.get("preset_id", "overall")
            errors.append(
                f"{label} GUI reference-view static/live contract evidence is "
                f"{row['reference_contract_percent']}%, expected {row['target_percent']}%"
            )
        if int(row.get("reference_policy_count", 0)) and float(row["reference_policy_percent"]) < target:
            label = row.get("preset_id", "overall")
            errors.append(
                f"{label} GUI reference-view sanitized policy evidence is "
                f"{row['reference_policy_percent']}%, expected {row['target_percent']}%"
            )
        if int(row.get("live_render_proof_count", 0)) and float(row["live_render_proof_percent"]) < target:
            label = row.get("preset_id", "overall")
            errors.append(
                f"{label} GUI strict live-render proof is "
                f"{row['live_render_proof_percent']}%, expected {row['target_percent']}%"
            )
    return errors


def gui_parity_report(
    criteria: dict[str, Any],
    visual_metrics: dict[str, Any] | None = None,
    preview_manifest: dict[str, Any] | None = None,
    workflow_text: str | None = None,
    verifier_source: str | None = None,
    docs: dict[str, str] | None = None,
) -> dict[str, Any]:
    target = float(criteria.get("target_percent", 100))
    dimensions = required_dimensions(criteria)
    presets = criteria.get("presets", {})
    metrics = visual_metrics if isinstance(visual_metrics, dict) else load_json(METRICS_PATH)
    manifest = preview_manifest if isinstance(preview_manifest, dict) else load_json(PREVIEW_MANIFEST_PATH)
    live_contract_source = (ROOT / "scripts" / "check_real_gui_render.py").read_text(encoding="utf-8")
    live_contract_summaries = load_live_contract_summaries()
    rows: list[dict[str, Any]] = []
    total_count = 0
    total_met = 0
    total_dimension_count = 0
    total_dimensions_met = 0
    total_reference_view_count = 0
    total_reference_dimension_count = 0
    total_reference_dimensions_met = 0
    total_reference_visual_count = 0
    total_reference_visual_met = 0
    total_reference_contract_count = 0
    total_reference_contract_met = 0
    total_reference_policy_count = 0
    total_reference_policy_met = 0
    live_render_proof_ok = not check_live_render_proof_contract(
        criteria,
        workflow_text=workflow_text,
        verifier_source=verifier_source,
        docs=docs,
    )
    total_live_render_proof_count = 0
    total_live_render_proof_met = 0
    if isinstance(presets, dict):
        for preset_id in sorted(presets):
            preset_data = presets[preset_id]
            requirements = preset_data.get("requirements", []) if isinstance(preset_data, dict) else []
            count = len(requirements) if isinstance(requirements, list) else 0
            met = sum(1 for requirement in requirements if requirement_satisfied(requirement)) if isinstance(requirements, list) else 0
            dimension_count, dimensions_met = dimension_counts(preset_data, dimensions)
            reference_view_count, reference_dimension_count, reference_dimensions_met = reference_view_counts(
                preset_data,
                dimensions,
            )
            reference_visual_count, reference_visual_met = reference_visual_counts(
                preset_id,
                preset_data,
                metrics,
                manifest,
            )
            reference_contract_count, reference_contract_met = reference_contract_counts(
                preset_id,
                preset_data,
                manifest,
                live_contract_source,
                live_contract_summaries,
            )
            reference_policy_count, reference_policy_met = reference_policy_counts(preset_data)
            live_render_proof_count, live_render_proof_met = live_render_proof_counts(
                preset_id,
                live_render_proof_ok,
            )
            rows.append(
                parity_row(
                    preset_id,
                    count,
                    met,
                    target,
                    dimension_count,
                    dimensions_met,
                    reference_view_count,
                    reference_dimension_count,
                    reference_dimensions_met,
                    reference_visual_count,
                    reference_visual_met,
                    reference_contract_count,
                    reference_contract_met,
                    reference_policy_count,
                    reference_policy_met,
                    live_render_proof_count,
                    live_render_proof_met,
                )
            )
            total_count += count
            total_met += met
            total_dimension_count += dimension_count
            total_dimensions_met += dimensions_met
            total_reference_view_count += reference_view_count
            total_reference_dimension_count += reference_dimension_count
            total_reference_dimensions_met += reference_dimensions_met
            total_reference_visual_count += reference_visual_count
            total_reference_visual_met += reference_visual_met
            total_reference_contract_count += reference_contract_count
            total_reference_contract_met += reference_contract_met
            total_reference_policy_count += reference_policy_count
            total_reference_policy_met += reference_policy_met
            total_live_render_proof_count += live_render_proof_count
            total_live_render_proof_met += live_render_proof_met
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
            total_reference_view_count,
            total_reference_dimension_count,
            total_reference_dimensions_met,
            total_reference_visual_count,
            total_reference_visual_met,
            total_reference_contract_count,
            total_reference_contract_met,
            total_reference_policy_count,
            total_reference_policy_met,
            total_live_render_proof_count,
            total_live_render_proof_met,
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
    reference_view_count: int = 0,
    reference_dimension_count: int = 0,
    reference_dimensions_met: int = 0,
    reference_visual_count: int = 0,
    reference_visual_met: int = 0,
    reference_contract_count: int = 0,
    reference_contract_met: int = 0,
    reference_policy_count: int = 0,
    reference_policy_met: int = 0,
    live_render_proof_count: int = 0,
    live_render_proof_met: int = 0,
) -> dict[str, Any]:
    current = (requirements_met / requirement_count * 100.0) if requirement_count else 0.0
    gap = max(target_percent - current, 0.0)
    dimension_current = (dimensions_met / dimension_count * 100.0) if dimension_count else 0.0
    dimension_gap = max(target_percent - dimension_current, 0.0) if dimension_count else 0.0
    reference_dimension_current = (
        reference_dimensions_met / reference_dimension_count * 100.0
        if reference_dimension_count
        else 0.0
    )
    reference_dimension_gap = (
        max(target_percent - reference_dimension_current, 0.0)
        if reference_dimension_count
        else 0.0
    )
    reference_visual_current = (
        reference_visual_met / reference_visual_count * 100.0
        if reference_visual_count
        else 0.0
    )
    reference_visual_gap = (
        max(target_percent - reference_visual_current, 0.0)
        if reference_visual_count
        else 0.0
    )
    reference_contract_current = (
        reference_contract_met / reference_contract_count * 100.0
        if reference_contract_count
        else 0.0
    )
    reference_contract_gap = (
        max(target_percent - reference_contract_current, 0.0)
        if reference_contract_count
        else 0.0
    )
    reference_policy_current = (
        reference_policy_met / reference_policy_count * 100.0
        if reference_policy_count
        else 0.0
    )
    reference_policy_gap = (
        max(target_percent - reference_policy_current, 0.0)
        if reference_policy_count
        else 0.0
    )
    live_render_proof_current = (
        live_render_proof_met / live_render_proof_count * 100.0
        if live_render_proof_count
        else 0.0
    )
    live_render_proof_gap = (
        max(target_percent - live_render_proof_current, 0.0)
        if live_render_proof_count
        else 0.0
    )
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
        "reference_view_count": reference_view_count,
        "reference_dimensions_met": reference_dimensions_met,
        "reference_dimension_count": reference_dimension_count,
        "reference_dimension_percent": round(reference_dimension_current, 1),
        "reference_dimension_gap_percent": round(reference_dimension_gap, 1),
        "reference_visual_met": reference_visual_met,
        "reference_visual_count": reference_visual_count,
        "reference_visual_percent": round(reference_visual_current, 1),
        "reference_visual_gap_percent": round(reference_visual_gap, 1),
        "reference_contract_met": reference_contract_met,
        "reference_contract_count": reference_contract_count,
        "reference_contract_percent": round(reference_contract_current, 1),
        "reference_contract_gap_percent": round(reference_contract_gap, 1),
        "reference_policy_met": reference_policy_met,
        "reference_policy_count": reference_policy_count,
        "reference_policy_percent": round(reference_policy_current, 1),
        "reference_policy_gap_percent": round(reference_policy_gap, 1),
        "live_render_proof_met": live_render_proof_met,
        "live_render_proof_count": live_render_proof_count,
        "live_render_proof_percent": round(live_render_proof_current, 1),
        "live_render_proof_gap_percent": round(live_render_proof_gap, 1),
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


def reference_view_counts(preset_data: Any, dimensions: list[str]) -> tuple[int, int, int]:
    if not isinstance(preset_data, dict):
        return 0, len(dimensions), 0
    reference_views = preset_data.get("reference_views", [])
    if not isinstance(reference_views, list):
        return 0, len(dimensions), 0
    expected_dimensions = set(dimensions)
    covered: set[str] = set()
    view_count = 0
    for view in reference_views:
        if not isinstance(view, dict):
            continue
        view_count += 1
        view_dimensions = view.get("dimensions", [])
        if isinstance(view_dimensions, list):
            actual_dimensions = {
                str(dimension)
                for dimension in view_dimensions
                if isinstance(dimension, str) and dimension in expected_dimensions
            }
            if not check_reference_view_dimension_evidence(
                str(view.get("id", "reference-view")),
                view,
                actual_dimensions,
            ):
                covered.update(actual_dimensions)
    return view_count, len(dimensions), len(covered & expected_dimensions)


def reference_visual_counts(
    preset_id: str,
    preset_data: Any,
    visual_metrics: dict[str, Any],
    preview_manifest: dict[str, Any],
) -> tuple[int, int]:
    if not isinstance(preset_data, dict):
        return 0, 0
    reference_views = preset_data.get("reference_views", [])
    if not isinstance(reference_views, list):
        return 0, 0
    view_count = 0
    valid_count = 0
    for view in reference_views:
        if not isinstance(view, dict):
            continue
        view_count += 1
        if not check_reference_view_visual_evidence(preset_id, view, visual_metrics, preview_manifest):
            valid_count += 1
    return view_count, valid_count


def reference_contract_counts(
    preset_id: str,
    preset_data: Any,
    preview_manifest: dict[str, Any],
    live_contract_source: str,
    live_contract_summaries: dict[str, Any],
) -> tuple[int, int]:
    if not isinstance(preset_data, dict):
        return 0, 0
    reference_views = preset_data.get("reference_views", [])
    if not isinstance(reference_views, list):
        return 0, 0
    view_count = 0
    valid_count = 0
    for view in reference_views:
        if not isinstance(view, dict):
            continue
        view_count += 1
        if not check_reference_view_contract_evidence(
            preset_id,
            view,
            preview_manifest,
            live_contract_source,
            live_contract_summaries,
        ):
            valid_count += 1
    return view_count, valid_count


def reference_policy_counts(preset_data: Any) -> tuple[int, int]:
    if not isinstance(preset_data, dict):
        return 0, 0
    reference_views = preset_data.get("reference_views", [])
    if not isinstance(reference_views, list):
        return 0, 0
    view_count = 0
    valid_count = 0
    for view in reference_views:
        if not isinstance(view, dict):
            continue
        view_count += 1
        if not check_reference_view_policy(str(view.get("id", "reference-view")), view):
            valid_count += 1
    return view_count, valid_count


def live_render_proof_counts(preset_id: str, live_render_proof_ok: bool) -> tuple[int, int]:
    if preset_id not in PRODUCT_STYLE_PRESETS:
        return 0, 0
    return 1, 1 if live_render_proof_ok else 0


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
        (
            "GUI reference-view dimensions: "
            f"{overall['reference_dimension_percent']:.1f}% target {overall['target_percent']:.1f}% "
            f"({overall['reference_dimension_gap_percent']:.1f}% gap)"
        ),
        (
            "GUI reference-view measured visuals: "
            f"{overall['reference_visual_percent']:.1f}% target {overall['target_percent']:.1f}% "
            f"({overall['reference_visual_gap_percent']:.1f}% gap)"
        ),
        (
            "GUI reference-view static/live contracts: "
            f"{overall['reference_contract_percent']:.1f}% target {overall['target_percent']:.1f}% "
            f"({overall['reference_contract_gap_percent']:.1f}% gap)"
        ),
        (
            "GUI reference-view sanitized policy: "
            f"{overall['reference_policy_percent']:.1f}% target {overall['target_percent']:.1f}% "
            f"({overall['reference_policy_gap_percent']:.1f}% gap)"
        ),
        (
            "GUI strict live-render proof: "
            f"{overall['live_render_proof_percent']:.1f}% target {overall['target_percent']:.1f}% "
            f"({overall['live_render_proof_gap_percent']:.1f}% gap)"
        ),
    ]
    for row in report["presets"]:
        lines.append(
            f"  {row['preset_id']:<10} {row['current_percent']:.1f}% "
            f"({row['requirements_met']}/{row['requirement_count']} requirements), "
            f"{row['dimension_percent']:.1f}% dimensions "
            f"({row['dimensions_met']}/{row['dimension_count']}), "
            f"{row['reference_dimension_percent']:.1f}% reference dims "
            f"({row['reference_dimensions_met']}/{row['reference_dimension_count']}), "
            f"{row['reference_visual_percent']:.1f}% measured refs "
            f"({row['reference_visual_met']}/{row['reference_visual_count']}), "
            f"{row['reference_contract_percent']:.1f}% contracts "
            f"({row['reference_contract_met']}/{row['reference_contract_count']}), "
            f"{row['reference_policy_percent']:.1f}% policy "
            f"({row['reference_policy_met']}/{row['reference_policy_count']}), "
            f"{row['live_render_proof_percent']:.1f}% live proof "
            f"({row['live_render_proof_met']}/{row['live_render_proof_count']})"
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


def preview_manifest_entry(manifest: dict[str, Any], preset_id: str) -> dict[str, Any] | None:
    presets = manifest.get("presets", [])
    if not isinstance(presets, list):
        return None
    for item in presets:
        if isinstance(item, dict) and str(item.get("id", "")) == preset_id:
            return item
    return None


def reference_view_manifest_image(
    manifest: dict[str, Any],
    collection: str,
    metrics_id: str,
) -> dict[str, Any] | None:
    collection_key = "presets" if collection == "presets" else "state_previews"
    items = manifest.get(collection_key, [])
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or str(item.get("id", "")) != metrics_id:
            continue
        image = item.get("image")
        return image if isinstance(image, dict) else None
    return None


def load_live_contract_summaries() -> dict[str, Any]:
    module_path = ROOT / "scripts" / "check_real_gui_render.py"
    spec = importlib.util.spec_from_file_location("remote_ops_check_real_gui_render", module_path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    summaries = module.live_contract_summaries_for_presets(sorted(PRODUCT_STYLE_PRESETS))
    return summaries if isinstance(summaries, dict) else {}


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

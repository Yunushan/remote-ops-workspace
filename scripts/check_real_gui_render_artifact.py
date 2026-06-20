from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.gui_designs import GUI_DESIGN_PRESETS  # noqa: E402

MANIFEST_NAME = "real-gui-render-manifest.json"
RENDERER = "scripts/check_real_gui_render.py"
CAPTURE_MODE = "live-pyqt6-offscreen"
PRODUCT_STYLE_PRESETS = {"mobaxterm", "securecrt", "termius", "remmina", "mremoteng"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IHDR_LENGTH = 13
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate live PyQt6 GUI screenshot artifacts.")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Directory containing real-gui-render-manifest.json and live PNG captures.",
    )
    parser.add_argument(
        "--contract",
        action="store_true",
        help="Validate the repository contract for producing and checking live GUI render artifacts.",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    if args.contract:
        errors.extend(check_repository_contract())
    if args.artifact_dir is not None:
        errors.extend(check_real_gui_render_artifact(args.artifact_dir))
    if not args.contract and args.artifact_dir is None:
        errors.append("pass --contract or --artifact-dir")

    if errors:
        for error in errors:
            print(f"real GUI render artifact: {error}", file=sys.stderr)
        return 1
    print("real GUI render artifact checks passed")
    return 0


def check_repository_contract() -> list[str]:
    errors: list[str] = []
    render_source = (ROOT / "scripts" / "check_real_gui_render.py").read_text(encoding="utf-8")
    verifier_source = (ROOT / "scripts" / "verify.py").read_text(encoding="utf-8")
    workflow_source = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    docs_source = (ROOT / "docs" / "GUI_DESIGN.md").read_text(encoding="utf-8")
    required_render_snippets = {
        f'MANIFEST_NAME = "{MANIFEST_NAME}"': "stable manifest filename",
        '"schema_version": 1': "manifest schema version",
        f'"renderer": "{RENDERER}"': "manifest renderer identity",
        f'"capture_mode": "{CAPTURE_MODE}"': "manifest capture mode",
        "DEFAULT_RENDER_TIMEOUT_SECONDS = 240": "bounded renderer timeout default",
        "def run_render_child": "renderer subprocess timeout guard",
        "subprocess.run": "renderer subprocess timeout execution",
        "def render_child_command": "renderer child command builder",
        "--render-child": "renderer child-process guard flag",
        "--timeout-seconds": "renderer timeout CLI option",
        "timed out after": "renderer timeout failure message",
        '"captures": [capture.to_dict() for capture in captures]': "capture list payload",
        '"sha256"': "per-capture sha256 payload",
        "measured_contract_evidence_complete": "measured contract audit payload",
    }
    for snippet, label in required_render_snippets.items():
        if snippet not in render_source:
            errors.append(f"renderer missing {label}: {snippet}")
    required_workflow_snippets = {
        "python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 240 --out-dir artifacts/gui-real": (
            "strict bounded live render artifact command"
        ),
        "Validate real GUI render artifact": "artifact validation step",
        "python scripts/check_real_gui_render_artifact.py --artifact-dir artifacts/gui-real": (
            "artifact validator command"
        ),
        "name: gui-real-render": "stable artifact upload name",
        "path: artifacts/gui-real/*": "uploaded live render artifact directory",
        "if-no-files-found: error": "artifact upload failure on missing screenshots",
    }
    for snippet, label in required_workflow_snippets.items():
        if snippet not in workflow_source:
            errors.append(f"ci workflow missing {label}: {snippet}")
    required_verifier_snippets = {
        "scripts/check_real_gui_render_artifact.py": "artifact validator in local verifier",
        "--contract": "artifact validator contract mode",
    }
    for snippet, label in required_verifier_snippets.items():
        if snippet not in verifier_source:
            errors.append(f"verifier missing {label}: {snippet}")
    if "check_real_gui_render_artifact.py --artifact-dir" not in docs_source:
        errors.append("GUI design docs missing artifact validator command")
    return errors


def check_real_gui_render_artifact(artifact_dir: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = artifact_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return [f"manifest missing: {display(manifest_path)}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"cannot parse manifest {display(manifest_path)}: {exc}"]
    if not isinstance(manifest, dict):
        return [f"manifest must be an object: {display(manifest_path)}"]
    errors.extend(check_manifest_contract(manifest))
    errors.extend(check_capture_artifacts(artifact_dir, manifest))
    return errors


def check_manifest_contract(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_preset_ids = expected_all_preset_ids()
    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version must be 1")
    if manifest.get("renderer") != RENDERER:
        errors.append(f"manifest renderer must be {RENDERER}")
    if manifest.get("capture_mode") != CAPTURE_MODE:
        errors.append(f"manifest capture_mode must be {CAPTURE_MODE}")
    for key in ("selected_preset_ids", "captured_preset_ids"):
        if manifest.get(key) != expected_preset_ids:
            errors.append(f"manifest {key} must equal {expected_preset_ids}")
    if manifest.get("expected_capture_count") != len(expected_preset_ids):
        errors.append("manifest expected_capture_count must match all GUI presets")
    if manifest.get("actual_capture_count") != len(expected_preset_ids):
        errors.append("manifest actual_capture_count must match all GUI presets")
    if manifest.get("complete_preset_capture") is not True:
        errors.append("manifest complete_preset_capture must be true")
    for key in ("missing_capture_preset_ids", "extra_capture_preset_ids"):
        if manifest.get(key) != []:
            errors.append(f"manifest {key} must be empty")
    product_style_ids = set(manifest.get("product_style_presets", []))
    if product_style_ids != PRODUCT_STYLE_PRESETS:
        errors.append(f"manifest product_style_presets must equal {sorted(PRODUCT_STYLE_PRESETS)}")
    measured_required_ids = set(manifest.get("measured_contract_evidence_required_preset_ids", []))
    if measured_required_ids != PRODUCT_STYLE_PRESETS:
        errors.append("manifest measured contract evidence must require every product-style preset")
    if manifest.get("measured_contract_evidence_complete") is not True:
        errors.append("manifest measured_contract_evidence_complete must be true")
    for key in (
        "missing_contract_evidence_preset_ids",
        "incomplete_contract_evidence_preset_ids",
        "failed_contract_evidence_preset_ids",
    ):
        if manifest.get(key) != []:
            errors.append(f"manifest {key} must be empty")
    summaries = manifest.get("preset_live_contracts")
    if not isinstance(summaries, dict):
        errors.append("manifest preset_live_contracts must be an object")
    else:
        missing_summaries = sorted(PRODUCT_STYLE_PRESETS - set(summaries))
        if missing_summaries:
            errors.append(f"manifest preset_live_contracts missing product presets: {missing_summaries}")
    captures = manifest.get("captures")
    if not isinstance(captures, list) or len(captures) != len(expected_preset_ids):
        errors.append("manifest captures must include exactly one item per GUI preset")
    return errors


def check_capture_artifacts(artifact_dir: Path, manifest: dict[str, Any]) -> list[str]:
    captures = manifest.get("captures")
    if not isinstance(captures, list):
        return []
    errors: list[str] = []
    expected_preset_ids = expected_all_preset_ids()
    seen_preset_ids: set[str] = set()
    minimum_size = manifest.get("minimum_capture_size", {})
    min_width = int(minimum_size.get("width", 1)) if isinstance(minimum_size, dict) else 1
    min_height = int(minimum_size.get("height", 1)) if isinstance(minimum_size, dict) else 1
    for capture in captures:
        if not isinstance(capture, dict):
            errors.append("manifest capture entries must be objects")
            continue
        preset_id = str(capture.get("preset_id", ""))
        if preset_id not in expected_preset_ids:
            errors.append(f"capture preset_id is not expected: {preset_id}")
        if preset_id in seen_preset_ids:
            errors.append(f"duplicate capture preset_id: {preset_id}")
        seen_preset_ids.add(preset_id)
        errors.extend(check_capture_metrics(preset_id, capture.get("metrics"), min_width, min_height))
        errors.extend(check_capture_file(artifact_dir, preset_id, capture, min_width, min_height))
        if preset_id in PRODUCT_STYLE_PRESETS:
            errors.extend(check_capture_contract_evidence(preset_id, capture.get("contract_evidence")))
    missing_captures = sorted(set(expected_preset_ids) - seen_preset_ids)
    if missing_captures:
        errors.append(f"manifest captures missing presets: {missing_captures}")
    return errors


def check_capture_metrics(preset_id: str, metrics: Any, min_width: int, min_height: int) -> list[str]:
    if not isinstance(metrics, dict):
        return [f"{preset_id} capture metrics must be an object"]
    errors: list[str] = []
    if int(metrics.get("width", 0)) < min_width:
        errors.append(f"{preset_id} capture width must be at least {min_width}")
    if int(metrics.get("height", 0)) < min_height:
        errors.append(f"{preset_id} capture height must be at least {min_height}")
    if int(metrics.get("sampled_pixels", 0)) <= 0:
        errors.append(f"{preset_id} capture sampled_pixels must be positive")
    if int(metrics.get("distinct_colors", 0)) < 2:
        errors.append(f"{preset_id} capture distinct_colors must be at least 2")
    if int(metrics.get("luminance_range", 0)) <= 0:
        errors.append(f"{preset_id} capture luminance_range must be positive")
    if float(metrics.get("non_background_ratio", 0.0)) <= 0.0:
        errors.append(f"{preset_id} capture non_background_ratio must be positive")
    return errors


def check_capture_file(
    artifact_dir: Path,
    preset_id: str,
    capture: dict[str, Any],
    min_width: int,
    min_height: int,
) -> list[str]:
    errors: list[str] = []
    raw_path = str(capture.get("path", ""))
    expected_name = f"{preset_id}-live.png"
    if not raw_path or Path(raw_path).name != raw_path:
        return [f"{preset_id} capture path must be a file name"]
    if raw_path != expected_name:
        errors.append(f"{preset_id} capture path must be {expected_name}")
    path = artifact_dir / raw_path
    if not path.is_file():
        return [*errors, f"{preset_id} capture file missing: {display(path)}"]
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        errors.append(f"{preset_id} capture file must be a PNG")
    dimensions = png_dimensions(data)
    if dimensions is None:
        errors.append(f"{preset_id} capture file must have readable PNG IHDR dimensions")
    else:
        actual_width, actual_height = dimensions
        if actual_width < min_width:
            errors.append(f"{preset_id} capture file width must be at least {min_width}")
        if actual_height < min_height:
            errors.append(f"{preset_id} capture file height must be at least {min_height}")
        metrics = capture.get("metrics")
        if isinstance(metrics, dict):
            metric_width = int_or_none(metrics.get("width"))
            metric_height = int_or_none(metrics.get("height"))
            if metric_width is not None and actual_width != metric_width:
                errors.append(f"{preset_id} capture file width does not match metrics width")
            if metric_height is not None and actual_height != metric_height:
                errors.append(f"{preset_id} capture file height does not match metrics height")
    size_bytes = capture.get("size_bytes")
    if not isinstance(size_bytes, int) or size_bytes <= 0:
        errors.append(f"{preset_id} capture size_bytes must be positive")
    elif len(data) != size_bytes:
        errors.append(f"{preset_id} capture size_bytes does not match file size")
    sha256 = str(capture.get("sha256", ""))
    if not SHA256_RE.fullmatch(sha256):
        errors.append(f"{preset_id} capture sha256 must be lowercase hex")
    elif hashlib.sha256(data).hexdigest() != sha256:
        errors.append(f"{preset_id} capture sha256 does not match file")
    return errors


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 33 or not data.startswith(PNG_SIGNATURE):
        return None
    ihdr_length = int.from_bytes(data[8:12], "big")
    if ihdr_length != PNG_IHDR_LENGTH or data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def check_capture_contract_evidence(preset_id: str, evidence: Any) -> list[str]:
    if not isinstance(evidence, dict):
        return [f"{preset_id} capture contract_evidence must be an object"]
    errors: list[str] = []
    for key in ("layout_measurements", "topology_measurements"):
        measurements = evidence.get(key)
        if not isinstance(measurements, list) or not measurements:
            errors.append(f"{preset_id} capture contract_evidence {key} must be a non-empty list")
            continue
        for item in measurements:
            if not isinstance(item, dict):
                errors.append(f"{preset_id} capture contract_evidence {key} entries must be objects")
                continue
            if not str(item.get("id", "")):
                errors.append(f"{preset_id} capture contract_evidence {key} entry missing id")
            if item.get("passed") is not True:
                errors.append(f"{preset_id} capture contract_evidence {key} entry must pass")
    return errors


def expected_all_preset_ids() -> list[str]:
    return [preset.id for preset in GUI_DESIGN_PRESETS]


def display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

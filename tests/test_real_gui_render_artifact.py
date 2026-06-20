from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_BYTES = b""


def test_real_gui_render_artifact_contract_passes() -> None:
    checker = _load_checker()

    assert checker.main(["--contract"]) == 0


def test_real_gui_render_artifact_accepts_complete_artifact(tmp_path: Path) -> None:
    checker = _load_checker()
    manifest = _write_complete_artifact(checker, tmp_path)

    errors = checker.check_real_gui_render_artifact(tmp_path)

    assert errors == []
    assert manifest["complete_preset_capture"] is True


def test_real_gui_render_artifact_rejects_missing_product_capture(tmp_path: Path) -> None:
    checker = _load_checker()
    manifest = _write_complete_artifact(checker, tmp_path)
    manifest["captures"] = [
        capture for capture in manifest["captures"] if capture["preset_id"] != "mobaxterm"
    ]
    manifest["captured_preset_ids"] = [
        preset_id for preset_id in manifest["captured_preset_ids"] if preset_id != "mobaxterm"
    ]
    manifest["actual_capture_count"] -= 1
    (tmp_path / checker.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_real_gui_render_artifact(tmp_path)

    assert any("actual_capture_count must match all GUI presets" in error for error in errors)
    assert any("captures must include exactly one item per GUI preset" in error for error in errors)
    assert any("captures missing presets: ['mobaxterm']" in error for error in errors)


def test_real_gui_render_artifact_rejects_sha_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_complete_artifact(checker, tmp_path)
    (tmp_path / "securecrt-live.png").write_bytes(PNG_BYTES + b"-changed")

    errors = checker.check_real_gui_render_artifact(tmp_path)

    assert any("securecrt capture size_bytes does not match file size" in error for error in errors)
    assert any("securecrt capture sha256 does not match file" in error for error in errors)


def test_real_gui_render_artifact_rejects_png_signature_without_dimensions(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_complete_artifact(checker, tmp_path)
    data = PNG_SIGNATURE + b"not-a-readable-ihdr"
    securecrt = tmp_path / "securecrt-live.png"
    securecrt.write_bytes(data)
    _rewrite_capture_digest(checker, tmp_path, "securecrt", data)

    errors = checker.check_real_gui_render_artifact(tmp_path)

    assert any("securecrt capture file must have readable PNG IHDR dimensions" in error for error in errors)


def test_real_gui_render_artifact_rejects_file_dimension_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_complete_artifact(checker, tmp_path)
    data = _png_bytes(1280, 820)
    securecrt = tmp_path / "securecrt-live.png"
    securecrt.write_bytes(data)
    _rewrite_capture_digest(checker, tmp_path, "securecrt", data)

    errors = checker.check_real_gui_render_artifact(tmp_path)

    assert any("securecrt capture file width does not match metrics width" in error for error in errors)


def _write_complete_artifact(checker, root: Path) -> dict[str, object]:
    preset_ids = checker.expected_all_preset_ids()
    captures = [_capture_record(checker, root, preset_id) for preset_id in preset_ids]
    manifest: dict[str, object] = {
        "schema_version": 1,
        "renderer": checker.RENDERER,
        "capture_mode": checker.CAPTURE_MODE,
        "requested_window_size": {"width": 1420, "height": 820},
        "minimum_capture_size": {"width": 800, "height": 600},
        "selected_preset_ids": preset_ids,
        "captured_preset_ids": preset_ids,
        "expected_capture_count": len(preset_ids),
        "actual_capture_count": len(preset_ids),
        "complete_preset_capture": True,
        "missing_capture_preset_ids": [],
        "extra_capture_preset_ids": [],
        "measured_contract_evidence_required_preset_ids": sorted(checker.PRODUCT_STYLE_PRESETS),
        "measured_contract_evidence_complete": True,
        "missing_contract_evidence_preset_ids": [],
        "incomplete_contract_evidence_preset_ids": [],
        "failed_contract_evidence_preset_ids": [],
        "product_style_presets": sorted(checker.PRODUCT_STYLE_PRESETS),
        "preset_live_contracts": {preset_id: {} for preset_id in preset_ids},
        "captures": captures,
    }
    (root / checker.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _capture_record(checker, root: Path, preset_id: str) -> dict[str, object]:
    data = PNG_BYTES
    path = root / f"{preset_id}-live.png"
    path.write_bytes(data)
    capture: dict[str, object] = {
        "preset_id": preset_id,
        "preset_label": preset_id,
        "path": path.name,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "metrics": {
            "width": 1420,
            "height": 820,
            "sampled_pixels": 128,
            "distinct_colors": 42,
            "luminance_range": 80,
            "non_background_ratio": 0.25,
        },
    }
    if preset_id in checker.PRODUCT_STYLE_PRESETS:
        capture["contract_evidence"] = {
            "layout_measurements": [{"id": f"{preset_id}-layout", "passed": True}],
            "topology_measurements": [{"id": f"{preset_id}-topology", "passed": True}],
        }
    return capture


def _rewrite_capture_digest(checker, root: Path, preset_id: str, data: bytes) -> None:
    manifest_path = root / checker.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for capture in manifest["captures"]:
        if capture["preset_id"] == preset_id:
            capture["size_bytes"] = len(data)
            capture["sha256"] = hashlib.sha256(data).hexdigest()
            break
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _png_bytes(width: int, height: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + (b"\x11\x22\x33" * width)
    idat = zlib.compress(row * height, level=9)
    return PNG_SIGNATURE + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _load_checker():
    path = Path("scripts/check_real_gui_render_artifact.py")
    spec = importlib.util.spec_from_file_location("real_gui_render_artifact_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PNG_BYTES = _png_bytes(1420, 820)

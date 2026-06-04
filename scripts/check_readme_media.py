from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MEDIA_DIR = ROOT / "artifacts" / "readme"
MANIFEST_PATH = MEDIA_DIR / "readme-media-manifest.json"
README_PATH = ROOT / "README.md"
PREVIEW_CONTACT_SHEET = "artifacts/gui-design-previews/all-gui-designs-contact-sheet.png"
REQUIRED_ASSETS = {
    "artifacts/readme/remote-ops-hero.png": "png",
    "artifacts/readme/gui-preset-tour.gif": "gif",
    "artifacts/readme/feature-workflow-tour.gif": "gif",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
GIF_SIGNATURES = (b"GIF87a", b"GIF89a")


def main() -> int:
    errors = check_readme_media()
    if errors:
        for error in errors:
            print(f"README media: {error}", file=sys.stderr)
        return 1
    print("README media checks passed")
    return 0


def check_readme_media() -> list[str]:
    errors: list[str] = []
    if not MANIFEST_PATH.is_file():
        return [f"missing README media manifest: {display(MANIFEST_PATH)}"]
    if not README_PATH.is_file():
        return [f"missing README: {display(README_PATH)}"]

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"README media manifest is invalid JSON: {exc}"]

    errors.extend(check_manifest(manifest))
    errors.extend(check_readme_references(manifest))
    return errors


def check_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version must be 1")
    if manifest.get("renderer") != "scripts/render_readme_media.py":
        errors.append("manifest renderer must point at scripts/render_readme_media.py")
    if manifest.get("source_previews") != "artifacts/gui-design-previews/preview-manifest.json":
        errors.append("manifest source_previews must point at the GUI preview manifest")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        return [*errors, "manifest assets must be a list"]

    found = {str(item.get("path", "")): item for item in assets if isinstance(item, dict)}
    for path, kind in REQUIRED_ASSETS.items():
        item = found.get(path)
        if not item:
            errors.append(f"manifest missing asset: {path}")
            continue
        if item.get("kind") != kind:
            errors.append(f"{path} kind must be {kind}")
        errors.extend(check_asset(item))
    return errors


def check_asset(item: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    relative = str(item.get("path", ""))
    path = ROOT / relative
    if not path.is_file():
        return [f"asset missing: {relative}"]
    data = path.read_bytes()
    if item.get("size_bytes") != len(data):
        errors.append(f"{relative} size_bytes does not match file size")
    if item.get("sha256") != hashlib.sha256(data).hexdigest():
        errors.append(f"{relative} sha256 does not match file content")

    kind = str(item.get("kind", ""))
    try:
        if kind == "png":
            width, height = png_dimensions(data)
        elif kind == "gif":
            width, height = gif_dimensions(data)
            if int(item.get("frame_count", 0)) < 2:
                errors.append(f"{relative} must contain multiple GIF frames")
        else:
            return [*errors, f"{relative} has unsupported kind: {kind}"]
    except ValueError as exc:
        return [*errors, f"{relative} image header is invalid: {exc}"]

    if item.get("width") != width or item.get("height") != height:
        errors.append(f"{relative} manifest dimensions do not match image header")
    if width < 1000 or height < 600:
        errors.append(f"{relative} dimensions {(width, height)} are too small for README media")
    return errors


def check_readme_references(manifest: dict[str, Any]) -> list[str]:
    text = README_PATH.read_text(encoding="utf-8")
    errors: list[str] = []
    for path in REQUIRED_ASSETS:
        if path not in text:
            errors.append(f"README.md must reference {path}")
    if PREVIEW_CONTACT_SHEET not in text:
        errors.append(f"README.md must reference {PREVIEW_CONTACT_SHEET}")
    if "## Visual Overview" not in text:
        errors.append("README.md must include a Visual Overview section")
    assets = manifest.get("assets", [])
    if isinstance(assets, list):
        for item in assets:
            if isinstance(item, dict) and str(item.get("path", "")) not in text:
                errors.append(f"README.md missing manifest asset reference: {item.get('path', '')}")
    return errors


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != PNG_SIGNATURE:
        raise ValueError("not a PNG image")
    chunk_length = struct.unpack(">I", data[8:12])[0]
    chunk_type = data[12:16]
    if chunk_length != 13 or chunk_type != b"IHDR":
        raise ValueError("PNG missing IHDR chunk")
    return struct.unpack(">II", data[16:24])


def gif_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 10 or data[:6] not in GIF_SIGNATURES:
        raise ValueError("not a GIF image")
    return struct.unpack("<HH", data[6:10])


def display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

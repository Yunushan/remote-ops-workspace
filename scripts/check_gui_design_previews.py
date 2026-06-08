from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.gui_designs import GUI_DESIGN_PRESETS  # noqa: E402

PREVIEW_DIR = ROOT / "artifacts" / "gui-design-previews"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def main() -> int:
    errors = check_gui_design_previews()
    if errors:
        for error in errors:
            print(f"GUI preview workflow: {error}", file=sys.stderr)
        return 1
    print("GUI preview workflow passed")
    return 0


def check_gui_design_previews() -> list[str]:
    renderer = load_renderer()
    errors: list[str] = []
    manifest_path = PREVIEW_DIR / renderer.MANIFEST_NAME
    gallery_path = PREVIEW_DIR / renderer.GALLERY_NAME
    contact_path = PREVIEW_DIR / renderer.CONTACT_SHEET_NAME

    if not manifest_path.is_file():
        return [f"missing preview manifest: {display(manifest_path)}"]
    if not gallery_path.is_file():
        errors.append(f"missing preview gallery: {display(gallery_path)}")
    if not contact_path.is_file():
        errors.append(f"missing contact sheet: {display(contact_path)}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"preview manifest is invalid JSON: {exc}"]

    errors.extend(check_manifest_shape(manifest, renderer))
    errors.extend(check_preset_images(manifest, renderer))
    errors.extend(check_state_preview_images(manifest, renderer))
    errors.extend(check_contact_sheet(manifest, contact_path))
    if gallery_path.is_file():
        errors.extend(check_gallery_links(manifest, gallery_path))
    return errors


def check_manifest_shape(manifest: dict[str, object], renderer) -> list[str]:  # type: ignore[no-untyped-def]
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("preview manifest schema_version must be 1")
    if manifest.get("renderer") != "scripts/render_gui_design_previews.py":
        errors.append("preview manifest renderer must point at scripts/render_gui_design_previews.py")
    expected_size = {"width": renderer.PREVIEW_SIZE[0], "height": renderer.PREVIEW_SIZE[1]}
    if manifest.get("preview_size") != expected_size:
        errors.append(f"preview manifest size must be {expected_size}")
    expected_ids = [preset.id for preset in GUI_DESIGN_PRESETS]
    manifest_presets = manifest.get("presets")
    if not isinstance(manifest_presets, list):
        return [*errors, "preview manifest presets must be a list"]
    found_ids = [str(item.get("id", "")) for item in manifest_presets if isinstance(item, dict)]
    if found_ids != expected_ids:
        errors.append(f"preview manifest preset ids {found_ids} must equal {expected_ids}")
    state_previews = manifest.get("state_previews")
    if not isinstance(state_previews, list):
        errors.append("preview manifest state_previews must be a list")
    else:
        state_ids = [str(item.get("id", "")) for item in state_previews if isinstance(item, dict)]
        if "mobaxterm-home" not in state_ids:
            errors.append("preview manifest must include mobaxterm-home state preview")
    return errors


def check_preset_images(manifest: dict[str, object], renderer) -> list[str]:  # type: ignore[no-untyped-def]
    errors: list[str] = []
    presets = manifest.get("presets", [])
    if not isinstance(presets, list):
        return ["preview manifest presets must be a list"]
    for item in presets:
        if not isinstance(item, dict):
            errors.append("preview manifest preset entry must be an object")
            continue
        image = item.get("image")
        if not isinstance(image, dict):
            errors.append(f"{item.get('id', '<unknown>')} missing image manifest")
            continue
        path = PREVIEW_DIR / str(image.get("path", ""))
        errors.extend(
            check_image_manifest(
                f"preset {item.get('id', '<unknown>')}",
                path,
                image,
                expected_size=renderer.PREVIEW_SIZE,
            )
        )
    return errors


def check_state_preview_images(manifest: dict[str, object], renderer) -> list[str]:  # type: ignore[no-untyped-def]
    errors: list[str] = []
    state_previews = manifest.get("state_previews", [])
    if not isinstance(state_previews, list):
        return ["preview manifest state_previews must be a list"]
    for item in state_previews:
        if not isinstance(item, dict):
            errors.append("preview manifest state preview entry must be an object")
            continue
        image = item.get("image")
        if not isinstance(image, dict):
            errors.append(f"{item.get('id', '<unknown>')} missing image manifest")
            continue
        path = PREVIEW_DIR / str(image.get("path", ""))
        errors.extend(
            check_image_manifest(
                f"state preview {item.get('id', '<unknown>')}",
                path,
                image,
                expected_size=renderer.PREVIEW_SIZE,
            )
        )
    return errors


def check_contact_sheet(manifest: dict[str, object], contact_path: Path) -> list[str]:
    contact = manifest.get("contact_sheet")
    if not isinstance(contact, dict):
        return ["preview manifest missing contact_sheet metadata"]
    return check_image_manifest("contact sheet", contact_path, contact, expected_size=None)


def check_image_manifest(
    label: str,
    path: Path,
    image: dict[str, object],
    *,
    expected_size: tuple[int, int] | None,
) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"{label} image missing: {display(path)}"]
    width, height = png_dimensions(path)
    if expected_size and (width, height) != expected_size:
        errors.append(f"{label} dimensions {(width, height)} must equal {expected_size}")
    if image.get("width") != width or image.get("height") != height:
        errors.append(f"{label} manifest dimensions do not match PNG header")
    size_bytes = path.stat().st_size
    if image.get("size_bytes") != size_bytes:
        errors.append(f"{label} manifest size_bytes does not match file size")
    sha256 = sha256_file(path)
    if image.get("sha256") != sha256:
        errors.append(f"{label} manifest sha256 does not match file content")
    return errors


def check_gallery_links(manifest: dict[str, object], gallery_path: Path) -> list[str]:
    text = gallery_path.read_text(encoding="utf-8")
    errors: list[str] = []
    contact = manifest.get("contact_sheet")
    if isinstance(contact, dict) and str(contact.get("path", "")) not in text:
        errors.append("preview gallery must link the contact sheet")
    presets = manifest.get("presets", [])
    state_previews = manifest.get("state_previews", [])
    for collection, label_key in ((presets, "preset label"), (state_previews, "state preview label")):
        if isinstance(collection, list):
            for item in collection:
                if not isinstance(item, dict):
                    continue
                image = item.get("image")
                if not isinstance(image, dict):
                    continue
                image_path = str(image.get("path", ""))
                label = str(item.get("label", ""))
                if image_path not in text:
                    errors.append(f"preview gallery must reference {image_path}")
                if label not in text:
                    errors.append(f"preview gallery must include {label_key} {label}")
    return errors


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != PNG_SIGNATURE:
        raise ValueError(f"not a PNG file: {display(path)}")
    chunk_length = struct.unpack(">I", data[8:12])[0]
    chunk_type = data[12:16]
    if chunk_length != 13 or chunk_type != b"IHDR":
        raise ValueError(f"PNG missing IHDR chunk: {display(path)}")
    return struct.unpack(">II", data[16:24])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_renderer():
    path = ROOT / "scripts" / "render_gui_design_previews.py"
    spec = importlib.util.spec_from_file_location("render_gui_design_previews_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

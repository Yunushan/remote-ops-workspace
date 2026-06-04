#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.features import coverage_report  # noqa: E402

PREVIEW_DIR = ROOT / "artifacts" / "gui-design-previews"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "readme"
MANIFEST_NAME = "readme-media-manifest.json"
HERO_NAME = "remote-ops-hero.png"
PRESET_TOUR_NAME = "gui-preset-tour.gif"
WORKFLOW_TOUR_NAME = "feature-workflow-tour.gif"
HERO_SIZE = (1600, 900)
GIF_SIZE = (1120, 680)
SCREENSHOT_SIZE = (1280, 760)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render premium README media from tracked GUI previews.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    if not ensure_pillow():
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    preview_manifest = load_preview_manifest()

    assets: list[dict[str, Any]] = []
    hero_path = args.out_dir / HERO_NAME
    preset_tour_path = args.out_dir / PRESET_TOUR_NAME
    workflow_tour_path = args.out_dir / WORKFLOW_TOUR_NAME

    render_hero(preview_manifest, hero_path)
    print(f"created {display(hero_path)}")
    assets.append(asset_manifest("hero", hero_path, kind="png", frame_count=1))

    render_preset_tour(preview_manifest, preset_tour_path)
    print(f"created {display(preset_tour_path)}")
    assets.append(asset_manifest("gui-preset-tour", preset_tour_path, kind="gif"))

    render_workflow_tour(preview_manifest, workflow_tour_path)
    print(f"created {display(workflow_tour_path)}")
    assets.append(asset_manifest("feature-workflow-tour", workflow_tour_path, kind="gif"))

    manifest = {
        "schema_version": 1,
        "renderer": "scripts/render_readme_media.py",
        "source_previews": "artifacts/gui-design-previews/preview-manifest.json",
        "assets": assets,
    }
    manifest_path = args.out_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"created {display(manifest_path)}")
    return 0


def ensure_pillow() -> bool:
    try:
        __import__("PIL.Image")
        __import__("PIL.ImageDraw")
        __import__("PIL.ImageFilter")
        __import__("PIL.ImageFont")
    except Exception as exc:
        print("Pillow is required to render README media.", file=sys.stderr)
        print(exc, file=sys.stderr)
        return False
    return True


def load_preview_manifest() -> dict[str, Any]:
    path = PREVIEW_DIR / "preview-manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def render_hero(preview_manifest: dict[str, Any], out_path: Path) -> None:
    from PIL import Image, ImageDraw

    image = vertical_gradient(HERO_SIZE, "#07111f", "#18233a")
    draw = ImageDraw.Draw(image)

    draw_glow(image, (1080, 235), 420, "#0f766e", opacity=68)
    draw_glow(image, (1340, 710), 300, "#1d4ed8", opacity=56)

    title_font = load_font(64, bold=True)
    body_font = load_font(22)
    chip_font = load_font(20, bold=True)
    small_font = load_font(16)

    draw.text((78, 72), "Remote Ops", font=title_font, fill="#f8fafc")
    draw.text((78, 142), "Workspace", font=title_font, fill="#f8fafc")
    draw_wrapped_text(
        draw,
        "Enterprise-grade remote access workspace for operators who need CLI, GUI, Web/PWA, secure profiles, split panes and protocol adapters in one open foundation.",
        (82, 238),
        body_font,
        "#cbd5e1",
        max_width=500,
        line_spacing=8,
    )

    chip_x = 82
    chip_y = 374
    for label in ("SSH", "RDP", "VNC", "SFTP", "Mosh", "Telnet", "Serial"):
        width = text_width(draw, label, chip_font) + 34
        if chip_x + width > 530:
            chip_x = 82
            chip_y += 58
        rounded(draw, (chip_x, chip_y, chip_x + width, chip_y + 46), radius=18, fill="#0f2537", outline="#27547a")
        draw.text((chip_x + 17, chip_y + 10), label, font=chip_font, fill="#dbeafe")
        chip_x += width + 12

    stats = [
        ("44", "feature families"),
        ("28", "product targets"),
        ("16", "platform targets"),
        ("3", "interfaces"),
    ]
    for index, (value, label) in enumerate(stats):
        x = 82 + (index % 2) * 250
        y = 530 + (index // 2) * 118
        rounded(draw, (x, y, x + 220, y + 92), radius=18, fill="#101b2c", outline="#334155")
        draw.text((x + 20, y + 14), value, font=load_font(34, bold=True), fill="#67e8f9")
        draw.text((x + 20, y + 56), label, font=small_font, fill="#cbd5e1")

    primary = preset_image(preview_manifest, "mobaxterm")
    secondary = preset_image(preview_manifest, "termius")
    tertiary = preset_image(preview_manifest, "remmina")

    draw_desktop_frame(image, tertiary, (840, 72, 1420, 417), title="Remote desktop profile view", opacity=190)
    draw_desktop_frame(image, secondary, (960, 562, 1510, 889), title="SSH-focused dark workspace", opacity=210)
    draw_desktop_frame(image, primary, (565, 182, 1515, 746), title="Dense operator console", opacity=255)

    ribbon = Image.new("RGBA", HERO_SIZE, (0, 0, 0, 0))
    ribbon_draw = ImageDraw.Draw(ribbon)
    rounded(ribbon_draw, (565, 770, 1515, 850), radius=22, fill="#020617dd", outline="#38bdf8")
    draw_wrapped_text(
        ribbon_draw,
        "Profiles, vault-backed launch planning, SFTP queue previews, split panes, audit logs and platform readiness are shown from generated repo assets.",
        (595, 790),
        load_font(22),
        "#e0f2fe",
        max_width=880,
        line_spacing=4,
    )
    image.alpha_composite(ribbon)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(out_path, "PNG", optimize=True)


def render_preset_tour(preview_manifest: dict[str, Any], out_path: Path) -> None:
    from PIL import Image, ImageDraw

    frames = []
    for item in preview_manifest["presets"]:
        frame = vertical_gradient(GIF_SIZE, "#08111f", "#172033")
        draw = ImageDraw.Draw(frame)
        label = str(item["label"])
        description = str(item["description"])
        draw.text((54, 34), "GUI preset tour", font=load_font(34, bold=True), fill="#f8fafc")
        draw.text((54, 78), label, font=load_font(24, bold=True), fill="#67e8f9")
        draw_wrapped_text(draw, description, (54, 112), load_font(18), "#cbd5e1", max_width=680, line_spacing=4)

        chip_y = 52
        chip_x = 780
        chips = [
            f"density: {item['density']}",
            f"tabs: {item['tab_position']}",
            f"profile: {item['profile_width']}px",
        ]
        for chip in chips:
            width = text_width(draw, chip, load_font(15, bold=True)) + 28
            rounded(draw, (chip_x, chip_y, chip_x + width, chip_y + 34), radius=13, fill="#0f2537", outline="#285a76")
            draw.text((chip_x + 14, chip_y + 8), chip, font=load_font(15, bold=True), fill="#dbeafe")
            chip_y += 42

        screenshot = preset_image(preview_manifest, str(item["id"]))
        draw_desktop_frame(frame, screenshot, (54, 168, 1066, 640), title=label, opacity=255)
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))

    save_gif(frames, out_path, duration=1350)


def render_workflow_tour(preview_manifest: dict[str, Any], out_path: Path) -> None:
    from PIL import Image

    screenshot = preset_image(preview_manifest, "native")
    report = coverage_report()
    steps = [
        (
            "Profile store + quick connect",
            "Groups, tags, imports and validated protocol options feed the same launch planner used by CLI and GUI.",
            [(30, 128, 328, 650), (248, 58, 362, 90)],
        ),
        (
            "Split terminal workspace",
            "Process-backed panes capture stdout/stderr, support managed lifecycle cleanup and preserve operator context.",
            [(350, 170, 1240, 610)],
        ),
        (
            "SFTP queue previews",
            "File transfer actions can be previewed before upload, download, rename or destructive remote operations run.",
            [(376, 58, 548, 90), (354, 626, 1238, 735)],
        ),
        (
            "Vault, audit and dry-run safety",
            "Secrets stay out of launch arguments, audit output is redacted, and commands can be inspected before execution.",
            [(354, 170, 1240, 610), (354, 626, 1238, 735)],
        ),
    ]

    frames = []
    for title, body, rects in steps:
        frame = workflow_base(title, body)
        screenshot_box = (54, 176, 1066, 626)
        framed_box = (54, 146, 1066, 640)
        draw_desktop_frame(frame, screenshot, framed_box, title="Live workspace surface", opacity=255)
        draw_highlights(frame, rects, screenshot_box)
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))

    frames.append(coverage_frame(report).convert("P", palette=Image.Palette.ADAPTIVE))
    save_gif(frames, out_path, duration=1450)


def workflow_base(title: str, body: str):
    from PIL import ImageDraw

    frame = vertical_gradient(GIF_SIZE, "#07111f", "#18233a")
    draw = ImageDraw.Draw(frame)
    draw.text((54, 34), title, font=load_font(32, bold=True), fill="#f8fafc")
    draw_wrapped_text(draw, body, (54, 78), load_font(18), "#cbd5e1", max_width=960, line_spacing=5)
    return frame


def coverage_frame(report: dict[str, Any]):
    from PIL import ImageDraw

    frame = vertical_gradient(GIF_SIZE, "#07111f", "#18233a")
    draw = ImageDraw.Draw(frame)
    draw.text((54, 40), "Coverage and platform truth", font=load_font(34, bold=True), fill="#f8fafc")
    draw_wrapped_text(
        draw,
        "The README shows adapter-ready and production-parity coverage separately from platform verification.",
        (54, 86),
        load_font(19),
        "#cbd5e1",
        max_width=900,
        line_spacing=5,
    )
    metrics = [
        ("Feature mapping", report["feature_family_mapping"]["overall"]["current_percent"], "#22c55e"),
        ("Adapter-ready", report["adapter_ready_coverage"]["overall"]["current_percent"], "#38bdf8"),
        ("Production parity", report["production_parity_coverage"]["overall"]["current_percent"], "#f59e0b"),
        ("Platform readiness", report["platform_verified_readiness"]["overall"]["current_percent"], "#a78bfa"),
    ]
    for index, (label, value, color) in enumerate(metrics):
        x = 72 + (index % 2) * 495
        y = 174 + (index // 2) * 172
        rounded(draw, (x, y, x + 450, y + 126), radius=24, fill="#0f172add", outline="#334155")
        draw.text((x + 28, y + 24), label, font=load_font(23, bold=True), fill="#f8fafc")
        draw.text((x + 28, y + 64), f"{value:.1f}%", font=load_font(39, bold=True), fill=color)
    rounded(draw, (72, 548, 1048, 625), radius=22, fill="#020617cc", outline="#38bdf8")
    draw.text((102, 570), "Generated by row features --coverage and checked in CI-style verification.", font=load_font(20), fill="#e0f2fe")
    return frame


def draw_desktop_frame(base, screenshot, box: tuple[int, int, int, int], *, title: str, opacity: int) -> None:
    from PIL import Image, ImageDraw

    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    shadow_box = (x1 + 14, y1 + 18, x2 + 14, y2 + 18)
    rounded(draw, shadow_box, radius=28, fill=(0, 0, 0, 70))
    rounded(draw, box, radius=24, fill=(6, 11, 22, opacity), outline="#475569")
    rounded(draw, (x1, y1, x2, y1 + 46), radius=24, fill="#0f172a", outline="#475569")
    draw.ellipse((x1 + 22, y1 + 17, x1 + 33, y1 + 28), fill="#ef4444")
    draw.ellipse((x1 + 42, y1 + 17, x1 + 53, y1 + 28), fill="#f59e0b")
    draw.ellipse((x1 + 62, y1 + 17, x1 + 73, y1 + 28), fill="#22c55e")
    draw.text((x1 + 94, y1 + 14), title, font=load_font(16, bold=True), fill="#cbd5e1")
    base.alpha_composite(layer)

    inner = fit_image(screenshot, (width - 24, height - 58))
    base.alpha_composite(inner, (x1 + 12, y1 + 46))


def draw_highlights(base, rects: list[tuple[int, int, int, int]], screenshot_box: tuple[int, int, int, int]) -> None:
    from PIL import Image, ImageDraw

    sx1, sy1, sx2, sy2 = screenshot_box
    display_w = sx2 - sx1
    display_h = sy2 - sy1
    scale_x = display_w / SCREENSHOT_SIZE[0]
    scale_y = display_h / SCREENSHOT_SIZE[1]
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x1, y1, x2, y2 in rects:
        box = (
            int(sx1 + x1 * scale_x),
            int(sy1 + y1 * scale_y),
            int(sx1 + x2 * scale_x),
            int(sy1 + y2 * scale_y),
        )
        rounded(draw, box, radius=18, fill=(56, 189, 248, 34), outline="#67e8f9", width=5)
    base.alpha_composite(overlay)


def preset_image(preview_manifest: dict[str, Any], preset_id: str):
    from PIL import Image

    for item in preview_manifest["presets"]:
        if item["id"] == preset_id:
            return Image.open(PREVIEW_DIR / item["image"]["path"]).convert("RGBA")
    raise ValueError(f"unknown preview preset: {preset_id}")


def vertical_gradient(size: tuple[int, int], top: str, bottom: str):
    from PIL import Image

    width, height = size
    top_rgb = hex_to_rgb(top)
    bottom_rgb = hex_to_rgb(bottom)
    image = Image.new("RGBA", size)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top_rgb[i] * (1 - ratio) + bottom_rgb[i] * ratio) for i in range(3))
        for x in range(width):
            pixels[x, y] = (*color, 255)
    return image


def draw_glow(base, center: tuple[int, int], radius: int, color: str, *, opacity: int) -> None:
    from PIL import Image, ImageDraw, ImageFilter

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(*hex_to_rgb(color), opacity))
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    base.alpha_composite(layer)


def fit_image(image, size: tuple[int, int]):
    from PIL import Image

    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    x = (size[0] - copy.width) // 2
    y = (size[1] - copy.height) // 2
    canvas.alpha_composite(copy, (x, y))
    return canvas


def rounded(draw, box, *, radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_wrapped_text(draw, text: str, xy: tuple[int, int], font, fill, *, max_width: int, line_spacing: int) -> None:
    x, y = xy
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if text_width(draw, candidate, font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += text_height(draw, line, font) + line_spacing


def text_width(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def text_height(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def load_font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    names = (
        ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    )
    paths = [Path("C:/Windows/Fonts") / name for name in names]
    for path in paths:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def save_gif(frames: list[Any], out_path: Path, *, duration: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out_path,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        optimize=True,
        disposal=2,
    )


def asset_manifest(asset_id: str, path: Path, *, kind: str, frame_count: int | None = None) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
        frames = frame_count if frame_count is not None else int(getattr(image, "n_frames", 1))
    data = path.read_bytes()
    return {
        "id": asset_id,
        "kind": kind,
        "path": display(path),
        "width": width,
        "height": height,
        "frame_count": frames,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from remote_ops_workspace.gui_designs import GUI_DESIGN_PRESETS, GuiDesignPreset, gui_design_preset_ids


PREVIEW_SIZE = (1280, 760)
CONTACT_THUMB = (600, 356)
CONTACT_SHEET_NAME = "all-gui-designs-contact-sheet.png"
GALLERY_NAME = "index.html"
MANIFEST_NAME = "preview-manifest.json"


@dataclass(slots=True)
class PreviewArtifact:
    path: Path
    png_bytes: bytes
    width: int
    height: int
    preset: GuiDesignPreset | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.png_bytes)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.png_bytes).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render static GUI design preset previews.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "artifacts" / "gui-design-previews",
        help="Directory for generated preview PNGs.",
    )
    parser.add_argument(
        "--preset",
        action="append",
        choices=gui_design_preset_ids(),
        help="Render only this preset id. Can be provided more than once.",
    )
    parser.add_argument("--list", action="store_true", help="List previewable preset ids and exit.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Render in memory and fail if tracked preview PNGs, manifest or gallery are stale.",
    )
    parser.add_argument("--no-contact-sheet", action="store_true", help="Do not write the contact sheet.")
    parser.add_argument("--no-gallery", action="store_true", help="Do not write the HTML preview gallery.")
    parser.add_argument("--no-manifest", action="store_true", help="Do not write preview-manifest.json.")
    args = parser.parse_args(argv)

    if args.list:
        for preset in GUI_DESIGN_PRESETS:
            print(f"{preset.id:<12} {preset.label:<18} {preset.description}")
        return 0

    if args.check and args.preset:
        print("--check validates the complete preview set; omit --preset", file=sys.stderr)
        return 2

    if not ensure_pillow():
        return 2

    selected = select_presets(args.preset)
    full_set = len(selected) == len(GUI_DESIGN_PRESETS)
    include_contact = full_set and not args.no_contact_sheet
    include_manifest = full_set and not args.no_manifest
    include_gallery = full_set and not args.no_gallery
    artifacts = render_artifacts(
        args.out_dir,
        selected,
        include_contact=include_contact,
    )
    manifest = build_manifest(artifacts) if include_manifest else None
    gallery = build_gallery_html(manifest) if manifest is not None and include_gallery else None

    if args.check:
        return check_outputs(args.out_dir, artifacts, manifest, gallery)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        artifact.path.write_bytes(artifact.png_bytes)
        print(f"created {display(artifact.path)}")

    if manifest is not None:
        manifest_path = args.out_dir / MANIFEST_NAME
        manifest_path.write_text(manifest_text(manifest), encoding="utf-8")
        print(f"created {display(manifest_path)}")
    if gallery is not None:
        gallery_path = args.out_dir / GALLERY_NAME
        gallery_path.write_text(gallery, encoding="utf-8")
        print(f"created {display(gallery_path)}")
    if not full_set:
        print("partial preset render: contact sheet, manifest and gallery were skipped")
    return 0


def ensure_pillow() -> bool:
    try:
        __import__("PIL.Image")
    except Exception as exc:
        print("Pillow is required to render GUI design previews.", file=sys.stderr)
        print(exc, file=sys.stderr)
        return False
    return True


def select_presets(ids: list[str] | None) -> list[GuiDesignPreset]:
    if not ids:
        return list(GUI_DESIGN_PRESETS)
    wanted = set(ids)
    return [preset for preset in GUI_DESIGN_PRESETS if preset.id in wanted]


def render_artifacts(
    out_dir: Path,
    presets: list[GuiDesignPreset],
    *,
    include_contact: bool,
) -> list[PreviewArtifact]:
    rendered: list[tuple[GuiDesignPreset, Any]] = []
    artifacts: list[PreviewArtifact] = []
    for preset in presets:
        image = render_preset(preset)
        rendered.append((preset, image))
        artifacts.append(
            PreviewArtifact(
                path=out_dir / f"{preset.id}.png",
                png_bytes=image_to_png_bytes(image),
                width=PREVIEW_SIZE[0],
                height=PREVIEW_SIZE[1],
                preset=preset,
            )
        )
    if include_contact:
        contact = render_contact_sheet(rendered)
        artifacts.append(
            PreviewArtifact(
                path=out_dir / CONTACT_SHEET_NAME,
                png_bytes=image_to_png_bytes(contact),
                width=contact.width,
                height=contact.height,
                preset=None,
            )
        )
    return artifacts


def image_to_png_bytes(image: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_manifest(artifacts: list[PreviewArtifact]) -> dict[str, Any]:
    preview_artifacts = [artifact for artifact in artifacts if artifact.preset is not None]
    contact_artifact = next((artifact for artifact in artifacts if artifact.preset is None), None)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "renderer": "scripts/render_gui_design_previews.py",
        "preview_size": {"width": PREVIEW_SIZE[0], "height": PREVIEW_SIZE[1]},
        "contact_thumb": {"width": CONTACT_THUMB[0], "height": CONTACT_THUMB[1]},
        "presets": [preset_manifest(artifact) for artifact in preview_artifacts],
    }
    if contact_artifact is not None:
        manifest["contact_sheet"] = image_manifest(contact_artifact)
    return manifest


def preset_manifest(artifact: PreviewArtifact) -> dict[str, Any]:
    if artifact.preset is None:
        raise ValueError("preset artifact required")
    preset = artifact.preset
    return {
        "id": preset.id,
        "label": preset.label,
        "description": preset.description,
        "density": preset.density,
        "profile_width": preset.profile_width,
        "log_height": preset.log_height,
        "tab_position": preset.tab_position,
        "image": image_manifest(artifact),
    }


def image_manifest(artifact: PreviewArtifact) -> dict[str, Any]:
    return {
        "path": artifact.path.name,
        "width": artifact.width,
        "height": artifact.height,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
    }


def manifest_text(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def build_gallery_html(manifest: dict[str, Any]) -> str:
    cards = []
    for preset in manifest["presets"]:
        image = preset["image"]
        cards.append(
            f"""
      <article class="card">
        <a href="{html.escape(image['path'])}"><img src="{html.escape(image['path'])}" alt="{html.escape(preset['label'])} preview"></a>
        <div class="meta">
          <h2>{html.escape(preset['label'])}</h2>
          <p>{html.escape(preset['description'])}</p>
          <dl>
            <div><dt>Density</dt><dd>{html.escape(preset['density'])}</dd></div>
            <div><dt>Profile Width</dt><dd>{preset['profile_width']} px</dd></div>
            <div><dt>Log Height</dt><dd>{preset['log_height']} px</dd></div>
            <div><dt>Tabs</dt><dd>{html.escape(preset['tab_position'])}</dd></div>
          </dl>
        </div>
      </article>"""
        )
    contact = manifest.get("contact_sheet", {})
    contact_path = html.escape(str(contact.get("path", CONTACT_SHEET_NAME)))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Remote Ops Workspace GUI Preview Gallery</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172033;
      --muted: #667085;
      --line: #d8dee8;
      --panel: #ffffff;
      --page: #f4f6f9;
      --accent: #206a8e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--page);
      color: var(--ink);
      font: 14px/1.45 "Segoe UI", system-ui, -apple-system, sans-serif;
    }}
    header {{
      padding: 22px 28px 14px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }}
    h1 {{
      margin: 0;
      font-size: 22px;
      font-weight: 700;
    }}
    header p {{
      margin: 6px 0 0;
      color: var(--muted);
      max-width: 900px;
    }}
    main {{
      max-width: 1500px;
      margin: 0 auto;
      padding: 24px 28px 34px;
    }}
    .contact {{
      display: block;
      margin-bottom: 24px;
      color: var(--accent);
      font-weight: 600;
      text-decoration: none;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    img {{
      display: block;
      width: 100%;
      height: auto;
      border-bottom: 1px solid var(--line);
    }}
    .meta {{
      padding: 14px 16px 16px;
    }}
    h2 {{
      margin: 0 0 4px;
      font-size: 16px;
      font-weight: 700;
    }}
    p {{
      margin: 0 0 12px;
      color: var(--muted);
    }}
    dl {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin: 0;
    }}
    dt {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
    }}
    dd {{
      margin: 2px 0 0;
      font-weight: 600;
    }}
    @media (max-width: 640px) {{
      main {{ padding: 18px 14px 24px; }}
      header {{ padding: 18px 16px 12px; }}
      .grid {{ grid-template-columns: 1fr; }}
      dl {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Remote Ops Workspace GUI Preview Gallery</h1>
    <p>Static Windows-friendly previews generated from the same GUI design preset metadata used by the PyQt6 desktop shell.</p>
  </header>
  <main>
    <a class="contact" href="{contact_path}">Open contact sheet</a>
    <section class="grid">
{''.join(cards)}
    </section>
  </main>
</body>
</html>
"""


def check_outputs(
    out_dir: Path,
    artifacts: list[PreviewArtifact],
    manifest: dict[str, Any] | None,
    gallery: str | None,
) -> int:
    errors: list[str] = []
    for artifact in artifacts:
        if not artifact.path.exists():
            errors.append(f"missing {display(artifact.path)}")
            continue
        actual = artifact.path.read_bytes()
        if actual != artifact.png_bytes:
            errors.append(f"stale {display(artifact.path)}")
    if manifest is not None:
        manifest_path = out_dir / MANIFEST_NAME
        expected = manifest_text(manifest)
        if not manifest_path.exists():
            errors.append(f"missing {display(manifest_path)}")
        elif manifest_path.read_text(encoding="utf-8") != expected:
            errors.append(f"stale {display(manifest_path)}")
    if gallery is not None:
        gallery_path = out_dir / GALLERY_NAME
        if not gallery_path.exists():
            errors.append(f"missing {display(gallery_path)}")
        elif gallery_path.read_text(encoding="utf-8") != gallery:
            errors.append(f"stale {display(gallery_path)}")
    if errors:
        for error in errors:
            print(f"GUI preview check: {error}", file=sys.stderr)
        return 1
    print("GUI preview render outputs are current")
    return 0


def render_preset(preset: GuiDesignPreset):
    from PIL import Image, ImageDraw

    colors = preset.colors
    image = Image.new("RGB", PREVIEW_SIZE, colors.window)
    draw = ImageDraw.Draw(image)

    title_h = 34
    toolbar_h = 54
    status_h = 24
    margin = 18
    sidebar_w = preset.profile_width
    log_h = preset.log_height
    content_y = title_h + toolbar_h
    content_h = PREVIEW_SIZE[1] - content_y - status_h

    draw_title_bar(draw, preset, 0, 0, PREVIEW_SIZE[0], title_h)
    draw_toolbar(draw, preset, 0, title_h, PREVIEW_SIZE[0], toolbar_h)
    draw_sidebar(draw, preset, margin, content_y + margin, sidebar_w - margin, content_h - margin * 2)
    workspace_x = sidebar_w + margin
    workspace_w = PREVIEW_SIZE[0] - workspace_x - margin
    draw_workspace(
        draw,
        preset,
        workspace_x,
        content_y + margin,
        workspace_w,
        content_h - margin * 2,
        log_h,
    )
    draw_status_bar(draw, preset, 0, PREVIEW_SIZE[1] - status_h, PREVIEW_SIZE[0], status_h)
    return image


def draw_title_bar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)
    draw_text(draw, "Remote Ops Workspace", x + 14, y + 9, c.control_text, 14, bold=True)
    draw_text(draw, preset.label, x + 190, y + 9, c.sidebar_muted, 13)
    for index, token in enumerate(("-", "+", "x")):
        bx = x + w - 92 + index * 30
        draw_text(draw, token, bx, y + 8, c.sidebar_muted, 14, bold=True)


def draw_toolbar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)
    bx = x + 14
    buttons = [
        ("R", "Refresh", c.control, c.control_text),
        ("N", "New", c.control, c.control_text),
        ("E", "Edit", c.control, c.control_text),
        ("C", "Connect", c.primary, c.primary_text),
        ("F", "Files", c.control, c.control_text),
        ("Q", "Queue", c.control, c.control_text),
        ("D", "Dry Run", c.control, c.control_text),
        ("+", "Split", c.control, c.control_text),
    ]
    for icon, label, fill, text in buttons:
        width = max(76, 34 + len(label) * 7)
        rounded(draw, (bx, y + 11, bx + width, y + 39), fill, c.control_border, 4)
        rounded(draw, (bx + 8, y + 17, bx + 23, y + 32), c.window, c.control_border, 3)
        draw_text(draw, icon, bx + 12, y + 18, c.primary if fill != c.primary else c.primary_text, 10, bold=True)
        draw_text(draw, label, bx + 31, y + 18, text, 11, bold=True)
        bx += width + 7

    draw_text(draw, "View", bx + 10, y + 18, c.sidebar_muted, 11)
    bx += 46
    selector_w = 178
    rounded(draw, (bx, y + 11, bx + selector_w, y + 39), c.control, c.control_border, 4)
    draw_text(draw, preset.label, bx + 10, y + 18, c.control_text, 11)
    bx += selector_w + 9
    rounded(draw, (bx, y + 11, bx + 145, y + 39), c.control, c.control_border, 4)
    draw_text(draw, "triage-layout", bx + 10, y + 18, c.control_text, 11)

    search_w = 166
    sx = w - search_w - 16
    rounded(draw, (sx, y + 11, sx + search_w, y + 39), c.control, c.control_border, 4)
    draw_text(draw, "Search log", sx + 10, y + 18, c.sidebar_muted, 11)


def draw_sidebar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    rounded(draw, (x, y, x + w, y + h), c.sidebar, c.pane_border, 5)
    draw_text(draw, "Profiles", x + 14, y + 14, c.sidebar_text, 14, bold=True)
    draw_text(draw, preset.density, x + w - 86, y + 15, c.sidebar_muted, 11)
    rows = [
        ("default", "", True),
        ("  example.jump-ssh", "ssh jump.example", False),
        ("  example.rdp", "rdp win-lab.example", False),
        ("prod", "", True),
        ("  edge-prod", "ssh edge-prod.example", False),
        ("  win-admin", "rdp admin-win.example", False),
        ("files", "", True),
        ("  sftp-ops", "sftp logs.example", False),
        ("  sync-stage", "sync staging-share", False),
    ]
    row_y = y + 45
    for index, (name, target, group) in enumerate(rows):
        selected = index == 4
        if selected:
            rounded(draw, (x + 8, row_y - 4, x + w - 8, row_y + 32), c.sidebar_selected, c.sidebar_selected, 4)
        color = c.sidebar_selected_text if selected else c.sidebar_text
        muted = c.sidebar_selected_text if selected else c.sidebar_muted
        if group:
            draw_text(draw, name, x + 14, row_y, c.status, 11, bold=True)
            row_y += 25
        else:
            draw_text(draw, name, x + 18, row_y, color, 12)
            draw_text(draw, target, x + 29, row_y + 15, muted, 9)
            row_y += 42 if preset.density != "dense" else 36


def draw_workspace(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int, log_h: int) -> None:
    c = preset.colors
    tabs_h = 35
    log_y = y + h - log_h
    draw_tabs(draw, preset, x, y, w, tabs_h)
    pane_y = y + tabs_h
    pane_h = log_y - pane_y - 8
    rounded(draw, (x, pane_y, x + w, pane_y + pane_h), c.pane, c.pane_border, 4)

    left_w = int(w * 0.57)
    right_w = w - left_w - 12
    draw_terminal(draw, preset, x + 12, pane_y + 12, left_w - 18, pane_h - 24, "edge-prod", main=True)
    draw_terminal(draw, preset, x + left_w + 2, pane_y + 12, right_w - 14, pane_h - 24, "net-tools", main=False)

    rounded(draw, (x, log_y, x + w, y + h), c.log, c.pane_border, 4)
    draw_text(draw, "Activity Log", x + 12, log_y + 10, c.log_text, 13, bold=True)
    log_lines = [
        "View: " + preset.label,
        "LAUNCHED: ssh -p 22 operator@edge-prod.example",
        "FILES: sftp -P 22 operator@logs.example",
        "Running process panes: 2",
    ]
    ly = log_y + 34
    for line in log_lines:
        draw_text(draw, line, x + 12, ly, c.log_text, 11, mono=True)
        ly += 18


def draw_tabs(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.pane)
    labels = ["edge-prod", "files-prod", "Split 3", "Welcome"]
    tx = x
    for index, label in enumerate(labels):
        active = index == 0
        tw = 116 if label != "Welcome" else 104
        fill = c.tab_selected if active else c.tab
        text = c.tab_selected_text if active else c.tab_text
        rounded(draw, (tx, y, tx + tw, y + h - 2), fill, c.pane_border, 3)
        draw_text(draw, label, tx + 12, y + 11, text, 11, bold=active)
        tx += tw + 3
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.pane_border)


def draw_terminal(
    draw: Any,
    preset: GuiDesignPreset,
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    *,
    main: bool,
) -> None:
    c = preset.colors
    rounded(draw, (x, y, x + w, y + h), c.terminal, c.pane_border, 3)
    draw_text(draw, title, x + 12, y + 10, c.terminal_text, 12, bold=True)
    lines = [
        "$ ssh -p 22 operator@edge-prod.example",
        "[note] command built as argv list",
        "sftp -> queue preview ready",
        "[process running] stdout captured",
        "",
        "$ row vault status",
        "initialized: yes",
    ] if main else [
        "$ row nettool ping docs.example --dry-run",
        "ping docs.example",
        "",
        "$ row doctor --json",
        "{",
        '  "ssh": true,',
        '  "rdp": true',
        "}",
    ]
    ly = y + 35
    for line in lines:
        color = c.terminal_accent if line.startswith("$") or line.startswith("initialized") else c.terminal_text
        draw_text(draw, line, x + 12, ly, color, 12, mono=True)
        ly += 19


def draw_status_bar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y, x + w, y), fill=c.toolbar_border)
    draw_text(draw, preset.description, x + 14, y + 6, c.sidebar_muted, 10)
    right = f"profile width {preset.profile_width}px | log {preset.log_height}px | tabs {preset.tab_position}"
    draw_text(draw, right, x + w - 300, y + 6, c.sidebar_muted, 10)


def render_contact_sheet(rendered: list[tuple[GuiDesignPreset, Any]]):
    from PIL import Image, ImageDraw

    cols = 2
    gutter = 24
    title_h = 48
    cell_w = CONTACT_THUMB[0]
    cell_h = CONTACT_THUMB[1] + 76
    rows = (len(rendered) + cols - 1) // cols
    sheet_w = cols * cell_w + (cols + 1) * gutter
    sheet_h = rows * cell_h + (rows + 1) * gutter
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#f3f5f8")
    draw = ImageDraw.Draw(sheet)
    for index, (preset, image) in enumerate(rendered):
        row = index // cols
        col = index % cols
        x = gutter + col * (cell_w + gutter)
        y = gutter + row * cell_h
        draw_text(draw, preset.label, x, y, "#111827", 18, bold=True)
        draw_text(draw, preset.description, x, y + 24, "#344054", 12)
        thumb = image.resize(CONTACT_THUMB)
        sheet.paste(thumb, (x, y + title_h))
    return sheet


def rounded(draw: Any, box: tuple[int, int, int, int], fill: str, outline: str, radius: int) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline)


def draw_text(
    draw: Any,
    text: str,
    x: int,
    y: int,
    fill: str,
    size: int,
    *,
    bold: bool = False,
    mono: bool = False,
) -> None:
    draw.text((x, y), text, fill=fill, font=font(size, bold=bold, mono=mono))


def font(size: int, *, bold: bool = False, mono: bool = False):
    from PIL import ImageFont

    candidates = []
    if mono:
        candidates.extend(
            [
                "C:/Windows/Fonts/CascadiaMono.ttf",
                "C:/Windows/Fonts/consola.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            ]
        )
    elif bold:
        candidates.extend(
            [
                "C:/Windows/Fonts/segoeuib.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "C:/Windows/Fonts/segoeui.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

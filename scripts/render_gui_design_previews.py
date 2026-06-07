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

from remote_ops_workspace.gui_designs import (  # noqa: E402
    GUI_DESIGN_PRESETS,
    GuiDesignPreset,
    gui_design_interaction_state,
    gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics,
    gui_design_moba_rail_items,
    gui_design_moba_ribbon_actions,
    gui_design_moba_right_utility_actions,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_menu_items,
    gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_property_grid_chrome,
    gui_design_preset_ids,
    gui_design_reference_state,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_viewer_controls,
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_session_status_strip,
    gui_design_sidebar_copy,
    gui_design_status_segments,
    gui_design_tab_items,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_toolbar_actions,
    gui_design_tree_rows,
    gui_design_workspace_surface,
)
from remote_ops_workspace.moba_connected import (  # noqa: E402
    MobaConnectedSessionState,
    build_moba_connected_session_state,
    moba_connected_tab_chrome_items,
    moba_connected_window_title,
    moba_telemetry_cells,
)
from remote_ops_workspace.models import Profile  # noqa: E402

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

    if preset.id == "mobaxterm":
        return render_mobaxterm_preset(preset)

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


def moba_preview_reference_state() -> MobaConnectedSessionState:
    profile = Profile(
        name="edge-prod",
        protocol="ssh",
        host="edge-prod.example.invalid",
        port=22,
        username="operator",
        group="prod",
        tags=["ssh", "demo"],
        options={"compression": "true", "ssh_browser": "true"},
    )
    listing = "\n".join(
        [
            "drwxr-xr-x 2 operator operator 4096 Jun 06 12:01 current",
            "drwxr-xr-x 2 operator operator 4096 Jun 06 12:02 archive",
            "-rw-r--r-- 1 operator operator 65536 Jun 06 12:03 app.log",
            "-rw-r--r-- 1 operator operator 4096 Jun 06 12:04 health.json",
            "-rw-r--r-- 1 operator operator 8192 Jun 06 12:05 deploy.log",
        ]
    )
    return build_moba_connected_session_state(
        profile,
        remote_path="/var/log",
        terminal_cwd="/var/log",
        follow_terminal_folder=True,
        sftp_listing=listing,
        monitoring_output="cpu=7 mem_mb=410/7680 disk_mb=2867/49152 load=0.07 users=1 "
        "processes=158 net_up_mbps=0.01 net_down_mbps=0.01",
    )


def render_mobaxterm_preset(preset: GuiDesignPreset):
    from PIL import Image, ImageDraw

    c = preset.colors
    interaction = gui_design_interaction_state(preset.id)
    state = moba_preview_reference_state()
    image = Image.new("RGB", PREVIEW_SIZE, c.window)
    draw = ImageDraw.Draw(image)

    title_h = 22
    menu_h = 22
    ribbon_h = 64
    quick_h = 24
    status_h = 22
    side_w = 390
    rail_w = 24
    top_h = title_h + menu_h + ribbon_h
    main_y = top_h
    main_h = PREVIEW_SIZE[1] - main_y - status_h

    titlebar_chrome = gui_design_moba_titlebar_chrome()
    draw.rectangle((0, 0, PREVIEW_SIZE[0], title_h), fill="#1c1c1c")
    draw_moba_titlebar_icon(
        draw,
        titlebar_chrome.icon_left,
        (title_h - titlebar_chrome.icon_size) // 2,
        titlebar_chrome.icon_size,
        c,
    )
    draw_text(draw, moba_connected_window_title(state), titlebar_chrome.title_left, 5, c.control_text, 12, bold=True)
    control_x = PREVIEW_SIZE[0] - titlebar_chrome.control_right_inset - (
        titlebar_chrome.control_width * len(titlebar_chrome.control_keys)
    )
    for key in titlebar_chrome.control_keys:
        draw_moba_titlebar_control(draw, key, control_x, 0, titlebar_chrome.control_width, title_h, c)
        control_x += titlebar_chrome.control_width
    draw.line((0, title_h - 1, PREVIEW_SIZE[0], title_h - 1), fill=c.toolbar_border)

    draw.rectangle((0, title_h, PREVIEW_SIZE[0], title_h + menu_h), fill="#141414")
    mx = 8
    for item in gui_design_moba_top_menu_items():
        draw_text(draw, item.label, mx, title_h + 5, c.control_text, 11)
        mx += len(item.label) * 7 + 18

    ribbon_y = title_h + menu_h
    draw.rectangle((0, ribbon_y, PREVIEW_SIZE[0], ribbon_y + ribbon_h), fill=c.toolbar)
    rx = 12
    for index, action in enumerate(gui_design_moba_ribbon_actions()):
        icon_key = action.icon_key
        label = action.label
        color = action.color
        item_w = max(58, len(label) * 7 + 12)
        if index in {1, 4, 7, 10}:
            draw.line((rx - 6, ribbon_y + 7, rx - 6, ribbon_y + ribbon_h - 8), fill=c.toolbar_border)
        action_state = toolbar_interaction_state(label.lower().replace(" ", "-"), interaction)
        icon_fill, icon_outline, text_color = interaction_button_colors(action_state, c)
        icon_fill = color if action_state == "normal" else icon_fill
        if action_state in {"active", "checked"}:
            draw.rectangle((rx + 10, ribbon_y + 3, rx + 42, ribbon_y + 34), outline=c.control_hover)
        draw_moba_ribbon_icon(draw, icon_key, rx + 14, ribbon_y + 6, 24, icon_fill, icon_outline, c)
        draw_text(draw, label, rx + max(0, (item_w - len(label) * 6) // 2), ribbon_y + 40, text_color, 10)
        rx += item_w
    right_x = PREVIEW_SIZE[0] - 128
    draw.line((right_x - 12, ribbon_y + 7, right_x - 12, ribbon_y + ribbon_h - 8), fill=c.toolbar_border)
    draw_moba_ribbon_icon(draw, "xserver", right_x + 6, ribbon_y + 6, 28, "#1a1a1a", "#1a1a1a", c)
    draw_text(draw, "X server", right_x, ribbon_y + 42, c.control_text, 10)
    draw_moba_ribbon_icon(draw, "exit", PREVIEW_SIZE[0] - 48, ribbon_y + 7, 25, "#e2473f", "#e2473f", c)
    draw_text(draw, "Exit", PREVIEW_SIZE[0] - 50, ribbon_y + 42, c.control_text, 10)
    draw.line((0, ribbon_y + ribbon_h - 1, PREVIEW_SIZE[0], ribbon_y + ribbon_h - 1), fill=c.toolbar_border)

    draw.rectangle((0, main_y, side_w, main_y + quick_h), fill=c.control, outline=c.toolbar_border)
    if interaction.focused_control == "quick-connect":
        draw.rectangle((2, main_y + 2, side_w - 2, main_y + quick_h - 2), outline=c.control_hover, width=2)
    draw_text(draw, "Quick connect...", 8, main_y + 5, c.sidebar_muted, 12)

    tree_y = main_y + quick_h
    draw.rectangle((0, tree_y, rail_w, tree_y + main_h - quick_h), fill="#101010")
    rail_icon_keys = {
        "collapse": "collapse",
        "sessions": "session",
        "favorites": "star",
        "tools": "tools",
        "macros": "macros",
        "sftp": "sftp",
    }
    ry = tree_y + 8
    for item in gui_design_moba_rail_items():
        rail_state = toolbar_interaction_state(item.role, interaction)
        if rail_state == "checked":
            draw.rectangle((2, ry - 3, rail_w - 2, ry + 27), fill=c.sidebar_selected, outline=c.control_hover)
        draw_moba_rail_icon(draw, rail_icon_keys[item.role], 5, ry, 16, item.color, c)
        ry += 26
        if item.label:
            draw_moba_rail_label(image, item.label, 0, ry, rail_w, 54, c)
            ry += 58
        else:
            ry += 8

    draw_moba_connected_sftp_dock(draw, preset, state, rail_w, tree_y, side_w - rail_w, main_h - quick_h)

    tab_y = main_y
    workspace_x = side_w
    draw.rectangle((workspace_x, tab_y, PREVIEW_SIZE[0], tab_y + 28), fill=c.tab, outline=c.toolbar_border)
    tx = workspace_x + 10
    for item in moba_connected_tab_chrome_items(state):
        draw_moba_connected_tab(draw, item, tx, tab_y + 3, c)
        tx += item.width + 4

    content_y = tab_y + 28
    draw.rectangle((workspace_x, content_y, PREVIEW_SIZE[0], PREVIEW_SIZE[1] - status_h), fill=c.pane)
    draw_moba_right_utility_rail(draw, PREVIEW_SIZE[0] - 30, content_y, 30, PREVIEW_SIZE[1] - status_h - content_y, c)

    content_bottom = PREVIEW_SIZE[1] - status_h - 24
    term_x = workspace_x
    banner_chrome = gui_design_moba_ssh_banner_chrome()
    banner_x = term_x + banner_chrome.static_left_offset
    banner_y = content_y + banner_chrome.static_top_offset
    banner_w = banner_chrome.static_width
    banner_h = banner_chrome.static_height
    draw.rectangle((banner_x, banner_y, banner_x + banner_w, banner_y + banner_h), fill=c.terminal, outline=c.terminal_accent)
    draw_centered_text(draw, f"* {banner_chrome.title} *", banner_x, banner_y + 10, banner_w, c.status, 12, mono=True, bold=True)
    draw_centered_text(draw, banner_chrome.subtitle, banner_x, banner_y + 27, banner_w, c.status, 12, mono=True)
    banner_lines = [f"> {line}" if index == 0 else f"  * {line}" for index, line in enumerate(state.banner.lines())]
    by = banner_y + banner_chrome.body_top_offset
    for line in banner_lines:
        color = c.control_text
        draw_text(draw, line, banner_x + 14, by, color, 12, mono=True)
        by += 16
    term_y = banner_y + banner_h + banner_chrome.terminal_gap
    ty = term_y
    for line in state.terminal_transcript:
        color = "#7dd3fc" if line.tone == "info" else c.terminal_text
        draw_text(draw, line.text, term_x + 14, ty, color, 13, mono=True)
        ty += 20
    draw.rectangle((term_x, content_bottom, PREVIEW_SIZE[0], PREVIEW_SIZE[1] - status_h), fill=c.toolbar, outline=c.toolbar_border)
    telemetry_x = term_x + 10
    for cell in moba_telemetry_cells(state):
        cell_right = telemetry_x + cell.width
        draw.rectangle((telemetry_x, content_bottom + 1, cell_right, PREVIEW_SIZE[1] - status_h - 1), fill=c.toolbar)
        draw.line((telemetry_x, content_bottom + 2, telemetry_x, PREVIEW_SIZE[1] - status_h - 2), fill=c.toolbar_border)
        draw_moba_telemetry_icon(draw, cell.icon_key, telemetry_x + 5, content_bottom + 5, 12, c)
        draw_text(draw, cell.display_text, telemetry_x + 22, content_bottom + 6, c.control_text, 9)
        telemetry_x = cell_right
    draw.line((telemetry_x, content_bottom + 2, telemetry_x, PREVIEW_SIZE[1] - status_h - 2), fill=c.toolbar_border)

    draw_status_bar(draw, preset, 0, PREVIEW_SIZE[1] - status_h, PREVIEW_SIZE[0], status_h)
    return image


def draw_moba_telemetry_icon(draw: Any, icon_key: str, x: int, y: int, size: int, c: Any) -> None:
    accent = "#35d7c7"
    if icon_key in {"upload", "download"}:
        accent = "#4da3ff"
    elif icon_key in {"cpu", "process"}:
        accent = "#f4c430"
    elif icon_key in {"memory", "disk"}:
        accent = "#6ac76a"
    draw.rectangle((x, y, x + size, y + size), fill="#101010", outline=accent)
    mid = x + size // 2
    if icon_key == "host":
        draw.rectangle((x + 3, y + 3, x + size - 3, y + size - 5), outline=accent)
        draw.line((x + 4, y + size - 3, x + size - 4, y + size - 3), fill=accent)
    elif icon_key == "cpu":
        draw.rectangle((x + 3, y + 3, x + size - 3, y + size - 3), outline=accent)
        draw.point((mid, y + 4), fill=accent)
        draw.point((mid, y + size - 4), fill=accent)
        draw.point((x + 4, mid), fill=accent)
        draw.point((x + size - 4, mid), fill=accent)
    elif icon_key in {"memory", "disk"}:
        draw.rectangle((x + 3, y + 4, x + size - 3, y + size - 4), outline=accent)
        draw.line((x + 4, y + size - 5, x + size - 4, y + size - 5), fill=accent)
    elif icon_key == "upload":
        draw.line((mid, y + size - 3, mid, y + 3), fill=accent, width=2)
        draw.polygon([(mid - 3, y + 5), (mid + 3, y + 5), (mid, y + 2)], fill=accent)
    elif icon_key == "download":
        draw.line((mid, y + 3, mid, y + size - 3), fill=accent, width=2)
        draw.polygon([(mid - 3, y + size - 5), (mid + 3, y + size - 5), (mid, y + size - 2)], fill=accent)
    elif icon_key == "connection":
        draw.arc((x + 2, y + 3, x + size - 2, y + size + 3), 200, 340, fill=accent, width=2)
    elif icon_key == "process":
        draw.line((x + 3, y + 4, x + size - 3, y + 4), fill=accent)
        draw.line((x + 3, y + 7, x + size - 5, y + 7), fill=accent)
        draw.line((x + 3, y + 10, x + size - 6, y + 10), fill=accent)


def draw_moba_titlebar_icon(draw: Any, x: int, y: int, size: int, c: Any) -> None:
    draw.rectangle((x, y, x + size, y + size), fill="#101010", outline="#d7dde5")
    draw.rectangle((x + 2, y + 2, x + size - 2, y + size - 2), fill="#1b5dbf")
    draw.rectangle((x + 4, y + 4, x + size - 4, y + size - 4), fill="#35d7c7")
    draw.line((x + 2, y + size - 3, x + size - 2, y + 3), fill="#f4c430", width=2)


def draw_moba_titlebar_control(draw: Any, key: str, x: int, y: int, w: int, h: int, c: Any) -> None:
    color = "#e7edf4" if key != "close" else "#ff6b5f"
    mid_x = x + w // 2
    mid_y = y + h // 2
    if key == "minimize":
        draw.line((mid_x - 5, mid_y + 4, mid_x + 5, mid_y + 4), fill=color)
    elif key == "maximize":
        draw.rectangle((mid_x - 5, mid_y - 5, mid_x + 5, mid_y + 5), outline=color)
    elif key == "close":
        draw.line((mid_x - 5, mid_y - 5, mid_x + 5, mid_y + 5), fill=color)
        draw.line((mid_x + 5, mid_y - 5, mid_x - 5, mid_y + 5), fill=color)


def draw_moba_right_utility_rail(draw: Any, x: int, y: int, w: int, h: int, c: Any) -> None:
    draw.rectangle((x, y, x + w, y + h), fill=c.pane)
    draw.line((x, y, x, y + h), fill=c.toolbar_border)
    icon_y = y + 13
    for action in gui_design_moba_right_utility_actions():
        draw_moba_right_utility_icon(draw, action.icon_key, x + 7, icon_y, 16, action.color, c)
        icon_y += 36


def draw_moba_right_utility_icon(draw: Any, icon_key: str, x: int, y: int, size: int, color: str, c: Any) -> None:
    mid = x + size // 2
    if icon_key == "clip":
        draw.arc((x + 3, y + 1, x + size - 3, y + size - 2), 35, 310, fill=color, width=2)
        draw.arc((x + 6, y + 4, x + size - 4, y + size + 1), 35, 310, fill=color, width=2)
        draw.line((x + 8, y + size - 2, x + 4, y + size - 6), fill=color, width=2)
        return
    if icon_key == "spark":
        draw.line((mid, y + 1, mid, y + size - 1), fill=color, width=2)
        draw.line((x + 1, y + size // 2, x + size - 1, y + size // 2), fill=color, width=2)
        draw.line((x + 4, y + 4, x + size - 4, y + size - 4), fill=color)
        draw.line((x + size - 4, y + 4, x + 4, y + size - 4), fill=color)
        return
    if icon_key == "gear":
        draw.ellipse((x + 5, y + 5, x + size - 5, y + size - 5), outline=color, width=2)
        draw.ellipse((x + 7, y + 7, x + size - 7, y + size - 7), outline=color)
        for tx, ty in (
            (mid, y + 1),
            (mid, y + size - 1),
            (x + 1, y + size // 2),
            (x + size - 1, y + size // 2),
            (x + 4, y + 4),
            (x + size - 4, y + 4),
            (x + 4, y + size - 4),
            (x + size - 4, y + size - 4),
        ):
            draw.line((mid, y + size // 2, tx, ty), fill=color, width=1)
        return
    draw.rectangle((x + 2, y + 2, x + size - 2, y + size - 2), outline=c.control_hover)


def draw_moba_connected_tab(draw: Any, item: Any, x: int, y: int, c: Any) -> None:
    fill = c.tab_selected if item.active else c.tab
    text = c.tab_selected_text if item.active else c.tab_text
    rounded(draw, (x, y, x + item.width, y + 22), fill, c.toolbar_border, 2)
    icon_x = x + 8
    if item.key == "new-session":
        draw_text(draw, "+", x + 11, y + 3, text, 13, bold=True)
        return
    draw_moba_tab_icon(draw, item.icon_key, icon_x, y + 5, 12, c)
    if item.label:
        draw_text(draw, item.label, icon_x + 18, y + 7, text, 8, bold=item.active)
    if item.closeable:
        draw_text(draw, "x", x + item.width - 16, y + 6, c.sidebar_muted, 9, bold=True)


def draw_moba_tab_icon(draw: Any, icon_key: str, x: int, y: int, size: int, c: Any) -> None:
    if icon_key == "home":
        draw.polygon(
            [(x, y + 7), (x + size // 2, y), (x + size, y + 7), (x + size - 2, y + 7), (x + size - 2, y + size), (x + 2, y + size), (x + 2, y + 7)],
            fill="#f5f5f5",
            outline=c.toolbar_border,
        )
        draw.rectangle((x + 5, y + 7, x + 8, y + size), fill="#e2473f")
        return
    if icon_key == "terminal-key":
        draw.rectangle((x, y, x + size, y + size), fill="#2b2b2b", outline="#d6a72d")
        draw.line((x + 3, y + 4, x + 7, y + 4), fill="#f7d63f", width=2)
        draw.line((x + 7, y + 4, x + 10, y + 7), fill="#f7d63f", width=2)
        draw.rectangle((x + 2, y + 8, x + 5, y + 10), fill="#f7d63f")
        return
    draw.rectangle((x, y, x + size, y + size), outline=c.control_hover)
    draw.line((x + 3, y + size // 2, x + size - 3, y + size // 2), fill=c.control_hover)
    draw.line((x + size // 2, y + 3, x + size // 2, y + size - 3), fill=c.control_hover)


def draw_moba_rail_icon(draw: Any, icon_key: str, x: int, y: int, size: int, color: str, c: Any) -> None:
    dark = "#101010"
    white = c.control_text
    if icon_key == "collapse":
        draw.line((x + 10, y + 3, x + 5, y + 8), fill=color, width=2)
        draw.line((x + 5, y + 8, x + 10, y + 13), fill=color, width=2)
        draw.line((x + 15, y + 3, x + 10, y + 8), fill=color, width=2)
        draw.line((x + 10, y + 8, x + 15, y + 13), fill=color, width=2)
        return
    if icon_key == "star":
        mid = x + size // 2
        draw.polygon(
            [
                (mid, y + 1),
                (mid + 3, y + 6),
                (x + size - 1, y + 6),
                (mid + 4, y + 10),
                (mid + 6, y + size - 1),
                (mid, y + 12),
                (x + 2, y + size - 1),
                (mid - 4, y + 10),
                (x + 1, y + 6),
                (mid - 3, y + 6),
            ],
            fill=color,
            outline=dark,
        )
        return
    draw.rectangle((x, y, x + size, y + size), fill=color, outline=c.pane_border)
    if icon_key == "session":
        draw.rectangle((x + 3, y + 3, x + size - 3, y + size - 5), fill=dark, outline=white)
        draw.rectangle((x + 5, y + size - 4, x + size - 5, y + size - 3), fill=white)
        return
    if icon_key == "tools":
        draw.line((x + 4, y + size - 4, x + size - 4, y + 4), fill=white, width=2)
        draw.rectangle((x + size - 6, y + 2, x + size - 2, y + 7), fill=white)
        return
    if icon_key == "macros":
        draw.line((x + 4, y + 5, x + size - 4, y + 5), fill=white, width=2)
        draw.line((x + 4, y + 10, x + size - 4, y + 10), fill=white, width=2)
        draw.line((x + 4, y + 15, x + 11, y + 15), fill=white, width=2)
        return
    if icon_key == "sftp":
        draw.rectangle((x + 3, y + 6, x + size - 2, y + size - 3), fill="#ffd866", outline=dark)
        draw.rectangle((x + 4, y + 4, x + 10, y + 7), fill="#ffe58a", outline=dark)
        draw.line((x + 5, y + 13, x + size - 5, y + 13), fill="#2f6fb1", width=2)


def draw_moba_rail_label(image: Any, text: str, x: int, y: int, w: int, h: int, c: Any) -> None:
    from PIL import Image, ImageDraw

    label = Image.new("RGBA", (h, w), (0, 0, 0, 0))
    label_draw = ImageDraw.Draw(label)
    label_font = font(10, bold=True)
    bbox = label_draw.textbbox((0, 0), text, font=label_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    label_draw.text(
        ((h - text_w) // 2, (w - text_h) // 2 - bbox[1]),
        text,
        fill=c.sidebar_text,
        font=label_font,
    )
    rotated = label.rotate(-90, expand=True)
    image.paste(rotated, (x, y), rotated)
    draw = ImageDraw.Draw(image)
    draw.line((x + 2, y + h - 1, x + w - 2, y + h - 1), fill=c.toolbar_border)


def draw_moba_connected_sftp_dock(
    draw: Any,
    preset: GuiDesignPreset,
    state: MobaConnectedSessionState,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    c = preset.colors
    density = gui_design_moba_sftp_dock_layout()
    draw.rectangle((x, y, x + w, y + h), fill=c.sidebar, outline=c.toolbar_border)
    toolbar_y = y + density.inner_margin
    dock_left = x + density.inner_margin
    dock_right = x + w - density.inner_margin
    draw.rectangle(
        (dock_left, toolbar_y, dock_right, toolbar_y + density.toolbar_height),
        fill=c.control,
        outline=c.toolbar_border,
    )
    tool_x = dock_left + density.toolbar_icon_left_inset
    for action in gui_design_moba_sftp_dock_actions():
        draw_moba_sftp_toolbar_icon(
            draw,
            action.icon_key,
            tool_x,
            toolbar_y + (density.toolbar_height - density.toolbar_icon_size) // 2,
            density.toolbar_icon_size,
            action.color,
            c,
        )
        tool_x += density.toolbar_icon_step
        if action.separator_after:
            separator_x = tool_x + density.toolbar_separator_width // 2
            draw.line(
                (separator_x, toolbar_y + 5, separator_x, toolbar_y + density.toolbar_height - 5),
                fill=c.toolbar_border,
            )
            tool_x += density.toolbar_separator_width

    chrome = gui_design_moba_sftp_browser_chrome()
    path_y = toolbar_y + density.toolbar_height + density.path_gap
    draw.rectangle((dock_left, path_y, dock_right, path_y + density.path_height), fill=c.control, outline=c.toolbar_border)
    draw_text(draw, state.remote_path or chrome.path_placeholder, x + 14, path_y + 6, c.control_text, 11, mono=True)
    draw_text(draw, chrome.dropdown_marker, x + w - 18, path_y + 6, c.sidebar_muted, 10, bold=True)

    header_y = path_y + density.path_height + density.table_header_gap
    draw.rectangle(
        (dock_left, header_y, dock_right, header_y + density.table_header_height),
        fill="#2b2b2b",
        outline=c.toolbar_border,
    )
    for column in chrome.columns:
        draw_text(draw, column.label, x + column.static_x, header_y + 7, c.control_text, 10, bold=True)
    file_rows = [("parent-dir", "..", "", ""), *[(entry.kind, entry.name, str(entry.size_kb), entry.modified) for entry in state.file_entries]]
    row_y = header_y + density.table_header_height + density.file_row_gap
    for kind, name, size, modified in file_rows[: density.static_max_rows]:
        draw_moba_sftp_file_icon(draw, kind, x + 14, row_y - 1, 14, c)
        draw_text(draw, name, x + 38, row_y, c.control_text, 10)
        draw_text(draw, size, x + 202, row_y, c.control_text, 10)
        draw_text(draw, modified, x + 278, row_y, c.sidebar_muted, 9)
        row_y += density.file_row_height

    monitor_y = y + h - density.monitoring_height
    draw.line(
        (
            x + density.monitoring_left_inset,
            monitor_y - density.monitoring_divider_offset,
            x + w - density.monitoring_left_inset,
            monitor_y - density.monitoring_divider_offset,
        ),
        fill=c.sidebar_muted,
    )
    controls = list(gui_design_moba_monitoring_controls())
    remote_control = controls[0]
    follow_control = controls[1]
    draw_moba_monitoring_control(
        draw,
        remote_control,
        x + density.monitoring_icon_center_x,
        monitor_y + 1,
        c,
        checked=remote_control.checked,
        centered_icon=True,
    )
    metrics = [moba_monitoring_metric_text(state, metric) for metric in gui_design_moba_monitoring_metrics()]
    draw_text(draw, "   ".join(metrics[:2]), x + density.monitoring_content_left, monitor_y + 28, c.sidebar_text, 10)
    draw_text(
        draw,
        "   ".join(metrics[2:4]),
        x + density.monitoring_content_left,
        monitor_y + 28 + density.monitoring_metric_row_gap,
        c.sidebar_text,
        10,
    )
    draw_moba_monitoring_control(
        draw,
        follow_control,
        x + density.monitoring_content_left,
        monitor_y + 76,
        c,
        checked=state.follow_terminal_folder,
    )


def draw_moba_monitoring_control(
    draw: Any,
    control: Any,
    x: int,
    y: int,
    c: Any,
    *,
    checked: bool,
    centered_icon: bool = False,
) -> None:
    if control.control_type == "checkbox":
        draw.rectangle((x, y + 3, x + 10, y + 13), outline=c.control_text, fill=c.window)
        if checked:
            draw.line((x + 2, y + 8, x + 5, y + 12), fill=c.control_text, width=1)
            draw.line((x + 5, y + 12, x + 10, y + 4), fill=c.control_text, width=1)
        draw_moba_monitoring_control_icon(draw, control.icon_key, x + 18, y, 16, c)
        draw_text(draw, control.label, x + 38, y + 3, c.control_text, 11)
        return
    icon_x = x if centered_icon else x + 18
    draw_moba_monitoring_control_icon(draw, control.icon_key, icon_x, y, 20, c)
    draw_text(draw, control.label, icon_x + 28, y + 2, c.control_text, 12, bold=True)


def draw_moba_monitoring_control_icon(draw: Any, icon_key: str, x: int, y: int, size: int, c: Any) -> None:
    if icon_key == "monitor":
        draw_moba_monitor_icon(draw, x, y, size, c)
        return
    if icon_key == "follow-folder":
        draw.rectangle((x + 2, y + 6, x + size - 2, y + size - 3), fill="#ffd866", outline="#303030")
        draw.rectangle((x + 3, y + 4, x + 10, y + 7), fill="#ffe58a", outline="#303030")
        draw.line((x + size - 8, y + size - 7, x + size - 5, y + size - 4), fill="#1c7a38", width=2)
        draw.line((x + size - 5, y + size - 4, x + size - 2, y + size - 10), fill="#1c7a38", width=2)


def moba_monitoring_metric_text(state: MobaConnectedSessionState, metric: Any) -> str:
    monitoring = state.monitoring
    if metric.source == "cpu_percent":
        value = f"{monitoring.cpu_percent}%"
    elif metric.source == "memory_label":
        value = monitoring.memory_label
    elif metric.source == "disk_label":
        value = monitoring.disk_label
    elif metric.source == "network_pair":
        value = f"{monitoring.net_up_mbps:.2f}/{monitoring.net_down_mbps:.2f} Mb/s"
    elif metric.source == "load_average":
        value = monitoring.load_average
    elif metric.source == "process_count":
        value = str(monitoring.process_count)
    else:
        value = ""
    return f"{metric.label} {value}".strip()


def draw_moba_sftp_toolbar_icon(draw: Any, icon_key: str, x: int, y: int, size: int, color: str, c: Any) -> None:
    draw.rectangle((x, y, x + size, y + size), fill=color, outline=c.pane_border)
    white = c.primary_text
    dark = "#101010"
    mid = x + size // 2
    if icon_key in {"parent-folder", "new-folder"}:
        draw.rectangle((x + 3, y + 6, x + size - 2, y + size - 3), fill="#ffd866", outline=dark)
        draw.rectangle((x + 4, y + 4, x + 10, y + 7), fill="#ffe58a", outline=dark)
        if icon_key == "parent-folder":
            draw.polygon([(mid, y + 4), (mid - 4, y + 9), (mid + 4, y + 9)], fill="#2f6fb1")
            draw.rectangle((mid - 1, y + 8, mid + 1, y + 13), fill="#2f6fb1")
        else:
            draw.line((mid, y + 7, mid, y + size - 5), fill="#1c7a38", width=2)
            draw.line((mid - 4, y + 11, mid + 4, y + 11), fill="#1c7a38", width=2)
        return
    if icon_key == "connect":
        draw.ellipse((x + 3, y + 3, x + size - 3, y + size - 3), fill="#55cc7a", outline=white)
        draw.line((mid, y + 4, mid, y + 9), fill=white, width=2)
        return
    if icon_key == "new-file":
        draw.rectangle((x + 4, y + 2, x + size - 4, y + size - 2), fill="#d7dde5", outline=dark)
        draw.polygon([(x + size - 8, y + 2), (x + size - 4, y + 6), (x + size - 8, y + 6)], fill="#eef2f7")
        draw.line((mid, y + 6, mid, y + size - 5), fill="#1c7a38", width=2)
        draw.line((mid - 4, y + 10, mid + 4, y + 10), fill="#1c7a38", width=2)
        return
    if icon_key in {"download", "upload"}:
        direction = 1 if icon_key == "download" else -1
        shaft_top = y + 4 if direction == 1 else y + 8
        shaft_bottom = y + 11 if direction == 1 else y + 15
        draw.line((mid, shaft_top, mid, shaft_bottom), fill=white, width=2)
        if direction == 1:
            draw.polygon([(mid - 4, y + 10), (mid + 4, y + 10), (mid, y + 15)], fill=white)
        else:
            draw.polygon([(mid - 4, y + 9), (mid + 4, y + 9), (mid, y + 4)], fill=white)
        draw.rectangle((x + 4, y + 13, x + size - 4, y + 15), fill=white)
        return
    if icon_key == "delete":
        draw.line((x + 4, y + 4, x + size - 4, y + size - 4), fill=white, width=2)
        draw.line((x + size - 4, y + 4, x + 4, y + size - 4), fill=white, width=2)
        return
    if icon_key == "ascii-mode":
        draw_text(draw, "A", x + 5, y + 2, white, 12, bold=True)
        return
    if icon_key == "split-view":
        draw.rectangle((x + 3, y + 3, x + size - 3, y + size - 3), outline=white, width=2)
        draw.line((mid, y + 3, mid, y + size - 3), fill=white, width=2)
        return
    if icon_key == "tools":
        draw.line((x + 4, y + 4, x + size - 5, y + size - 5), fill=white, width=2)
        draw.line((x + size - 5, y + 4, x + 5, y + size - 4), fill=white, width=2)
        return
    if icon_key == "terminal":
        draw.rectangle((x + 3, y + 3, x + size - 3, y + size - 4), fill="#111111", outline=white)
        draw.line((x + 6, y + 7, x + 10, y + 10), fill="#35d7c7", width=2)
        draw.line((x + 10, y + 10, x + 6, y + 13), fill="#35d7c7", width=2)


def draw_moba_sftp_file_icon(draw: Any, kind: str, x: int, y: int, size: int, c: Any) -> None:
    if kind in {"dir", "parent-dir"}:
        fill = "#f2c744" if kind == "dir" else "#f5d96a"
        draw.rectangle((x, y + 4, x + size, y + size - 1), fill=fill, outline=c.pane_border)
        draw.rectangle((x + 2, y + 2, x + 8, y + 5), fill="#ffe58a", outline=c.pane_border)
        if kind == "parent-dir":
            mid = x + size // 2
            draw.polygon([(mid, y + 4), (mid - 3, y + 8), (mid + 3, y + 8)], fill="#2f6fb1")
        return
    draw.rectangle((x + 2, y + 1, x + size - 1, y + size), fill="#d7dde5", outline=c.pane_border)
    draw.polygon([(x + size - 5, y + 1), (x + size - 1, y + 5), (x + size - 5, y + 5)], fill="#eef2f7")
    draw.line((x + 4, y + 7, x + size - 4, y + 7), fill="#6b7280")
    draw.line((x + 4, y + 10, x + size - 5, y + 10), fill="#6b7280")


def draw_moba_monitor_icon(draw: Any, x: int, y: int, size: int, c: Any) -> None:
    draw.rectangle((x, y, x + size, y + size - 5), fill="#11332f", outline="#35d7c7")
    draw.line((x + 4, y + size - 8, x + 8, y + size - 12), fill="#35d7c7", width=2)
    draw.line((x + 8, y + size - 12, x + 12, y + size - 6), fill="#35d7c7", width=2)
    draw.line((x + 12, y + size - 6, x + size - 3, y + 4), fill="#35d7c7", width=2)
    draw.rectangle((x + 7, y + size - 4, x + size - 7, y + size - 2), fill=c.sidebar_muted)


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
    interaction = gui_design_interaction_state(preset.id)
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)
    bx = x + 14
    reserved_x = w - 402
    for key, label, _tooltip in gui_design_toolbar_actions(preset.id):
        icon = toolbar_action_icon(key, label)
        button_state = toolbar_interaction_state(key, interaction)
        fill, outline, text = interaction_button_colors(button_state, c)
        width = max(76, 34 + len(label) * 7)
        if bx + width > reserved_x:
            break
        rounded(draw, (bx, y + 11, bx + width, y + 39), fill, outline, 4)
        if button_state in {"active", "checked"}:
            draw.rectangle((bx + 4, y + 14, bx + width - 4, y + 36), outline=c.control_hover)
        rounded(draw, (bx + 8, y + 17, bx + 23, y + 32), c.window, outline, 3)
        draw_text(draw, icon, bx + 12, y + 18, c.primary if fill != c.primary else c.primary_text, 10, bold=True)
        draw_text(draw, label, bx + 31, y + 18, text, 11, bold=True)
        bx += width + 7

    draw_text(draw, "View", bx + 10, y + 18, c.sidebar_muted, 11)
    bx += 46
    selector_w = 178
    rounded(draw, (bx, y + 11, bx + selector_w, y + 39), c.control, c.control_border, 4)
    if interaction.focused_control == "view-select":
        draw.rectangle((bx - 2, y + 9, bx + selector_w + 2, y + 41), outline=c.control_hover, width=2)
    draw_text(draw, preset.label, bx + 10, y + 18, c.control_text, 11)
    bx += selector_w + 9
    rounded(draw, (bx, y + 11, bx + 145, y + 39), c.control, c.control_border, 4)
    draw_text(draw, "triage-layout", bx + 10, y + 18, c.control_text, 11)

    search_w = 166
    sx = w - search_w - 16
    rounded(draw, (sx, y + 11, sx + search_w, y + 39), c.control, c.control_border, 4)
    if interaction.focused_control in {"search-log", "session-filter", "host-search", "profile-filter", "tree-filter"}:
        draw.rectangle((sx - 2, y + 9, sx + search_w + 2, y + 41), outline=c.control_hover, width=2)
    draw_text(draw, "Search log", sx + 10, y + 18, c.sidebar_muted, 11)


def toolbar_interaction_state(key: str, interaction: Any) -> str:
    if key == interaction.active_toolbar_key:
        return "active"
    if key == interaction.checked_toolbar_key:
        return "checked"
    if key == interaction.disabled_toolbar_key:
        return "disabled"
    return "normal"


def interaction_button_colors(state: str, c: Any) -> tuple[str, str, str]:
    if state == "active":
        return c.primary, c.primary, c.primary_text
    if state == "checked":
        return c.sidebar_selected, c.control_hover, c.sidebar_selected_text
    if state == "disabled":
        return c.pane, c.toolbar_border, c.sidebar_muted
    return c.control, c.control_border, c.control_text


def toolbar_action_icon(key: str, label: str) -> str:
    tokens = {
        "refresh": "R",
        "new": "N",
        "edit": "E",
        "remove": "X",
        "connect": "C",
        "files": "F",
        "queue": "Q",
        "dry-run": "D",
        "doctor": "?",
        "split-h": "H",
        "split-v": "V",
    }
    return tokens.get(key, label[:1].upper() or "*")


def draw_moba_ribbon_icon(
    draw: Any,
    icon_key: str,
    x: int,
    y: int,
    size: int,
    fill: str,
    outline: str,
    c: Any,
) -> None:
    draw.rounded_rectangle((x, y, x + size, y + size), radius=3, fill=fill, outline=outline)
    white = c.primary_text
    dark = "#101010"
    accent = c.terminal_accent
    cyan = "#26d0d4"
    green = "#42d66b"
    blue = "#4da3ff"
    red = "#ff614f"
    yellow = "#f7d63f"
    mid_x = x + size // 2
    mid_y = y + size // 2

    if icon_key == "session":
        draw.rectangle((x + 5, y + 5, x + size - 5, y + size - 8), fill=dark, outline=white)
        draw.rectangle((x + 8, y + size - 7, x + size - 8, y + size - 5), fill=white)
        draw.rectangle((mid_x - 2, y + size - 5, mid_x + 2, y + size - 3), fill=white)
        draw.rectangle((x + 9, y + 9, x + 14, y + 13), fill=green)
        return
    if icon_key == "servers":
        nodes = [(mid_x, y + 5), (x + 6, y + size - 7), (x + size - 6, y + size - 7)]
        draw.line((nodes[0], nodes[1]), fill=white, width=2)
        draw.line((nodes[0], nodes[2]), fill=white, width=2)
        draw.line((nodes[1], nodes[2]), fill=white, width=2)
        for nx, ny in nodes:
            draw.ellipse((nx - 4, ny - 4, nx + 4, ny + 4), fill=cyan, outline=white)
        return
    if icon_key == "tools":
        draw.line((x + 7, y + 6, x + size - 6, y + size - 7), fill=white, width=3)
        draw.polygon([(x + size - 9, y + 4), (x + size - 4, y + 9), (x + size - 10, y + 13)], fill=red)
        draw.rectangle((x + 4, y + size - 8, x + 11, y + size - 4), fill=yellow)
        return
    if icon_key == "games":
        draw.rounded_rectangle((x + 4, y + 10, x + size - 4, y + size - 7), radius=6, fill=white, outline=dark)
        draw.line((x + 8, y + 17, x + 14, y + 17), fill=dark, width=2)
        draw.line((x + 11, y + 14, x + 11, y + 20), fill=dark, width=2)
        draw.ellipse((x + size - 12, y + 14, x + size - 8, y + 18), fill=red)
        draw.ellipse((x + size - 8, y + 18, x + size - 4, y + 22), fill=blue)
        return
    if icon_key == "sessions":
        points = [
            (mid_x, y + 3),
            (mid_x + 4, y + 10),
            (x + size - 4, y + 10),
            (mid_x + 6, y + 15),
            (mid_x + 9, y + size - 4),
            (mid_x, y + 18),
            (x + 6, y + size - 4),
            (mid_x - 6, y + 15),
            (x + 4, y + 10),
            (mid_x - 4, y + 10),
        ]
        draw.polygon(points, fill=yellow, outline=dark)
        return
    if icon_key == "view":
        draw.rectangle((x + 5, y + 5, x + size - 5, y + size - 5), fill=blue, outline=white)
        draw.line((x + 5, mid_y, x + size - 5, mid_y), fill=white)
        draw.line((mid_x, y + 5, mid_x, y + size - 5), fill=white)
        return
    if icon_key == "split":
        draw.rectangle((x + 5, y + 5, x + size - 5, y + size - 5), outline=white, width=2)
        draw.line((x + 5, mid_y, x + size - 5, mid_y), fill=white, width=2)
        draw.line((mid_x, y + 5, mid_x, y + size - 5), fill=white, width=2)
        draw.rectangle((x + 7, y + 7, mid_x - 2, mid_y - 2), fill=cyan)
        return
    if icon_key == "multiexec":
        draw.line((mid_x, y + 5, mid_x, y + size - 6), fill=white, width=3)
        draw.line((mid_x, y + 12, x + 6, y + size - 7), fill=white, width=2)
        draw.line((mid_x, y + 12, x + size - 6, y + size - 7), fill=white, width=2)
        for nx, ny in [(mid_x, y + 5), (x + 6, y + size - 7), (x + size - 6, y + size - 7)]:
            draw.ellipse((nx - 3, ny - 3, nx + 3, ny + 3), fill=blue)
        return
    if icon_key == "tunneling":
        draw.rectangle((x + 4, y + 8, x + size - 4, y + 16), fill=white)
        draw.polygon([(x + 4, y + 12), (x + 10, y + 7), (x + 10, y + 17)], fill=green)
        draw.polygon([(x + size - 4, y + 12), (x + size - 10, y + 7), (x + size - 10, y + 17)], fill=green)
        draw.rectangle((x + 8, y + 18, x + size - 8, y + 21), fill=white)
        return
    if icon_key == "packages":
        draw.polygon([(mid_x, y + 4), (x + size - 5, y + 10), (mid_x, y + 16), (x + 5, y + 10)], fill=white, outline=dark)
        draw.polygon([(x + 5, y + 10), (mid_x, y + 16), (mid_x, y + size - 4), (x + 5, y + 18)], fill=blue)
        draw.polygon([(x + size - 5, y + 10), (mid_x, y + 16), (mid_x, y + size - 4), (x + size - 5, y + 18)], fill="#9aa6ff")
        return
    if icon_key == "settings":
        draw.ellipse((x + 6, y + 6, x + size - 6, y + size - 6), outline=white, width=3)
        for dx, dy in [(0, -8), (0, 8), (-8, 0), (8, 0)]:
            draw.line((mid_x, mid_y, mid_x + dx, mid_y + dy), fill=white, width=2)
        draw.ellipse((mid_x - 3, mid_y - 3, mid_x + 3, mid_y + 3), fill=accent)
        return
    if icon_key == "help":
        draw.ellipse((x + 5, y + 4, x + size - 5, y + size - 4), fill=blue, outline=white)
        draw_text(draw, "?", x + 9, y + 4, white, 15, bold=True)
        return
    if icon_key == "xserver":
        draw.line((x + 5, y + 5, x + size - 5, y + size - 5), fill=green, width=4)
        draw.line((x + size - 5, y + 5, x + 5, y + size - 5), fill=blue, width=4)
        draw.line((x + mid_x - x, y + 4, x + mid_x - x, y + size - 4), fill=red, width=2)
        return
    if icon_key == "exit":
        draw.ellipse((x, y, x + size, y + size), fill=fill, outline=outline)
        draw.line((mid_x, y + 6, mid_x, mid_y + 2), fill=white, width=3)
        draw.arc((x + 6, y + 6, x + size - 6, y + size - 6), 35, 325, fill=white, width=3)


def draw_sidebar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    interaction = gui_design_interaction_state(preset.id)
    rounded(draw, (x, y, x + w, y + h), c.sidebar, c.pane_border, 5)
    title, subtitle = gui_design_sidebar_copy(preset.id)
    draw_text(draw, title, x + 14, y + 14, c.sidebar_text, 14, bold=True)
    draw_text(draw, subtitle, x + 14, y + 34, c.sidebar_muted, 10)
    draw_text(draw, preset.density, x + w - 86, y + 15, c.sidebar_muted, 11)
    rows = gui_design_tree_rows(preset.id)
    row_y = y + 66
    if preset.id == "remmina":
        draw_remmina_profile_list_chrome(draw, preset, x + 10, y + 62, w - 20, 126)
        row_y = y + 204
    for name, target, group in rows:
        selected = interaction.selected_tree_label in name
        icon_key = sidebar_row_icon_key(preset.id, name, target, group)
        if selected:
            rounded(draw, (x + 8, row_y - 4, x + w - 8, row_y + 32), c.sidebar_selected, c.sidebar_selected, 4)
        color = c.sidebar_selected_text if selected else c.sidebar_text
        muted = c.sidebar_selected_text if selected else c.sidebar_muted
        if group:
            draw_sidebar_row_icon(draw, preset, icon_key, x + 14, row_y - 1, 13, selected=False, group=True)
            draw_text(draw, name, x + 34, row_y, c.status, 11, bold=True)
            row_y += 25
        else:
            draw_sidebar_row_icon(draw, preset, icon_key, x + 18, row_y + 1, 14, selected=selected, group=False)
            draw_text(draw, name, x + 40, row_y, color, 12)
            draw_text(draw, target, x + 40, row_y + 15, muted, 9)
            row_y += 42 if preset.density != "dense" else 36


def draw_remmina_profile_list_chrome(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_remmina_profile_list_chrome()
    rounded(draw, (x, y, x + w, y + h), c.pane, c.pane_border, 4)
    draw_text(draw, chrome.title, x + 8, y + 8, c.control_text, 10, bold=True)
    filter_x = x + 110
    rounded(draw, (filter_x, y + 5, x + w - 7, y + 25), c.control, c.control_border, 3)
    draw_text(draw, chrome.filter_placeholder, filter_x + 7, y + 10, c.sidebar_muted, 8)
    header_y = y + 33
    col_x = x + 8
    for column in chrome.columns:
        draw_text(draw, column.label, col_x, header_y, c.sidebar_muted, 8, bold=True)
        col_x += column.static_width
    row_y = y + 48
    for row in chrome.rows:
        fill = c.sidebar_selected if row.selected else c.control
        outline = c.primary if row.selected else c.control_border
        rounded(draw, (x + 6, row_y, x + w - 6, row_y + 22), fill, outline, 3)
        values = {"name": row.name, "protocol": row.protocol, "server": row.server}
        col_x = x + 12
        for column in chrome.columns:
            text_color = c.sidebar_selected_text if row.selected else c.control_text
            if column.key == "protocol":
                text_color = c.primary
            draw_text(draw, values[column.key], col_x, row_y + 6, text_color, 8, bold=column.key == "name")
            col_x += column.static_width
        draw_text(draw, row.status, x + 12, row_y + 16, c.sidebar_muted, 7)
        row_y += 24


def sidebar_row_icon_key(preset_id: str, name: str, target: str, group: bool) -> str:
    value = f"{name} {target}".lower()
    if group:
        if "xml" in value or "database" in value or "vault" in value:
            return "database"
        return "folder"
    if "rdp" in value:
        return "rdp"
    if "vnc" in value:
        return "vnc"
    if "sftp" in value or "file" in value:
        return "sftp"
    if "local" in value or "powershell" in value:
        return "shell"
    if "snippet" in value or "deploy" in value:
        return "snippet"
    if "jump" in value or "pinned" in value:
        return "pin"
    if preset_id == "termius":
        return "host"
    return "ssh"


def draw_sidebar_row_icon(
    draw: Any,
    preset: GuiDesignPreset,
    icon_key: str,
    x: int,
    y: int,
    size: int,
    *,
    selected: bool,
    group: bool,
) -> None:
    c = preset.colors
    fill = c.sidebar_selected_text if selected else c.primary
    outline = c.sidebar_selected_text if selected else c.control_hover
    muted = c.sidebar_muted if not selected else c.sidebar_selected_text
    if group:
        fill = c.status
        outline = c.status
    if icon_key == "folder":
        draw.rectangle((x, y + 4, x + size, y + size), fill=fill, outline=outline)
        draw.rectangle((x + 2, y + 2, x + size // 2 + 2, y + 6), fill=fill, outline=outline)
        return
    if icon_key == "database":
        draw.ellipse((x, y + 1, x + size, y + 6), fill=fill, outline=outline)
        draw.rectangle((x, y + 4, x + size, y + size - 3), fill=fill, outline=outline)
        draw.ellipse((x, y + size - 7, x + size, y + size - 1), fill=fill, outline=outline)
        return
    if icon_key in {"rdp", "vnc"}:
        draw.rectangle((x, y + 1, x + size, y + size - 4), fill=None, outline=fill)
        draw.rectangle((x + 3, y + size - 3, x + size - 3, y + size - 1), fill=fill)
        if icon_key == "rdp":
            draw.rectangle((x + 3, y + 4, x + size - 3, y + size - 7), fill=muted)
        else:
            draw.line((x + 3, y + 4, x + size - 3, y + size - 7), fill=fill, width=1)
            draw.line((x + size - 3, y + 4, x + 3, y + size - 7), fill=fill, width=1)
        return
    if icon_key == "sftp":
        draw.rectangle((x + 2, y + 1, x + size - 2, y + size - 1), fill=None, outline=fill)
        draw.line((x + 4, y + 5, x + size - 4, y + 5), fill=fill)
        draw.line((x + 4, y + 8, x + size - 4, y + 8), fill=fill)
        draw.polygon([(x + size - 5, y + 3), (x + size - 2, y + 6), (x + size - 5, y + 9)], fill=fill)
        return
    if icon_key == "shell":
        draw.rectangle((x, y + 2, x + size, y + size - 1), fill="#101820", outline=fill)
        draw.line((x + 3, y + 5, x + 6, y + 8), fill=fill)
        draw.line((x + 6, y + 8, x + 3, y + 11), fill=fill)
        draw.line((x + 8, y + 11, x + size - 3, y + 11), fill=fill)
        return
    if icon_key == "snippet":
        draw.rectangle((x + 2, y + 1, x + size - 2, y + size - 1), fill=None, outline=fill)
        for offset in (4, 7, 10):
            draw.line((x + 5, y + offset, x + size - 5, y + offset), fill=fill)
        return
    if icon_key == "pin":
        draw.polygon([(x + size // 2, y), (x + size - 2, y + 6), (x + 8, y + 6)], fill=fill)
        draw.line((x + size // 2, y + 6, x + size // 2, y + size), fill=fill, width=2)
        return
    draw.rectangle((x + 2, y + 2, x + size - 2, y + size - 2), fill=None, outline=fill)
    draw.line((x + 4, y + size - 5, x + size - 4, y + 4), fill=fill, width=2)


def draw_workspace(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int, log_h: int) -> None:
    c = preset.colors
    surface = gui_design_workspace_surface(preset.id)
    if preset.id == "securecrt":
        draw_securecrt_workspace(draw, preset, surface, x, y, w, h, log_h)
        return
    if preset.id == "termius":
        draw_termius_workspace(draw, preset, surface, x, y, w, h, log_h)
        return
    if preset.id == "remmina":
        draw_remmina_workspace(draw, preset, surface, x, y, w, h, log_h)
        return
    if preset.id == "mremoteng":
        draw_mremoteng_workspace(draw, preset, surface, x, y, w, h, log_h)
        return

    tabs_h = 35
    log_y = y + h - log_h
    if preset.tab_position == "west":
        tabs_w = 86
        draw_vertical_tabs(draw, preset, x, y, tabs_w, log_y - y - 8)
        pane_x = x + tabs_w
        pane_y = y
        pane_w = w - tabs_w
        pane_h = log_y - pane_y - 8
    else:
        draw_tabs(draw, preset, x, y, w, tabs_h)
        pane_x = x
        pane_y = y + tabs_h
        pane_w = w
        pane_h = log_y - pane_y - 8
    rounded(draw, (pane_x, pane_y, pane_x + pane_w, pane_y + pane_h), c.pane, c.pane_border, 4)

    left_w = int(pane_w * 0.57)
    right_w = pane_w - left_w - 12
    draw_terminal(draw, preset, pane_x + 12, pane_y + 12, left_w - 18, pane_h - 24, "edge-prod", main=True)
    draw_terminal(draw, preset, pane_x + left_w + 2, pane_y + 12, right_w - 14, pane_h - 24, "net-tools", main=False)

    rounded(draw, (x, log_y, x + w, y + h), c.log, c.pane_border, 4)
    draw_text(draw, "Activity Log", x + 12, log_y + 10, c.log_text, 13, bold=True)
    log_lines = list(surface.activity_lines)
    ly = log_y + 34
    for line in log_lines:
        draw_text(draw, line, x + 12, ly, c.log_text, 11, mono=True)
        ly += 18


def draw_product_reference_state(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    reference = gui_design_reference_state(preset.id)
    rounded(draw, (x, y, x + w, y + h), c.control, c.control_border, 3)
    chip_x = x + 8
    for key, value in reference.items():
        text = f"{key}: {value}"
        chip_w = min(max(70, len(text) * 6 + 12), 180)
        if chip_x + chip_w > x + w - 6:
            break
        rounded(draw, (chip_x, y + 4, chip_x + chip_w, y + h - 4), c.pane, c.pane_border, 3)
        draw_text(draw, text, chip_x + 6, y + 8, c.control_text, 8, bold=True)
        chip_x += chip_w + 6


def draw_securecrt_workspace(
    draw: Any,
    preset: GuiDesignPreset,
    surface: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    log_h: int,
) -> None:
    c = preset.colors
    tabs_h = 35
    log_y = y + h - log_h
    draw_tabs(draw, preset, x, y, w, tabs_h)
    pane_y = y + tabs_h
    pane_h = log_y - pane_y - 8
    rounded(draw, (x, pane_y, x + w, pane_y + pane_h), c.pane, c.pane_border, 2)
    draw.rectangle((x + 10, pane_y + 9, x + w - 10, pane_y + 39), fill=c.toolbar, outline=c.pane_border)
    draw_text(draw, surface.title, x + 22, pane_y + 17, c.control_text, 12, bold=True)
    draw_text(draw, surface.subtitle, x + 304, pane_y + 17, c.sidebar_muted, 10)
    draw_product_reference_state(draw, preset, x + 10, pane_y + 44, w - 20, 24)

    term_w = int(w * 0.68)
    command_h = 52
    command_y = pane_y + pane_h - command_h - 10
    strip_y = pane_y + 74
    draw_securecrt_session_status_strip(draw, preset, x + 10, strip_y, w - 20, 30)
    terminal_y = strip_y + 38
    terminal_h = command_y - terminal_y - 10
    draw_product_terminal(draw, preset, surface, x + 12, terminal_y, term_w - 18, terminal_h)
    detail_x = x + term_w + 2
    detail_w = w - term_w - 14
    draw_detail_panel(draw, preset, surface, detail_x, terminal_y, detail_w, terminal_h, heading="Session / SFTP")
    draw_securecrt_command_window(draw, preset, x + 12, command_y, w - 24, command_h)
    draw_product_activity_log(draw, preset, surface, x, log_y, w, y + h - log_y, "Session Log")


def draw_termius_workspace(
    draw: Any,
    preset: GuiDesignPreset,
    surface: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    log_h: int,
) -> None:
    c = preset.colors
    tabs_w = 86
    log_y = y + h - log_h
    draw_vertical_tabs(draw, preset, x, y, tabs_w, log_y - y - 8)
    pane_x = x + tabs_w
    pane_w = w - tabs_w
    pane_h = log_y - y - 8
    rounded(draw, (pane_x, y, pane_x + pane_w, y + pane_h), c.pane, c.pane_border, 5)
    draw.rectangle((pane_x + 12, y + 12, pane_x + pane_w - 12, y + 74), fill=c.toolbar, outline=c.pane_border)
    draw_text(draw, surface.title, pane_x + 26, y + 24, c.control_text, 15, bold=True)
    draw_text(draw, surface.subtitle, pane_x + 26, y + 47, c.sidebar_muted, 10)
    for index, chip in enumerate(gui_design_termius_header_chips()):
        chip_x = pane_x + pane_w - 360 + index * 116
        rounded(draw, (chip_x, y + 25, chip_x + 104, y + 51), c.control, c.control_border, 12)
        draw_text(draw, chip.label, chip_x + 10, y + 33, c.terminal_accent, 8, bold=True)
    draw_product_reference_state(draw, preset, pane_x + 12, y + 80, pane_w - 24, 24)
    strip_y = y + 110
    draw_termius_host_identity_strip(draw, preset, pane_x + 12, strip_y, pane_w - 24, 30)

    term_w = int(pane_w * 0.64)
    main_h = pane_h - 196
    flow_y = y + 98 + main_h
    terminal_y = strip_y + 38
    terminal_h = flow_y - terminal_y - 10
    draw_product_terminal(draw, preset, surface, pane_x + 12, terminal_y, term_w - 18, terminal_h)
    detail_x = pane_x + term_w + 4
    draw_detail_panel(
        draw,
        preset,
        surface,
        detail_x,
        terminal_y,
        pane_w - term_w - 16,
        terminal_h,
        heading="Vault / Snippets",
    )
    draw_termius_session_workflow(draw, preset, pane_x + 12, flow_y, pane_w - 24, y + pane_h - flow_y - 10)
    draw_product_activity_log(draw, preset, surface, x, log_y, w, y + h - log_y, "Sync Activity")


def draw_remmina_workspace(
    draw: Any,
    preset: GuiDesignPreset,
    surface: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    log_h: int,
) -> None:
    c = preset.colors
    tabs_h = 35
    log_y = y + h - log_h
    draw_tabs(draw, preset, x, y, w, tabs_h)
    pane_y = y + tabs_h
    pane_h = log_y - pane_y - 8
    rounded(draw, (x, pane_y, x + w, pane_y + pane_h), c.pane, c.pane_border, 4)
    toolbar_y = pane_y + 10
    draw.rectangle((x + 10, toolbar_y, x + w - 10, toolbar_y + 34), fill=c.toolbar, outline=c.pane_border)
    draw_text(draw, surface.title, x + 22, toolbar_y + 10, c.control_text, 13, bold=True)
    controls = gui_design_remmina_viewer_controls()
    control_x = x + w - 410
    for control in controls:
        width = 74
        rounded(draw, (control_x, toolbar_y + 7, control_x + width, toolbar_y + 27), c.control, c.control_border, 2)
        draw_remmina_viewer_control_icon(
            draw,
            control.icon_key,
            control_x + 6,
            toolbar_y + 10,
            12,
            c.primary,
            c.control_text,
        )
        draw_text(draw, control.label, control_x + 22, toolbar_y + 12, c.control_text, 8)
        control_x += 78
    draw_product_reference_state(draw, preset, x + 10, toolbar_y + 40, w - 20, 24)

    viewer_x = x + 18
    viewer_y = toolbar_y + 70
    viewer_w = int(w * 0.72)
    viewer_h = pane_h - 88
    draw_remote_viewer(draw, preset, surface, viewer_x, viewer_y, viewer_w, viewer_h)
    draw_detail_panel(
        draw,
        preset,
        surface,
        viewer_x + viewer_w + 12,
        viewer_y,
        w - viewer_w - 42,
        viewer_h,
        heading="Profile Options",
    )
    draw_product_activity_log(draw, preset, surface, x, log_y, w, y + h - log_y, "Connection Activity")


def draw_mremoteng_workspace(
    draw: Any,
    preset: GuiDesignPreset,
    surface: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    log_h: int,
) -> None:
    c = preset.colors
    tabs_h = 35
    log_y = y + h - log_h
    draw_tabs(draw, preset, x, y, w, tabs_h)
    pane_y = y + tabs_h
    pane_h = log_y - pane_y - 8
    rounded(draw, (x, pane_y, x + w, pane_y + pane_h), c.pane, c.pane_border, 2)
    header_y = pane_y + 8
    draw.rectangle((x + 10, header_y, x + w - 10, header_y + 30), fill=c.toolbar, outline=c.pane_border)
    draw_text(draw, surface.title, x + 22, header_y + 9, c.control_text, 12, bold=True)
    draw_text(draw, surface.secondary_state, x + w - 120, header_y + 9, c.status, 10, bold=True)
    draw_product_reference_state(draw, preset, x + 10, header_y + 36, w - 20, 24)

    draw_mremoteng_document_toolbar(draw, preset, x + 10, header_y + 66, w - 20, 28)

    top_y = header_y + 104
    top_h = int(pane_h * 0.40)
    left_w = int(w * 0.58)
    draw_product_terminal(draw, preset, surface, x + 12, top_y, left_w - 18, top_h)
    rdp_x = x + left_w + 2
    draw_mremoteng_rdp_panel(draw, preset, rdp_x, top_y, w - left_w - 14, top_h)
    props_y = top_y + top_h + 12
    draw_mremoteng_config_grid(draw, preset, surface, x + 12, props_y, w - 24, pane_y + pane_h - props_y - 10)
    draw_product_activity_log(draw, preset, surface, x, log_y, w, y + h - log_y, "Connection Log")


def draw_product_terminal(draw: Any, preset: GuiDesignPreset, surface: Any, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    rounded(draw, (x, y, x + w, y + h), c.terminal, c.pane_border, 2)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + 32), fill=c.toolbar)
    draw_text(draw, surface.primary_title, x + 12, y + 10, c.control_text, 11, bold=True)
    rounded(draw, (x + w - 104, y + 7, x + w - 14, y + 25), c.control, c.primary, 2)
    draw_text(draw, surface.primary_state, x + w - 96, y + 12, c.status, 8, bold=True)
    draw.rectangle((x + 1, y + 33, x + w - 1, y + 59), fill=c.control)
    draw_text(draw, surface.command_line, x + 12, y + 41, c.terminal_accent, 10, mono=True)
    lines = [
        "[note] profile mapped from shared preset surface",
        "[process running] stdout captured",
        "",
        *surface.detail_lines[:4],
        "",
        "$ row doctor --json",
        '  "ssh": true',
    ]
    line_y = y + 74
    for line in lines:
        if line_y > y + h - 18:
            break
        color = c.terminal_accent if line.startswith(("$", "initialized")) else c.terminal_text
        draw_text(draw, line, x + 12, line_y, color, 11, mono=True)
        line_y += 18


def draw_detail_panel(
    draw: Any,
    preset: GuiDesignPreset,
    surface: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    heading: str,
) -> None:
    c = preset.colors
    rounded(draw, (x, y, x + w, y + h), c.log, c.pane_border, 3)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + 30), fill=c.toolbar)
    draw_text(draw, heading, x + 10, y + 10, c.control_text, 11, bold=True)
    draw_text(draw, surface.secondary_state, x + w - 100, y + 10, c.status, 9, bold=True)
    draw_text(draw, surface.secondary_title, x + 10, y + 44, c.control_text, 12, bold=True)
    line_y = y + 70
    for line in surface.detail_lines:
        if line_y > y + h - 24:
            break
        draw_text(draw, line, x + 12, line_y, c.log_text, 10, mono=True)
        line_y += 20


def draw_securecrt_command_window(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_securecrt_command_window_chrome()
    rounded(draw, (x, y, x + w, y + h), c.log, c.pane_border, 2)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + 25), fill=c.toolbar)
    draw_text(draw, chrome.title, x + 10, y + 8, c.control_text, 10, bold=True)
    draw_text(draw, chrome.helper, x + 138, y + 8, c.sidebar_muted, 9)
    control_y = y + 31
    target_w = 112
    rounded(draw, (x + 10, control_y, x + 10 + target_w, y + h - 8), c.control, c.control_border, 2)
    draw_sidebar_row_icon(draw, preset, "database", x + 18, control_y + 6, 13, selected=False, group=False)
    draw_text(draw, chrome.target_scope, x + 38, control_y + 7, c.control_text, 9)
    input_x = x + 132
    send_w = 58
    draw.rectangle((input_x, control_y, x + w - send_w - 18, y + h - 8), fill=c.terminal, outline=c.primary)
    draw_text(draw, chrome.command, input_x + 10, control_y + 7, c.terminal_accent, 10, mono=True)
    rounded(draw, (x + w - send_w - 10, control_y, x + w - 10, y + h - 8), c.primary, c.primary, 2)
    draw_text(draw, chrome.send_label, x + w - send_w + 5, control_y + 7, c.primary_text, 9, bold=True)


def draw_securecrt_session_status_strip(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_securecrt_session_status_strip()
    rounded(draw, (x, y, x + w, y + h), c.pane, c.control_border, 2)
    draw_text(draw, chrome.title, x + 9, y + 10, c.sidebar_muted, 9, bold=True)
    cell_x = x + 96
    for field in chrome.fields:
        cell_w = field.static_width
        if cell_x + cell_w > x + w - 6:
            break
        cell_fill = c.primary if field.key == "state" else c.terminal
        cell_text = c.primary_text if field.key == "state" else c.control_text
        rounded(draw, (cell_x, y + 5, cell_x + cell_w, y + h - 5), cell_fill, c.control_border, 2)
        draw_text(draw, field.label, cell_x + 6, y + 9, c.sidebar_muted if field.key != "state" else c.primary_text, 8)
        draw_text(draw, field.value, cell_x + 48, y + 9, cell_text, 8, mono=True, bold=field.key == "state")
        cell_x += cell_w + 6


def draw_termius_session_workflow(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    rounded(draw, (x, y, x + w, y + h), c.log, c.pane_border, 5)
    draw_text(draw, "Host workflow", x + 12, y + 10, c.log_text, 12, bold=True)
    card_y = y + 34
    card_h = max(44, h - 44)
    gap = 10
    card_w = (w - gap * 2 - 24) // 3
    cards = [
        ("host", "Vault identity", "prod-ed25519 unlocked", "agent key chained"),
        ("sftp", "Port forward", "8080 -> localhost:80", "local tunnel ready"),
        ("snippet", "Snippet", "row vault status", "one-click command"),
    ]
    for index, (icon_key, title, primary, secondary) in enumerate(cards):
        cx = x + 12 + index * (card_w + gap)
        rounded(draw, (cx, card_y, cx + card_w, card_y + card_h), c.control, c.control_border, 8)
        draw_sidebar_row_icon(draw, preset, icon_key, cx + 12, card_y + 14, 18, selected=False, group=False)
        draw_text(draw, title, cx + 40, card_y + 10, c.control_text, 10, bold=True)
        draw_text(draw, primary, cx + 40, card_y + 28, c.terminal_accent, 9, mono=True)
        draw_text(draw, secondary, cx + 40, card_y + 45, c.sidebar_muted, 8)


def draw_termius_host_identity_strip(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    strip = gui_design_termius_host_identity_strip()
    rounded(draw, (x, y, x + w, y + h), c.pane, c.control_border, 2)
    draw_text(draw, strip.title, x + 9, y + 10, c.sidebar_muted, 9, bold=True)
    cell_x = x + 80
    for field in strip.fields:
        cell_w = field.static_width
        if cell_x + cell_w > x + w - 6:
            break
        cell_fill = c.primary if field.key == "sync" else c.terminal
        cell_text = c.primary_text if field.key == "sync" else c.control_text
        rounded(draw, (cell_x, y + 5, cell_x + cell_w, y + h - 5), cell_fill, c.control_border, 2)
        label_color = c.primary_text if field.key == "sync" else c.sidebar_muted
        draw_text(draw, field.label, cell_x + 6, y + 9, label_color, 8)
        draw_text(draw, field.value, cell_x + 42, y + 9, cell_text, 8, mono=True, bold=field.key == "sync")
        cell_x += cell_w + 6


def draw_remmina_viewer_control_icon(
    draw: Any,
    icon_key: str,
    x: int,
    y: int,
    size: int,
    color: str,
    text_color: str,
) -> None:
    if icon_key == "fit":
        draw.rectangle((x, y, x + size, y + size), fill=None, outline=color)
        draw.line((x + 2, y + 2, x + size - 3, y + size - 3), fill=color)
        draw.line((x + size - 3, y + 2, x + 2, y + size - 3), fill=color)
        return
    if icon_key == "scale":
        draw.rectangle((x + 1, y + 3, x + size - 1, y + size - 3), fill=None, outline=color)
        draw.line((x + 3, y + size - 5, x + size - 3, y + size - 5), fill=color, width=2)
        draw.line((x + 3, y + 5, x + 5, y + 5), fill=color, width=2)
        return
    if icon_key == "clipboard":
        draw.rectangle((x + 2, y + 3, x + size - 2, y + size), fill=None, outline=color)
        draw.rectangle((x + 4, y, x + size - 4, y + 4), fill=color)
        draw.line((x + 4, y + 7, x + size - 4, y + 7), fill=color)
        return
    if icon_key == "fullscreen":
        for x1, y1, x2, y2 in [
            (x, y + 4, x, y),
            (x, y, x + 4, y),
            (x + size, y + 4, x + size, y),
            (x + size - 4, y, x + size, y),
            (x, y + size - 4, x, y + size),
            (x, y + size, x + 4, y + size),
            (x + size, y + size - 4, x + size, y + size),
            (x + size - 4, y + size, x + size, y + size),
        ]:
            draw.line((x1, y1, x2, y2), fill=color, width=2)
        return
    if icon_key == "screenshot":
        draw.rectangle((x, y + 3, x + size, y + size - 1), fill=None, outline=color)
        draw.rectangle((x + 3, y + 1, x + 7, y + 4), fill=color)
        draw.ellipse((x + 4, y + 6, x + size - 4, y + size - 3), fill=None, outline=color)
        return
    draw_text(draw, icon_key[:1].upper(), x, y - 2, text_color, 9, bold=True)


def draw_remote_viewer(draw: Any, preset: GuiDesignPreset, surface: Any, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    rounded(draw, (x, y, x + w, y + h), "#d7e4ef", c.pane_border, 3)
    draw.rectangle((x + 12, y + 12, x + w - 12, y + 42), fill="#2f6fb1")
    draw_text(draw, surface.primary_title, x + 24, y + 21, "#ffffff", 12, bold=True)
    draw_text(draw, surface.primary_state, x + w - 114, y + 21, "#ffffff", 10)
    rounded(draw, (x + 20, y + 54, x + 42, y + h - 36), "#ecf3f9", "#9fb5c9", 2)
    for index, icon_key in enumerate(["scale", "clipboard", "fullscreen", "screenshot"]):
        iy = y + 66 + index * 31
        draw_remmina_viewer_control_icon(draw, icon_key, x + 25, iy, 12, "#2f6fb1", "#35516a")
    desktop_x = x + 58
    desktop_y = y + 66
    desktop_w = int(w * 0.55)
    desktop_h = h - 99
    draw.rectangle((desktop_x, desktop_y, desktop_x + desktop_w, desktop_y + desktop_h), fill="#ffffff", outline="#9fb5c9")
    draw.rectangle((desktop_x + 1, desktop_y + 1, desktop_x + desktop_w - 1, desktop_y + 25), fill="#2f6fb1")
    draw_text(draw, "remote desktop session", desktop_x + 12, desktop_y + 8, "#ffffff", 10, bold=True)
    draw.rectangle((desktop_x + 18, desktop_y + 48, desktop_x + desktop_w - 66, desktop_y + 72), fill="#e8eef5", outline="#c8d0d8")
    draw.rectangle((desktop_x + 18, desktop_y + 90, desktop_x + desktop_w - 34, desktop_y + 196), fill="#f5f8fb", outline="#c8d0d8")
    draw.rectangle((desktop_x + desktop_w - 54, desktop_y + 48, desktop_x + desktop_w - 20, desktop_y + 84), fill="#dce8f3", outline="#c8d0d8")
    draw.rectangle((desktop_x + 18, desktop_y + desktop_h - 28, desktop_x + desktop_w - 18, desktop_y + desktop_h - 12), fill="#2f6fb1")
    card_x = x + int(w * 0.65)
    card_y = y + 70
    for index, (title, value, icon_key) in enumerate(
        [
            ("Protocol", "RDP connected", "rdp"),
            ("Scale", "100% fit window", "scale"),
            ("Clipboard", "sync enabled", "clipboard"),
        ]
    ):
        cy = card_y + index * 70
        draw.rectangle((card_x, cy, x + w - 28, cy + 52), fill="#ffffff", outline="#9fb5c9")
        draw_sidebar_row_icon(draw, preset, icon_key, card_x + 14, cy + 16, 16, selected=False, group=False)
        draw_text(draw, title, card_x + 42, cy + 11, "#35516a", 10, bold=True)
        draw_text(draw, value, card_x + 42, cy + 29, "#687682", 9)
    draw.rectangle((x + 12, y + h - 25, x + w - 12, y + h - 12), fill="#2f6fb1")


def draw_mremoteng_document_toolbar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_mremoteng_document_toolbar_chrome()
    draw.rectangle((x, y, x + w, y + h), fill=c.control, outline=c.pane_border)
    draw_text(draw, chrome.title, x + 10, y + 8, c.control_text, 10, bold=True)
    button_x = x + 128
    for control in gui_design_mremoteng_document_controls():
        rounded(draw, (button_x, y + 4, button_x + control.static_width, y + h - 4), c.toolbar, c.control_border, 2)
        draw_sidebar_row_icon(draw, preset, control.icon_key, button_x + 8, y + 7, 13, selected=False, group=False)
        draw_text(draw, control.label, button_x + 27, y + 8, c.control_text, 9)
        button_x += control.static_width + 8
    draw.rectangle((x + w - 188, y + 5, x + w - 10, y + h - 5), fill=c.window, outline=c.control_border)
    draw_text(draw, chrome.filter_placeholder, x + w - 178, y + 9, c.sidebar_muted, 9)


def draw_mremoteng_config_grid(draw: Any, preset: GuiDesignPreset, surface: Any, x: int, y: int, w: int, h: int) -> None:
    draw_mremoteng_property_grid(draw, preset, x, y, w, h)


def draw_mremoteng_property_grid(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_mremoteng_property_grid_chrome()
    rounded(draw, (x, y, x + w, y + h), c.log, c.pane_border, 3)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + 30), fill=c.toolbar)
    draw_text(draw, chrome.title, x + 10, y + 10, c.control_text, 11, bold=True)
    draw_text(draw, chrome.scope_label, x + 145, y + 10, c.status, 9, bold=True)
    draw_text(draw, chrome.inheritance_label, x + w - 100, y + 10, c.status, 9, bold=True)
    table_x = x + 10
    table_y = y + 38
    col_w = [column.static_width for column in chrome.columns]
    available_width = w - 20
    width_delta = max(0, available_width - sum(col_w))
    col_w[-1] += width_delta
    row_h = 16
    draw.rectangle((table_x, table_y, x + w - 10, table_y + row_h), fill=c.toolbar, outline=c.pane_border)
    cx = table_x
    grid_bottom = table_y + row_h * (len(chrome.rows) + 1)
    for index, column in enumerate(chrome.columns):
        draw_text(draw, column.label, cx + 8, table_y + 4, c.control_text, 8, bold=True)
        cx += col_w[index]
        draw.line((cx, table_y, cx, grid_bottom), fill=c.pane_border)
    for row_index, row in enumerate(chrome.rows):
        ry = table_y + row_h * (row_index + 1)
        fill = c.log if row.inherited else c.window
        draw.rectangle((table_x, ry, x + w - 10, ry + row_h), fill=fill, outline=c.pane_border)
        cx = table_x
        values = (row.property_label, row.inherited_from, row.effective_value, row.source)
        for index, value in enumerate(values):
            color = c.status if index == 1 and row.inherited else c.log_text
            draw_text(draw, value, cx + 8, ry + 4, color, 8, mono=index > 1)
            cx += col_w[index]


def draw_mremoteng_rdp_panel(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    rounded(draw, (x, y, x + w, y + h), c.terminal, c.pane_border, 2)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + 31), fill=c.toolbar)
    draw_text(draw, "win-admin [RDP]", x + 10, y + 10, c.control_text, 11, bold=True)
    draw_text(draw, "document tab", x + w - 96, y + 10, c.sidebar_muted, 9)
    toolbar_y = y + 36
    for index, icon_key in enumerate(["rdp", "scale", "clipboard", "fullscreen"]):
        bx = x + 16 + index * 30
        draw.rectangle((bx, toolbar_y, bx + 22, toolbar_y + 20), fill=c.control, outline=c.control_border)
        draw_remmina_viewer_control_icon(draw, icon_key, bx + 5, toolbar_y + 4, 12, c.primary, c.control_text)
    screen_top = y + 64
    screen_bottom = y + h - 22
    title_top = screen_top + 20
    title_bottom = min(title_top + 26, screen_bottom - 74)
    if title_bottom < title_top + 18:
        title_bottom = title_top + 18
    viewer_top = title_bottom + 20
    viewer_bottom = min(max(viewer_top + 42, screen_bottom - 34), screen_bottom - 12)
    draw.rectangle((x + 16, screen_top, x + w - 16, screen_bottom), fill="#ecf2f8", outline=c.pane_border)
    draw.rectangle((x + 34, title_top, x + w - 52, title_bottom), fill="#c9d8e8", outline=c.pane_border)
    draw.rectangle((x + 34, viewer_top, x + w - 76, viewer_bottom), fill="#ffffff", outline=c.pane_border)
    draw_sidebar_row_icon(draw, preset, "rdp", x + 48, viewer_top + 14, 18, selected=False, group=False)
    draw_text(draw, "RDP viewer pane", x + 74, viewer_top + 16, c.terminal_text, 12, bold=True)
    draw_text(draw, "embedded document surface", x + 74, viewer_top + 38, c.sidebar_muted, 9)


def draw_product_activity_log(
    draw: Any,
    preset: GuiDesignPreset,
    surface: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
) -> None:
    c = preset.colors
    rounded(draw, (x, y, x + w, y + h), c.log, c.pane_border, 4)
    draw_text(draw, title, x + 12, y + 10, c.log_text, 13, bold=True)
    line_y = y + 34
    for line in surface.activity_lines:
        draw_text(draw, line, x + 12, line_y, c.log_text, 10, mono=True)
        line_y += 18


def draw_tabs(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    interaction = gui_design_interaction_state(preset.id)
    draw.rectangle((x, y, x + w, y + h), fill=c.pane)
    tx = x
    for label, status, active in gui_design_tab_items(preset.id):
        visible_status = interaction.active_tab_status if active else status
        tw = min(156, max(104, len(label) * 8 + 34))
        fill = c.tab_selected if active else c.tab
        text = c.tab_selected_text if active else c.tab_text
        rounded(draw, (tx, y, tx + tw, y + h - 2), fill, c.pane_border, 3)
        if active:
            draw.rectangle((tx + 3, y + 3, tx + tw - 3, y + h - 5), outline=c.control_hover)
        draw_text(draw, label, tx + 10, y + 8, text, 10, bold=active)
        draw_text(draw, visible_status, tx + 10, y + 21, c.sidebar_muted, 7)
        tx += tw + 3
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.pane_border)


def draw_vertical_tabs(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    interaction = gui_design_interaction_state(preset.id)
    draw.rectangle((x, y, x + w, y + h), fill=c.pane)
    ty = y
    for label, status, active in gui_design_tab_items(preset.id):
        visible_status = interaction.active_tab_status if active else status
        th = 72 if label != "+" else 48
        fill = c.tab_selected if active else c.tab
        text = c.tab_selected_text if active else c.tab_text
        rounded(draw, (x, ty, x + w - 4, ty + th - 3), fill, c.pane_border, 3)
        if active:
            draw.rectangle((x + 3, ty + 3, x + w - 7, ty + th - 6), outline=c.control_hover)
        draw_text(draw, label, x + 10, ty + 14, text, 10 if label != "+" else 16, bold=active or label == "+")
        if label != "+":
            draw_text(draw, visible_status, x + 10, ty + 34, c.sidebar_muted, 8)
        ty += th + 4
    draw.line((x + w - 1, y, x + w - 1, y + h), fill=c.pane_border)


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
    header_h = 34
    command_h = 26
    draw.rectangle((x + 1, y + 1, x + w - 1, y + header_h), fill=c.toolbar)
    draw_text(draw, title, x + 12, y + 10, c.control_text, 12, bold=True)
    draw_text(draw, "profile:ssh", x + 88, y + 11, c.sidebar_muted, 10)
    rounded(draw, (x + 160, y + 7, x + 214, y + 27), c.primary if main else c.control, c.primary, 2)
    draw_text(draw, "running" if main else "ready", x + 170, y + 12, c.primary_text if main else c.status, 9, bold=True)
    action_x = x + w - 238
    for label, bw in [("Start", 40), ("Restart", 54), ("Stop", 38), ("Copy", 40), ("Clear", 40)]:
        rounded(draw, (action_x, y + 6, action_x + bw, y + 28), c.control, c.control_border, 2)
        draw_text(draw, label, action_x + 5, y + 12, c.control_text, 9)
        action_x += bw + 6
    draw.rectangle((x + 1, y + header_h, x + w - 1, y + header_h + command_h), fill=c.control)
    draw_text(draw, "$ ssh -p 22 operator@edge-prod.example", x + 12, y + header_h + 8, c.terminal_accent, 11, mono=True)
    lines = [
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
    ly = y + header_h + command_h + 14
    for line in lines:
        color = c.terminal_accent if line.startswith("$") or line.startswith("initialized") else c.terminal_text
        draw_text(draw, line, x + 12, ly, color, 12, mono=True)
        ly += 19


def draw_workflow_dialog(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x + 8, y + 8, x + w + 8, y + h + 8), fill="#101010")
    rounded(draw, (x, y, x + w, y + h), c.pane, c.pane_border, 3)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + 38), fill=c.toolbar)
    draw_text(draw, "Tools workflow", x + 14, y + 11, c.control_text, 14, bold=True)
    draw_text(draw, "Profiles, transfers, diagnostics and saved layouts", x + 140, y + 12, c.sidebar_muted, 10)
    draw_text(draw, "-", x + w - 58, y + 11, c.sidebar_muted, 13, bold=True)
    draw_text(draw, "x", x + w - 30, y + 11, c.sidebar_muted, 13, bold=True)

    table_x = x + 14
    table_y = y + 55
    table_w = w - 28
    table_h = 138
    rounded(draw, (table_x, table_y, table_x + table_w, table_y + table_h), c.sidebar, c.pane_border, 2)
    draw.rectangle((table_x + 1, table_y + 1, table_x + table_w - 1, table_y + 25), fill=c.control)
    draw_text(draw, "Workflow", table_x + 10, table_y + 8, c.control_text, 10, bold=True)
    draw_text(draw, "State", table_x + 180, table_y + 8, c.control_text, 10, bold=True)
    draw_text(draw, "Detail", table_x + 260, table_y + 8, c.control_text, 10, bold=True)
    rows = [
        ("Profile editor", "6 saved", "Create, edit or remove connection profiles"),
        ("Transfer queue", "ready", "Preview SFTP get, put, mkdir and delete operations"),
        ("Layouts", "3 saved", "Open grid, horizontal or vertical multi-pane layouts"),
        ("Doctor", "ready", "Inspect local protocol clients and launch readiness"),
    ]
    row_y = table_y + 31
    for index, (workflow, state, detail) in enumerate(rows):
        if index == 1:
            draw.rectangle((table_x + 4, row_y - 3, table_x + table_w - 4, row_y + 17), fill=c.sidebar_selected)
            text_color = c.sidebar_selected_text
        else:
            text_color = c.sidebar_text
        draw_text(draw, workflow, table_x + 10, row_y, text_color, 10)
        draw_text(draw, state, table_x + 180, row_y, c.status if state == "ready" else text_color, 10, bold=state == "ready")
        draw_text(draw, detail, table_x + 260, row_y, c.sidebar_muted if index != 1 else c.sidebar_selected_text, 9)
        row_y += 26

    preview_y = table_y + table_h + 12
    preview_h = 74
    rounded(draw, (table_x, preview_y, table_x + table_w, preview_y + preview_h), c.terminal, c.pane_border, 2)
    detail_lines = [
        "Tools workflow",
        "Profiles: 6",
        "Layouts: 3",
        "Use action buttons below to open the most common tools.",
    ]
    line_y = preview_y + 11
    for line in detail_lines:
        draw_text(draw, line, table_x + 12, line_y, c.terminal_accent if ":" in line else c.terminal_text, 10, mono=True)
        line_y += 15

    button_y = y + h - 43
    button_x = x + 14
    for label, width, primary in [
        ("New profile", 92, False),
        ("New layout", 86, False),
        ("Run doctor", 90, True),
        ("Close", 58, False),
    ]:
        fill = c.primary if primary else c.control
        outline = c.primary if primary else c.control_border
        text = c.primary_text if primary else c.control_text
        rounded(draw, (button_x, button_y, button_x + width, button_y + 26), fill, outline, 2)
        draw_text(draw, label, button_x + 10, button_y + 8, text, 10, bold=True)
        button_x += width + 8


def draw_status_bar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y, x + w, y), fill=c.toolbar_border)
    segments = gui_design_status_segments(preset.id)
    if preset.id == "mobaxterm":
        chrome = gui_design_moba_status_bar_chrome()
        draw_text(draw, chrome.notice, x + 6, y + 6, c.control_text, 10, bold=True)
        draw_text(draw, f" - {chrome.product_note}", x + 142, y + 6, c.sidebar_muted, 10)
        draw.rectangle((x + w - 20, y + 6, x + w - 6, y + 16), outline=c.sidebar_muted)
        draw_status_segments(draw, tuple(segment.text for segment in gui_design_moba_status_segments()), x + w - 360, y, c)
        return
    draw_text(draw, preset.description, x + 14, y + 6, c.sidebar_muted, 10)
    draw_status_segments(draw, segments, x + w - 430, y, c)


def draw_status_segments(draw: Any, segments: tuple[str, ...], x: int, y: int, c) -> None:
    segment_x = x
    for text in segments:
        draw.line((segment_x - 8, y + 4, segment_x - 8, y + 20), fill=c.toolbar_border)
        draw_text(draw, text, segment_x, y + 6, c.sidebar_muted, 10)
        segment_x += max(116, len(text) * 7 + 20)


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


def draw_centered_text(
    draw: Any,
    text: str,
    x: int,
    y: int,
    w: int,
    fill: str,
    size: int,
    *,
    bold: bool = False,
    mono: bool = False,
) -> None:
    text_font = font(size, bold=bold, mono=mono)
    bbox = draw.textbbox((0, 0), text, font=text_font)
    text_w = bbox[2] - bbox[0]
    draw.text((x + max(0, (w - text_w) // 2), y), text, fill=fill, font=text_font)


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

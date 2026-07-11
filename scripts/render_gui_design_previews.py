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

from remote_ops_workspace.gui import quick_connect_candidates  # noqa: E402
from remote_ops_workspace.gui_designs import (  # noqa: E402
    GUI_DESIGN_PRESETS,
    PRODUCT_GUI_PRESET_IDS,
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    GuiDesignPreset,
    gui_design_command_surface_actions,
    gui_design_home_tab_label,
    gui_design_interaction_state,
    gui_design_moba_bottom_edge_controls,
    gui_design_moba_connected_dock_frame,
    gui_design_moba_follow_terminal_folder_control_route,
    gui_design_moba_home_welcome_chrome,
    gui_design_moba_home_welcome_geometry,
    gui_design_moba_monitoring_control_geometry_for,
    gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics,
    gui_design_moba_monitoring_telemetry_route,
    gui_design_moba_quick_connect_chrome,
    gui_design_moba_quick_connect_suggestion_chrome,
    gui_design_moba_rail_chrome,
    gui_design_moba_rail_item_geometry_for,
    gui_design_moba_rail_items,
    gui_design_moba_remote_monitoring_control_route,
    gui_design_moba_remote_monitoring_dock_chrome,
    gui_design_moba_ribbon_action_geometry_for,
    gui_design_moba_ribbon_actions,
    gui_design_moba_ribbon_edge_action_route,
    gui_design_moba_ribbon_edge_actions,
    gui_design_moba_right_utility_action_route,
    gui_design_moba_right_utility_actions,
    gui_design_moba_right_utility_rail_chrome,
    gui_design_moba_session_edge_action_route,
    gui_design_moba_session_edge_actions,
    gui_design_moba_session_tree_chrome,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_sftp_file_row_icon,
    gui_design_moba_sftp_follow_folder_route,
    gui_design_moba_sftp_routed_file_rows,
    gui_design_moba_sftp_toolbar_action_geometry,
    gui_design_moba_sftp_toolbar_action_geometry_for,
    gui_design_moba_sftp_toolbar_action_route,
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_ssh_banner_row_geometry_for,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_terminal_transcript_row_geometry_for,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_menu_geometry_for,
    gui_design_moba_top_menu_items,
    gui_design_moba_top_stack_geometry,
    gui_design_mremoteng_connection_document_route,
    gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_filter_route,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_inheritance_route,
    gui_design_mremoteng_property_grid_chrome,
    gui_design_mremoteng_top_chrome,
    gui_design_preset_catalog_route,
    gui_design_preset_command_surface_route,
    gui_design_preset_focus_interaction_route,
    gui_design_preset_home_search_route,
    gui_design_preset_ids,
    gui_design_preset_isolation_route,
    gui_design_preset_keyboard_shortcut_route,
    gui_design_preset_reference_control_route,
    gui_design_preset_reference_input_route,
    gui_design_preset_reference_session_action_route,
    gui_design_preset_reference_status_bar_route,
    gui_design_preset_reference_surface_route,
    gui_design_preset_reference_tab_chrome_route,
    gui_design_preset_reference_tab_route,
    gui_design_preset_reference_transcript_route,
    gui_design_preset_selection_route,
    gui_design_preset_transition_route,
    gui_design_preset_visual_signature,
    gui_design_product_identity_route,
    gui_design_reference_state,
    gui_design_remmina_clipboard_route,
    gui_design_remmina_profile_filter_route,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_profile_viewer_route,
    gui_design_remmina_screenshot_route,
    gui_design_remmina_sftp_transfer_route,
    gui_design_remmina_viewer_controls,
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_command_window_send_route,
    gui_design_securecrt_session_manager_chrome,
    gui_design_securecrt_session_manager_filter_route,
    gui_design_securecrt_session_manager_route,
    gui_design_securecrt_session_status_strip,
    gui_design_securecrt_sftp_browser_route,
    gui_design_securecrt_sftp_tab_route,
    gui_design_securecrt_top_chrome,
    gui_design_sidebar_copy,
    gui_design_status_segments,
    gui_design_tab_items,
    gui_design_termius_files_browser_route,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_termius_host_selection_route,
    gui_design_termius_hosts_chrome,
    gui_design_termius_port_forward_route,
    gui_design_termius_snippet_route,
    gui_design_termius_sync_route,
    gui_design_toolbar_actions,
    gui_design_tree_root_copy,
    gui_design_tree_root_icon,
    gui_design_tree_row_icon_key,
    gui_design_tree_rows,
    gui_design_workflow_cards,
    gui_design_workspace_surface,
)
from remote_ops_workspace.moba_connected import (  # noqa: E402
    MobaConnectedSessionState,
    build_moba_connected_session_state,
    moba_connected_session_action_route,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_connected_tab_chrome_geometry_for,
    moba_connected_tab_chrome_items,
    moba_connected_window_title,
    moba_sftp_terminal_folder_route,
    moba_telemetry_cell_geometry,
    moba_telemetry_cell_geometry_for,
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
    variant_id: str = "primary"
    variant_label: str = ""
    variant_description: str = ""

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
        if preset.id == "mobaxterm":
            home_image = render_mobaxterm_home_preset(preset)
            artifacts.append(
                PreviewArtifact(
                    path=out_dir / "mobaxterm-home.png",
                    png_bytes=image_to_png_bytes(home_image),
                    width=PREVIEW_SIZE[0],
                    height=PREVIEW_SIZE[1],
                    preset=preset,
                    variant_id="home",
                    variant_label="MobaXterm-style Home",
                    variant_description=(
                        "Home/welcome state with Quick Connect, session tree, centered actions, "
                        "session search and recent sessions."
                    ),
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
    preview_artifacts = [
        artifact for artifact in artifacts if artifact.preset is not None and artifact.variant_id == "primary"
    ]
    state_artifacts = [
        artifact for artifact in artifacts if artifact.preset is not None and artifact.variant_id != "primary"
    ]
    contact_artifact = next((artifact for artifact in artifacts if artifact.preset is None), None)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "renderer": "scripts/render_gui_design_previews.py",
        "preview_size": {"width": PREVIEW_SIZE[0], "height": PREVIEW_SIZE[1]},
        "contact_thumb": {"width": CONTACT_THUMB[0], "height": CONTACT_THUMB[1]},
        "presets": [preset_manifest(artifact) for artifact in preview_artifacts],
        "state_previews": [state_preview_manifest(artifact) for artifact in state_artifacts],
    }
    if contact_artifact is not None:
        manifest["contact_sheet"] = image_manifest(contact_artifact)
    return manifest


def preset_manifest(artifact: PreviewArtifact) -> dict[str, Any]:
    if artifact.preset is None:
        raise ValueError("preset artifact required")
    preset = artifact.preset
    catalog_route = gui_design_preset_catalog_route()
    isolation_route = gui_design_preset_isolation_route(preset.id)
    selection_route = gui_design_preset_selection_route(preset.id)
    transition_route = gui_design_preset_transition_route(preset.id)
    keyboard_shortcut_route = (
        gui_design_preset_keyboard_shortcut_route(preset.id)
        if preset.id in PRODUCT_GUI_PRESET_IDS
        else None
    )
    command_surface_route = (
        gui_design_preset_command_surface_route(preset.id)
        if preset.id in PRODUCT_GUI_PRESET_IDS
        else None
    )
    focus_interaction_route = (
        gui_design_preset_focus_interaction_route(preset.id)
        if preset.id in PRODUCT_GUI_PRESET_IDS
        else None
    )
    home_search_route = (
        gui_design_preset_home_search_route(preset.id)
        if preset.id in PRODUCT_GUI_PRESET_IDS
        else None
    )
    reference_tab_route = (
        gui_design_preset_reference_tab_route(preset.id)
        if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        else None
    )
    reference_tab_chrome_route = (
        gui_design_preset_reference_tab_chrome_route(preset.id)
        if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        else None
    )
    reference_status_route = (
        gui_design_preset_reference_status_bar_route(preset.id)
        if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        else None
    )
    reference_session_action_route = (
        gui_design_preset_reference_session_action_route(preset.id)
        if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        else None
    )
    reference_surface_route = (
        gui_design_preset_reference_surface_route(preset.id)
        if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        else None
    )
    reference_control_route = (
        gui_design_preset_reference_control_route(preset.id)
        if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        else None
    )
    reference_input_route = (
        gui_design_preset_reference_input_route(preset.id)
        if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        else None
    )
    reference_transcript_route = (
        gui_design_preset_reference_transcript_route(preset.id)
        if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        else None
    )
    moba_connected_manifest_state = moba_preview_reference_state() if preset.id == "mobaxterm" else None
    moba_connected_action_route = (
        moba_connected_session_action_route(moba_connected_manifest_state)
        if moba_connected_manifest_state is not None
        else None
    )
    moba_remote_monitoring_control_route = (
        gui_design_moba_remote_monitoring_control_route() if preset.id == "mobaxterm" else None
    )
    moba_follow_terminal_folder_control_route = (
        gui_design_moba_follow_terminal_folder_control_route() if preset.id == "mobaxterm" else None
    )
    securecrt_session_manager_filter_route = (
        gui_design_securecrt_session_manager_filter_route() if preset.id == "securecrt" else None
    )
    securecrt_command_window_send_route = (
        gui_design_securecrt_command_window_send_route() if preset.id == "securecrt" else None
    )
    securecrt_sftp_tab_route = (
        gui_design_securecrt_sftp_tab_route() if preset.id == "securecrt" else None
    )
    securecrt_sftp_browser_route = (
        gui_design_securecrt_sftp_browser_route() if preset.id == "securecrt" else None
    )
    remmina_profile_filter_route = (
        gui_design_remmina_profile_filter_route() if preset.id == "remmina" else None
    )
    remmina_screenshot_route = (
        gui_design_remmina_screenshot_route() if preset.id == "remmina" else None
    )
    remmina_sftp_transfer_route = (
        gui_design_remmina_sftp_transfer_route() if preset.id == "remmina" else None
    )
    mremoteng_connection_document_route = (
        gui_design_mremoteng_connection_document_route() if preset.id == "mremoteng" else None
    )
    mremoteng_document_filter_route = (
        gui_design_mremoteng_document_filter_route() if preset.id == "mremoteng" else None
    )
    mremoteng_inheritance_route = (
        gui_design_mremoteng_inheritance_route() if preset.id == "mremoteng" else None
    )
    termius_port_forward_route = (
        gui_design_termius_port_forward_route() if preset.id == "termius" else None
    )
    termius_snippet_route = (
        gui_design_termius_snippet_route() if preset.id == "termius" else None
    )
    termius_files_browser_route = (
        gui_design_termius_files_browser_route() if preset.id == "termius" else None
    )
    moba_ribbon_edge_action_route = (
        gui_design_moba_ribbon_edge_action_route() if preset.id == "mobaxterm" else None
    )
    moba_right_utility_action_route = (
        gui_design_moba_right_utility_action_route() if preset.id == "mobaxterm" else None
    )
    moba_session_edge_action_route = (
        gui_design_moba_session_edge_action_route() if preset.id == "mobaxterm" else None
    )
    moba_sftp_toolbar_action_route = (
        gui_design_moba_sftp_toolbar_action_route() if preset.id == "mobaxterm" else None
    )
    visual_signature = gui_design_preset_visual_signature(preset.id)
    if preset.id not in catalog_route.option_ids:
        raise RuntimeError(f"{preset.id} preset catalog route missing active preset id")
    if preset.label not in catalog_route.option_labels:
        raise RuntimeError(f"{preset.id} preset catalog route missing active preset label")
    if selection_route.preset_id != preset.id:
        raise RuntimeError(f"{preset.id} preset-selection route preset id drifted")
    if selection_route.preset_label != preset.label:
        raise RuntimeError(f"{preset.id} preset-selection route label drifted")
    if selection_route.home_tab_label != gui_design_home_tab_label(preset.id):
        raise RuntimeError(f"{preset.id} preset-selection route home tab drifted")
    if selection_route.status_segments != gui_design_status_segments(preset.id):
        raise RuntimeError(f"{preset.id} preset-selection route status segments drifted")
    if visual_signature.preset_id != preset.id:
        raise RuntimeError(f"{preset.id} visual signature preset id drifted")
    if visual_signature.density != preset.density:
        raise RuntimeError(f"{preset.id} visual signature density drifted")
    if visual_signature.tab_position != preset.tab_position:
        raise RuntimeError(f"{preset.id} visual signature tab position drifted")
    if visual_signature.palette_items()[0][1] != preset.colors.window:
        raise RuntimeError(f"{preset.id} visual signature window color drifted")
    if visual_signature.terminal_accent_color != preset.colors.terminal_accent:
        raise RuntimeError(f"{preset.id} visual signature terminal accent drifted")
    isolation_overlap = set(isolation_route.visible_objects) & set(isolation_route.hidden_objects)
    if isolation_overlap:
        raise RuntimeError(f"{preset.id} preset isolation route has overlapping objects: {sorted(isolation_overlap)}")
    if isolation_route.preset_id != preset.id:
        raise RuntimeError(f"{preset.id} preset isolation route preset id drifted")
    if transition_route.to_preset_id != preset.id:
        raise RuntimeError(f"{preset.id} preset transition route target preset id drifted")
    if transition_route.to_preset_index != selection_route.preset_index:
        raise RuntimeError(f"{preset.id} preset transition route target index drifted")
    if set(transition_route.from_preset_ids) & {preset.id}:
        raise RuntimeError(f"{preset.id} preset transition route includes active preset as a source")
    if set(transition_route.reset_objects) != set(isolation_route.hidden_objects):
        raise RuntimeError(f"{preset.id} preset transition route reset objects drifted from isolation")
    if keyboard_shortcut_route is not None:
        if keyboard_shortcut_route.preset_id != preset.id:
            raise RuntimeError(f"{preset.id} keyboard shortcut route preset id drifted")
        if keyboard_shortcut_route.expected_shortcut_count != len(
            keyboard_shortcut_route.expected_shortcut_keys
        ):
            raise RuntimeError(f"{preset.id} keyboard shortcut route key count drifted")
        if len(keyboard_shortcut_route.expected_shortcut_keys) != len(keyboard_shortcut_route.expected_sequences):
            raise RuntimeError(f"{preset.id} keyboard shortcut route sequence count drifted")
        if len(keyboard_shortcut_route.expected_sequences) != len(
            keyboard_shortcut_route.expected_action_labels
        ):
            raise RuntimeError(f"{preset.id} keyboard shortcut route action label count drifted")
        if "Ctrl+T" not in keyboard_shortcut_route.expected_sequences:
            raise RuntimeError(f"{preset.id} keyboard shortcut route missing terminal shortcut")
    if command_surface_route is not None:
        actions = gui_design_command_surface_actions(preset.id)
        expected_command_object = "mobaRibbonButton" if preset.id == "mobaxterm" else "productToolbarButton"
        if command_surface_route.preset_id != preset.id:
            raise RuntimeError(f"{preset.id} command surface route preset id drifted")
        if command_surface_route.toolbar_object != "mainToolbar":
            raise RuntimeError(f"{preset.id} command surface route toolbar object drifted")
        if command_surface_route.command_object != expected_command_object:
            raise RuntimeError(f"{preset.id} command surface route command object drifted")
        if command_surface_route.expected_action_count != len(actions):
            raise RuntimeError(f"{preset.id} command surface route action count drifted")
        if command_surface_route.expected_action_keys != tuple(key for key, _label, _tooltip in actions):
            raise RuntimeError(f"{preset.id} command surface route action keys drifted")
        if command_surface_route.expected_action_labels != tuple(label for _key, label, _tooltip in actions):
            raise RuntimeError(f"{preset.id} command surface route action labels drifted")
        if command_surface_route.expected_action_tooltips != tuple(tooltip for _key, _label, tooltip in actions):
            raise RuntimeError(f"{preset.id} command surface route action tooltips drifted")
    if focus_interaction_route is not None:
        interaction = gui_design_interaction_state(preset.id)
        if focus_interaction_route.preset_id != preset.id:
            raise RuntimeError(f"{preset.id} focus interaction route preset id drifted")
        if focus_interaction_route.focused_control != interaction.focused_control:
            raise RuntimeError(f"{preset.id} focus interaction route focused control drifted")
        if focus_interaction_route.active_toolbar_key != interaction.active_toolbar_key:
            raise RuntimeError(f"{preset.id} focus interaction route active key drifted")
        if focus_interaction_route.checked_toolbar_key != interaction.checked_toolbar_key:
            raise RuntimeError(f"{preset.id} focus interaction route checked key drifted")
        if focus_interaction_route.disabled_toolbar_key != interaction.disabled_toolbar_key:
            raise RuntimeError(f"{preset.id} focus interaction route disabled key drifted")
        if focus_interaction_route.selected_tree_label != interaction.selected_tree_label:
            raise RuntimeError(f"{preset.id} focus interaction route selected row drifted")
        if focus_interaction_route.status_note != interaction.status_note:
            raise RuntimeError(f"{preset.id} focus interaction route status note drifted")
    if home_search_route is not None:
        if focus_interaction_route is None:
            raise RuntimeError(f"{preset.id} home search route missing focus interaction route")
        surface = gui_design_workspace_surface(preset.id)
        expected_recent_labels = tuple(item for column in surface.recent_columns for item in column)
        if home_search_route.preset_id != preset.id:
            raise RuntimeError(f"{preset.id} home search route preset id drifted")
        if home_search_route.placeholder_text != surface.home_search_placeholder:
            raise RuntimeError(f"{preset.id} home search route placeholder drifted")
        if home_search_route.entry_search_object != focus_interaction_route.focus_object:
            raise RuntimeError(f"{preset.id} home search route entry object drifted")
        if home_search_route.expected_home_actions != surface.home_actions:
            raise RuntimeError(f"{preset.id} home search route action metadata drifted")
        if home_search_route.expected_recent_labels != expected_recent_labels:
            raise RuntimeError(f"{preset.id} home search route recent label metadata drifted")
    if moba_ribbon_edge_action_route is not None:
        edge_actions = {action.key: action for action in gui_design_moba_ribbon_edge_actions()}
        for action_key in (
            moba_ribbon_edge_action_route.xserver_action_key,
            moba_ribbon_edge_action_route.exit_action_key,
        ):
            if action_key not in edge_actions:
                raise RuntimeError("Moba ribbon edge action route references a missing action")
            gui_design_moba_ribbon_action_geometry_for(action_key)
        xserver_action = edge_actions[moba_ribbon_edge_action_route.xserver_action_key]
        exit_action = edge_actions[moba_ribbon_edge_action_route.exit_action_key]
        if xserver_action.label != moba_ribbon_edge_action_route.xserver_action_label:
            raise RuntimeError("Moba ribbon edge action route X server label drifted")
        if xserver_action.icon_key != moba_ribbon_edge_action_route.xserver_icon_key:
            raise RuntimeError("Moba ribbon edge action route X server icon drifted")
        if exit_action.label != moba_ribbon_edge_action_route.exit_action_label:
            raise RuntimeError("Moba ribbon edge action route Exit label drifted")
        if exit_action.icon_key != moba_ribbon_edge_action_route.exit_icon_key:
            raise RuntimeError("Moba ribbon edge action route Exit icon drifted")
        if moba_ribbon_edge_action_route.xserver_dialog_detail != "X server workflow":
            raise RuntimeError("Moba ribbon edge action route X server dialog detail drifted")
        if moba_ribbon_edge_action_route.toolbar_object != "mainToolbar":
            raise RuntimeError("Moba ribbon edge action route toolbar object drifted")
        if moba_ribbon_edge_action_route.spacer_object != "mobaToolbarSpacer":
            raise RuntimeError("Moba ribbon edge action route spacer object drifted")
    if moba_right_utility_action_route is not None:
        utility_actions = {action.key: action for action in gui_design_moba_right_utility_actions()}
        if moba_right_utility_action_route.rail_object != "mobaRightUtilityRail":
            raise RuntimeError("Moba right utility action route rail object drifted")
        if moba_right_utility_action_route.action_object != "mobaRightUtilityAction":
            raise RuntimeError("Moba right utility action route action object drifted")
        if tuple(utility_actions) != moba_right_utility_action_route.action_keys:
            raise RuntimeError("Moba right utility action route key order drifted")
        if tuple(action.label for action in utility_actions.values()) != moba_right_utility_action_route.action_labels:
            raise RuntimeError("Moba right utility action route label metadata drifted")
        if tuple(action.icon_key for action in utility_actions.values()) != moba_right_utility_action_route.action_icon_keys:
            raise RuntimeError("Moba right utility action route icon metadata drifted")
        if "show_moba_clipboard_hints" not in moba_right_utility_action_route.action_handlers:
            raise RuntimeError("Moba right utility action route clipboard handler missing")
    if moba_session_edge_action_route is not None:
        session_edge_actions = {action.key: action for action in gui_design_moba_session_edge_actions()}
        if moba_session_edge_action_route.controls_object != "mobaSessionEdgeControls":
            raise RuntimeError("Moba session-edge action route controls object drifted")
        if moba_session_edge_action_route.action_object != "mobaSessionEdgeAction":
            raise RuntimeError("Moba session-edge action route action object drifted")
        if moba_session_edge_action_route.placement != "tab-strip-overlay":
            raise RuntimeError("Moba session-edge action route placement drifted")
        if tuple(session_edge_actions) != moba_session_edge_action_route.action_keys:
            raise RuntimeError("Moba session-edge action route key order drifted")
        if tuple(action.label for action in session_edge_actions.values()) != moba_session_edge_action_route.action_labels:
            raise RuntimeError("Moba session-edge action route label metadata drifted")
        if tuple(action.icon_key for action in session_edge_actions.values()) != moba_session_edge_action_route.action_icon_keys:
            raise RuntimeError("Moba session-edge action route icon metadata drifted")
        if "show_moba_session_attachment" not in moba_session_edge_action_route.action_handlers:
            raise RuntimeError("Moba session-edge action route attachment handler missing")
    if moba_sftp_toolbar_action_route is not None:
        sftp_actions = {action.key: action for action in gui_design_moba_sftp_dock_actions()}
        if moba_sftp_toolbar_action_route.toolbar_object != "mobaSftpToolbar":
            raise RuntimeError("Moba SFTP toolbar action route toolbar object drifted")
        if moba_sftp_toolbar_action_route.action_object != "mobaSftpAction":
            raise RuntimeError("Moba SFTP toolbar action route action object drifted")
        if moba_sftp_toolbar_action_route.target_path_object != "mobaSftpPath":
            raise RuntimeError("Moba SFTP toolbar action route path object drifted")
        if moba_sftp_toolbar_action_route.target_table_object != "mobaSftpFileTable":
            raise RuntimeError("Moba SFTP toolbar action route table object drifted")
        if tuple(sftp_actions) != moba_sftp_toolbar_action_route.action_keys:
            raise RuntimeError("Moba SFTP toolbar action route key order drifted")
        if tuple(action.label for action in sftp_actions.values()) != moba_sftp_toolbar_action_route.action_labels:
            raise RuntimeError("Moba SFTP toolbar action route label metadata drifted")
        if tuple(action.icon_key for action in sftp_actions.values()) != moba_sftp_toolbar_action_route.action_icon_keys:
            raise RuntimeError("Moba SFTP toolbar action route icon metadata drifted")
        if tuple(action.group_key for action in sftp_actions.values()) != moba_sftp_toolbar_action_route.action_group_keys:
            raise RuntimeError("Moba SFTP toolbar action route group metadata drifted")
        if "show_moba_sftp_toolbar_action" not in moba_sftp_toolbar_action_route.action_handlers:
            raise RuntimeError("Moba SFTP toolbar action route handler missing")
        if "queued" not in moba_sftp_toolbar_action_route.action_statuses:
            raise RuntimeError("Moba SFTP toolbar action route queued status missing")
        if moba_sftp_toolbar_action_route.signal != "clicked":
            raise RuntimeError("Moba SFTP toolbar action route signal drifted")
        if moba_sftp_toolbar_action_route.signal_property != "mobaSftpToolbarRouteSignal":
            raise RuntimeError("Moba SFTP toolbar action route signal property drifted")
        if moba_sftp_toolbar_action_route.captured_action_property != "mobaSftpToolbarRouteCapturedAction":
            raise RuntimeError("Moba SFTP toolbar action route captured action property drifted")
        if moba_sftp_toolbar_action_route.live_action_property != "mobaSftpToolbarRouteLiveAction":
            raise RuntimeError("Moba SFTP toolbar action route live action property drifted")
    if reference_tab_route is not None:
        product_identity_route = gui_design_product_identity_route(preset.id)
        if reference_tab_route.reference_profile != product_identity_route.selected_profile_name:
            raise RuntimeError(f"{preset.id} reference tab route profile metadata drifted")
        if reference_tab_route.active_tab_label != product_identity_route.active_tab_label:
            raise RuntimeError(f"{preset.id} reference tab route active tab metadata drifted")
        if reference_tab_route.home_tab_label != selection_route.home_tab_label:
            raise RuntimeError(f"{preset.id} reference tab route home tab metadata drifted")
    if reference_tab_chrome_route is not None:
        if reference_tab_route is None:
            raise RuntimeError(f"{preset.id} reference tab chrome route missing tab route")
        if reference_tab_chrome_route.reference_profile != reference_tab_route.reference_profile:
            raise RuntimeError(f"{preset.id} reference tab chrome route profile metadata drifted")
        if reference_tab_chrome_route.active_tab_label != reference_tab_route.active_tab_label:
            raise RuntimeError(f"{preset.id} reference tab chrome route active tab metadata drifted")
        if reference_tab_chrome_route.expected_tab_position != selection_route.tab_position:
            raise RuntimeError(f"{preset.id} reference tab chrome route tab position drifted")
        if not reference_tab_chrome_route.expected_tooltip.startswith(reference_tab_route.active_tab_label):
            raise RuntimeError(f"{preset.id} reference tab chrome route tooltip drifted")
    if reference_status_route is not None:
        product_identity_route = gui_design_product_identity_route(preset.id)
        if reference_tab_route is None:
            raise RuntimeError(f"{preset.id} reference status-bar route missing tab route")
        if reference_status_route.reference_profile != reference_tab_route.reference_profile:
            raise RuntimeError(f"{preset.id} reference status-bar route profile metadata drifted")
        if reference_status_route.active_tab_label != reference_tab_route.active_tab_label:
            raise RuntimeError(f"{preset.id} reference status-bar route active tab metadata drifted")
        if reference_status_route.expected_status_segments != product_identity_route.status_segments:
            raise RuntimeError(f"{preset.id} reference status-bar route status segment metadata drifted")
        if reference_status_route.expected_segment_count != len(product_identity_route.status_segments):
            raise RuntimeError(f"{preset.id} reference status-bar route segment count drifted")
    if reference_session_action_route is not None:
        if reference_tab_route is None:
            raise RuntimeError(f"{preset.id} reference session action route missing tab route")
        if reference_session_action_route.reference_profile != reference_tab_route.reference_profile:
            raise RuntimeError(f"{preset.id} reference session action route profile metadata drifted")
        if reference_session_action_route.active_tab_label != reference_tab_route.active_tab_label:
            raise RuntimeError(f"{preset.id} reference session action route active tab metadata drifted")
        if reference_session_action_route.expected_action_count != len(
            reference_session_action_route.expected_action_keys
        ):
            raise RuntimeError(f"{preset.id} reference session action route action count drifted")
        if len(reference_session_action_route.expected_action_keys) != len(
            reference_session_action_route.expected_action_labels
        ):
            raise RuntimeError(f"{preset.id} reference session action route label metadata drifted")
        if "close-other-tabs" not in reference_session_action_route.conditional_enabled_action_keys:
            raise RuntimeError(f"{preset.id} reference session action route conditional action drifted")
    if moba_connected_action_route is not None:
        tab_items = moba_connected_tab_chrome_items(moba_connected_manifest_state)
        if moba_connected_action_route.active_tab_key not in {item.key for item in tab_items if item.active}:
            raise RuntimeError("Moba connected session action route active tab key drifted")
        if moba_connected_action_route.reference_tab_label not in {item.label for item in tab_items}:
            raise RuntimeError("Moba connected session action route reference tab label drifted")
        if moba_connected_action_route.expected_action_count != len(
            moba_connected_action_route.expected_action_keys
        ):
            raise RuntimeError("Moba connected session action route action count drifted")
        if len(moba_connected_action_route.expected_action_keys) != len(
            moba_connected_action_route.expected_action_labels
        ):
            raise RuntimeError("Moba connected session action route label metadata drifted")
        if moba_connected_action_route.menu_object != "mobaConnectedSessionTabContextMenu":
            raise RuntimeError("Moba connected session action route menu object drifted")
        if "close-other-tabs" not in moba_connected_action_route.conditional_enabled_action_keys:
            raise RuntimeError("Moba connected session action route conditional action drifted")
    if moba_remote_monitoring_control_route is not None:
        telemetry_route = gui_design_moba_monitoring_telemetry_route()
        monitoring_controls = {control.key: control for control in gui_design_moba_monitoring_controls()}
        remote_control = monitoring_controls.get(moba_remote_monitoring_control_route.source_control_key)
        if remote_control is None:
            raise RuntimeError("Moba remote-monitoring control route source control missing")
        if moba_remote_monitoring_control_route.source_control_label != remote_control.label:
            raise RuntimeError("Moba remote-monitoring control route label drifted")
        if moba_remote_monitoring_control_route.source_control_type != remote_control.control_type:
            raise RuntimeError("Moba remote-monitoring control route type drifted")
        if moba_remote_monitoring_control_route.expected_checked != remote_control.checked:
            raise RuntimeError("Moba remote-monitoring control route checked state drifted")
        if moba_remote_monitoring_control_route.telemetry_route_key != telemetry_route.key:
            raise RuntimeError("Moba remote-monitoring control route telemetry key drifted")
        if moba_remote_monitoring_control_route.target_metric_cell_keys != telemetry_route.target_metric_cell_keys:
            raise RuntimeError("Moba remote-monitoring control route telemetry cells drifted")
        if moba_remote_monitoring_control_route.signal != "toggled":
            raise RuntimeError("Moba remote-monitoring control route signal drifted")
        if moba_remote_monitoring_control_route.handler != "handle_moba_remote_monitoring_toggled":
            raise RuntimeError("Moba remote-monitoring control route handler drifted")
    if moba_follow_terminal_folder_control_route is not None:
        follow_route = gui_design_moba_sftp_follow_folder_route()
        monitoring_controls = {control.key: control for control in gui_design_moba_monitoring_controls()}
        follow_control = monitoring_controls.get(moba_follow_terminal_folder_control_route.source_control_key)
        if follow_control is None:
            raise RuntimeError("Moba follow-folder control route source control missing")
        if moba_follow_terminal_folder_control_route.source_control_label != follow_control.label:
            raise RuntimeError("Moba follow-folder control route label drifted")
        if moba_follow_terminal_folder_control_route.source_control_type != follow_control.control_type:
            raise RuntimeError("Moba follow-folder control route type drifted")
        if moba_follow_terminal_folder_control_route.expected_checked != follow_control.checked:
            raise RuntimeError("Moba follow-folder control route checked state drifted")
        if moba_follow_terminal_folder_control_route.source_control_object != follow_route.source_control_object:
            raise RuntimeError("Moba follow-folder control route source object drifted")
        if moba_follow_terminal_folder_control_route.target_path_object != follow_route.target_path_object:
            raise RuntimeError("Moba follow-folder control route target path drifted")
        if moba_follow_terminal_folder_control_route.target_table_object != follow_route.target_table_object:
            raise RuntimeError("Moba follow-folder control route target table drifted")
        if moba_follow_terminal_folder_control_route.signal != "toggled":
            raise RuntimeError("Moba follow-folder control route signal drifted")
        if moba_follow_terminal_folder_control_route.handler != "handle_moba_follow_terminal_folder_toggled":
            raise RuntimeError("Moba follow-folder control route handler drifted")
    if securecrt_session_manager_filter_route is not None:
        session_route = gui_design_securecrt_session_manager_route()
        manager_chrome = gui_design_securecrt_session_manager_chrome()
        if securecrt_session_manager_filter_route.session_manager_object != session_route.session_manager_object:
            raise RuntimeError("SecureCRT Session Manager filter route panel object drifted")
        if securecrt_session_manager_filter_route.selected_tree_object != session_route.selected_tree_object:
            raise RuntimeError("SecureCRT Session Manager filter route tree object drifted")
        if securecrt_session_manager_filter_route.selected_tree_label != session_route.selected_tree_label:
            raise RuntimeError("SecureCRT Session Manager filter route selected row drifted")
        if securecrt_session_manager_filter_route.expected_placeholder != manager_chrome.filter_placeholder:
            raise RuntimeError("SecureCRT Session Manager filter route placeholder drifted")
        if not securecrt_session_manager_filter_route.expected_query:
            raise RuntimeError("SecureCRT Session Manager filter route query must be non-empty")
    if securecrt_command_window_send_route is not None:
        if securecrt_command_window_send_route.signal != "clicked":
            raise RuntimeError("SecureCRT command-window send route primary signal drifted")
        if securecrt_command_window_send_route.secondary_signal != "returnPressed":
            raise RuntimeError("SecureCRT command-window send route secondary signal drifted")
        if securecrt_command_window_send_route.handler != "handle_securecrt_command_window_send":
            raise RuntimeError("SecureCRT command-window send route handler drifted")
        if securecrt_command_window_send_route.live_command_property != "secureCrtCommandRouteLiveCommand":
            raise RuntimeError("SecureCRT command-window send route live command property drifted")
        if securecrt_command_window_send_route.live_submitted_property != "secureCrtCommandRouteLiveSubmitted":
            raise RuntimeError("SecureCRT command-window send route live submitted property drifted")
    if securecrt_sftp_tab_route is not None:
        status_strip = gui_design_securecrt_session_status_strip()
        workflow_cards = {card.key: card for card in gui_design_workflow_cards("securecrt")}
        workflow_card = workflow_cards.get(securecrt_sftp_tab_route.workflow_card_key)
        status_fields = {field.key: field for field in status_strip.fields}
        status_field = status_fields.get(securecrt_sftp_tab_route.status_field_key)
        tab_labels = {label for label, _status, _active in gui_design_tab_items("securecrt")}
        tree_labels = {name.strip() for name, _target, _group in gui_design_tree_rows("securecrt")}
        if workflow_card is None:
            raise RuntimeError("SecureCRT SFTP tab route workflow card is missing")
        if status_field is None:
            raise RuntimeError("SecureCRT SFTP tab route status field is missing")
        if workflow_card.title != securecrt_sftp_tab_route.workflow_title:
            raise RuntimeError("SecureCRT SFTP tab route workflow title drifted")
        if workflow_card.primary != securecrt_sftp_tab_route.transfer_state:
            raise RuntimeError("SecureCRT SFTP tab route workflow transfer state drifted")
        if workflow_card.secondary != securecrt_sftp_tab_route.workflow_secondary:
            raise RuntimeError("SecureCRT SFTP tab route workflow secondary copy drifted")
        if status_field.value != securecrt_sftp_tab_route.status_value:
            raise RuntimeError("SecureCRT SFTP tab route status value drifted")
        if securecrt_sftp_tab_route.sftp_tab_label not in tab_labels:
            raise RuntimeError("SecureCRT SFTP tab route tab label is missing")
        if securecrt_sftp_tab_route.selected_tree_label not in tree_labels:
            raise RuntimeError("SecureCRT SFTP tab route tree label is missing")
    if securecrt_sftp_browser_route is not None:
        if securecrt_sftp_tab_route is None:
            raise RuntimeError("SecureCRT SFTP browser route missing SFTP tab route")
        workflow_cards = {card.key: card for card in gui_design_workflow_cards("securecrt")}
        workflow_card = workflow_cards.get(securecrt_sftp_tab_route.workflow_card_key)
        if securecrt_sftp_browser_route.sftp_tab_route_key != securecrt_sftp_tab_route.key:
            raise RuntimeError("SecureCRT SFTP browser route tab key drifted")
        if securecrt_sftp_browser_route.selected_profile_name != securecrt_sftp_tab_route.selected_profile_name:
            raise RuntimeError("SecureCRT SFTP browser route profile drifted")
        if securecrt_sftp_browser_route.selected_tree_label != securecrt_sftp_tab_route.selected_tree_label:
            raise RuntimeError("SecureCRT SFTP browser route tree label drifted")
        if securecrt_sftp_browser_route.sftp_tab_label != securecrt_sftp_tab_route.sftp_tab_label:
            raise RuntimeError("SecureCRT SFTP browser route tab label drifted")
        if workflow_card is None or workflow_card.primary != securecrt_sftp_tab_route.transfer_state:
            raise RuntimeError("SecureCRT SFTP browser route workflow card drifted")
        if securecrt_sftp_browser_route.active_row_name not in {
            row.name for row in securecrt_sftp_browser_route.file_rows
        }:
            raise RuntimeError("SecureCRT SFTP browser route active row missing")
        if not any(row.selected for row in securecrt_sftp_browser_route.file_rows):
            raise RuntimeError("SecureCRT SFTP browser route must expose a selected row")
        if "refresh" not in securecrt_sftp_browser_route.toolbar_actions:
            raise RuntimeError("SecureCRT SFTP browser route missing refresh action")
        if securecrt_sftp_browser_route.action_key != "refresh":
            raise RuntimeError("SecureCRT SFTP browser live action key drifted")
        if securecrt_sftp_browser_route.handler != "handle_securecrt_sftp_browser_action":
            raise RuntimeError("SecureCRT SFTP browser live action handler drifted")
        if securecrt_sftp_browser_route.live_triggered_property != "secureCrtSftpBrowserRouteLiveTriggered":
            raise RuntimeError("SecureCRT SFTP browser live action trigger property drifted")
    if remmina_profile_filter_route is not None:
        profile_route = gui_design_remmina_profile_viewer_route()
        profile_chrome = gui_design_remmina_profile_list_chrome()
        rows_by_key = {row.key: row for row in profile_chrome.rows}
        matched_row = rows_by_key.get(remmina_profile_filter_route.selected_profile_key)
        if matched_row is None:
            raise RuntimeError("Remmina profile-filter route selected row missing")
        if remmina_profile_filter_route.profile_list_object != "remminaProfileListChrome":
            raise RuntimeError("Remmina profile-filter route panel object drifted")
        if remmina_profile_filter_route.filter_object != "remminaProfileFilter":
            raise RuntimeError("Remmina profile-filter route input object drifted")
        if remmina_profile_filter_route.selected_profile_key != profile_route.selected_profile_key:
            raise RuntimeError("Remmina profile-filter route selected profile drifted")
        if remmina_profile_filter_route.expected_placeholder != profile_chrome.filter_placeholder:
            raise RuntimeError("Remmina profile-filter route placeholder drifted")
        if remmina_profile_filter_route.expected_query.lower() not in matched_row.protocol.lower():
            raise RuntimeError("Remmina profile-filter route query no longer matches selected row protocol")
    if remmina_screenshot_route is not None:
        profile_route = gui_design_remmina_profile_viewer_route()
        reference = gui_design_reference_state("remmina")
        surface = gui_design_workspace_surface("remmina")
        controls_by_key = {control.key: control for control in gui_design_remmina_viewer_controls()}
        screenshot_control = controls_by_key.get(remmina_screenshot_route.viewer_control_key)
        if screenshot_control is None:
            raise RuntimeError("Remmina screenshot route target control is missing")
        if screenshot_control.label != "Screenshot":
            raise RuntimeError("Remmina screenshot route control label drifted")
        if remmina_screenshot_route.viewer_controls_object != profile_route.viewer_controls_object:
            raise RuntimeError("Remmina screenshot route viewer controls object drifted")
        if remmina_screenshot_route.viewer_control_object != profile_route.viewer_control_object:
            raise RuntimeError("Remmina screenshot route control object drifted")
        if remmina_screenshot_route.active_tab_label != reference.active_tab_label:
            raise RuntimeError("Remmina screenshot route active tab metadata drifted")
        if remmina_screenshot_route.status_segment not in reference.status_segments:
            raise RuntimeError("Remmina screenshot route status segment metadata drifted")
        if remmina_screenshot_route.detail_line not in surface.detail_lines:
            raise RuntimeError("Remmina screenshot route detail-line metadata drifted")
        if remmina_screenshot_route.activity_line not in surface.activity_lines:
            raise RuntimeError("Remmina screenshot route activity-line metadata drifted")
        if remmina_screenshot_route.signal != "clicked":
            raise RuntimeError("Remmina screenshot route live capture signal drifted")
        if remmina_screenshot_route.handler != "handle_remmina_screenshot_capture":
            raise RuntimeError("Remmina screenshot route live capture handler drifted")
        if remmina_screenshot_route.live_triggered_property != "remminaScreenshotRouteLiveTriggered":
            raise RuntimeError("Remmina screenshot route live capture trigger property drifted")
    if remmina_sftp_transfer_route is not None:
        profile_chrome = gui_design_remmina_profile_list_chrome()
        surface = gui_design_workspace_surface("remmina")
        rows_by_key = {row.key: row for row in profile_chrome.rows}
        profile_row = rows_by_key.get(remmina_sftp_transfer_route.selected_profile_key)
        toolbar_actions = {
            key: label for key, label, _tooltip in gui_design_toolbar_actions("remmina")
        }
        tab_labels = {label for label, _status, _active in gui_design_tab_items("remmina")}
        tree_labels = {name.strip() for name, _target, _group in gui_design_tree_rows("remmina")}
        if profile_row is None:
            raise RuntimeError("Remmina SFTP transfer route selected profile row missing")
        if remmina_sftp_transfer_route.profile_list_object != "remminaProfileListChrome":
            raise RuntimeError("Remmina SFTP transfer route profile-list object drifted")
        if profile_row.name != remmina_sftp_transfer_route.selected_profile_name:
            raise RuntimeError("Remmina SFTP transfer route selected profile name drifted")
        if profile_row.protocol != remmina_sftp_transfer_route.selected_profile_protocol:
            raise RuntimeError("Remmina SFTP transfer route selected profile protocol drifted")
        if profile_row.status != remmina_sftp_transfer_route.selected_profile_status:
            raise RuntimeError("Remmina SFTP transfer route selected profile status drifted")
        if toolbar_actions.get(remmina_sftp_transfer_route.toolbar_action_key) != remmina_sftp_transfer_route.toolbar_action_label:
            raise RuntimeError("Remmina SFTP transfer route toolbar action drifted")
        if remmina_sftp_transfer_route.active_tab_label not in tab_labels:
            raise RuntimeError("Remmina SFTP transfer route tab label is missing")
        if remmina_sftp_transfer_route.selected_tree_label not in tree_labels:
            raise RuntimeError("Remmina SFTP transfer route tree label is missing")
        if remmina_sftp_transfer_route.detail_line not in surface.detail_lines:
            raise RuntimeError("Remmina SFTP transfer route detail-line metadata drifted")
        if remmina_sftp_transfer_route.activity_line not in surface.activity_lines:
            raise RuntimeError("Remmina SFTP transfer route activity-line metadata drifted")
        if remmina_sftp_transfer_route.active_row_name not in {
            row.name for row in remmina_sftp_transfer_route.file_rows
        }:
            raise RuntimeError("Remmina SFTP transfer route active row missing")
        if not any(row.selected for row in remmina_sftp_transfer_route.file_rows):
            raise RuntimeError("Remmina SFTP transfer route must expose a selected row")
    if termius_port_forward_route is not None:
        host_route = gui_design_termius_host_selection_route()
        reference = gui_design_reference_state("termius")
        chips = {chip.key: chip for chip in gui_design_termius_header_chips()}
        fields = {field.key: field for field in gui_design_termius_host_identity_strip().fields}
        chip = chips.get(termius_port_forward_route.header_chip_key)
        field = fields.get(termius_port_forward_route.identity_field_key)
        if chip is None:
            raise RuntimeError("Termius port-forward route header chip is missing")
        if field is None:
            raise RuntimeError("Termius port-forward route identity field is missing")
        if chip.label != termius_port_forward_route.status_segment:
            raise RuntimeError("Termius port-forward route header chip label drifted")
        if field.value != termius_port_forward_route.forward_value:
            raise RuntimeError("Termius port-forward route identity value drifted")
        if termius_port_forward_route.active_tab_label != host_route.active_tab_label:
            raise RuntimeError("Termius port-forward route active tab drifted")
        if termius_port_forward_route.selected_profile_name != reference.profile_name:
            raise RuntimeError("Termius port-forward route selected profile drifted")
        if termius_port_forward_route.status_segment not in reference.status_segments:
            raise RuntimeError("Termius port-forward route status segment drifted")
        if (
            termius_port_forward_route.forward_value
            != f"{termius_port_forward_route.local_port} -> "
            f"{termius_port_forward_route.remote_host}:{termius_port_forward_route.remote_port}"
        ):
            raise RuntimeError("Termius port-forward route endpoint metadata drifted")
    if termius_snippet_route is not None:
        host_route = gui_design_termius_host_selection_route()
        reference = gui_design_reference_state("termius")
        surface = gui_design_workspace_surface("termius")
        workflow_cards = {card.key: card for card in gui_design_workflow_cards("termius")}
        fields = {field.key: field for field in gui_design_termius_host_identity_strip().fields}
        workflow_card = workflow_cards.get(termius_snippet_route.workflow_card_key)
        identity_field = fields.get(termius_snippet_route.identity_field_key)
        if workflow_card is None:
            raise RuntimeError("Termius snippet route workflow card is missing")
        if identity_field is None:
            raise RuntimeError("Termius snippet route identity field is missing")
        if workflow_card.title != termius_snippet_route.workflow_title:
            raise RuntimeError("Termius snippet route workflow title drifted")
        if workflow_card.primary != termius_snippet_route.snippet_command:
            raise RuntimeError("Termius snippet route workflow command drifted")
        if workflow_card.secondary != termius_snippet_route.snippet_state:
            raise RuntimeError("Termius snippet route workflow state drifted")
        if identity_field.value != termius_snippet_route.snippet_command:
            raise RuntimeError("Termius snippet route identity value drifted")
        if termius_snippet_route.active_tab_label != host_route.active_tab_label:
            raise RuntimeError("Termius snippet route active tab drifted")
        if termius_snippet_route.selected_profile_name != reference.profile_name:
            raise RuntimeError("Termius snippet route selected profile drifted")
        if termius_snippet_route.detail_line not in surface.detail_lines:
            raise RuntimeError("Termius snippet route detail-line metadata drifted")
        if termius_snippet_route.action_object != "termiusSnippetRunAction":
            raise RuntimeError("Termius snippet route action object drifted")
        if termius_snippet_route.shortcut_object != "termiusSnippetRunShortcut":
            raise RuntimeError("Termius snippet route shortcut object drifted")
        if termius_snippet_route.action_label != "Run":
            raise RuntimeError("Termius snippet route action label drifted")
        if termius_snippet_route.shortcut_sequence != "Return":
            raise RuntimeError("Termius snippet route shortcut sequence drifted")
        if termius_snippet_route.handler != "handle_termius_snippet_run":
            raise RuntimeError("Termius snippet route handler drifted")
    if termius_files_browser_route is not None:
        host_route = gui_design_termius_host_selection_route()
        fields = {field.key: field for field in gui_design_termius_host_identity_strip().fields}
        identity_field = fields.get(termius_files_browser_route.identity_field_key)
        if termius_files_browser_route.host_selection_route_key != host_route.key:
            raise RuntimeError("Termius files browser route host-selection key drifted")
        if identity_field is None:
            raise RuntimeError("Termius files browser route identity field is missing")
        if identity_field.value != termius_files_browser_route.files_state:
            raise RuntimeError("Termius files browser route identity value drifted")
        if termius_files_browser_route.active_tab_label != host_route.active_tab_label:
            raise RuntimeError("Termius files browser route active tab drifted")
        if termius_files_browser_route.selected_profile_name != host_route.selected_profile_name:
            raise RuntimeError("Termius files browser route selected profile drifted")
        if termius_files_browser_route.selected_tree_label != host_route.selected_tree_label:
            raise RuntimeError("Termius files browser route selected tree label drifted")
        if termius_files_browser_route.active_row_name not in {
            row.name for row in termius_files_browser_route.file_rows
        }:
            raise RuntimeError("Termius files browser route active row missing")
        if not any(row.selected for row in termius_files_browser_route.file_rows):
            raise RuntimeError("Termius files browser route must expose a selected row")
        if "sync" not in termius_files_browser_route.toolbar_actions:
            raise RuntimeError("Termius files browser route missing sync action")
        if termius_files_browser_route.action_key != "sync":
            raise RuntimeError("Termius files browser live sync action key drifted")
        if termius_files_browser_route.handler != "handle_termius_files_sync":
            raise RuntimeError("Termius files browser live sync handler drifted")
        if termius_files_browser_route.live_triggered_property != "termiusFilesRouteLiveTriggered":
            raise RuntimeError("Termius files browser live sync trigger property drifted")
    if mremoteng_document_filter_route is not None:
        connection_route = gui_design_mremoteng_connection_document_route()
        document_chrome = gui_design_mremoteng_document_toolbar_chrome()
        if mremoteng_document_filter_route.document_controls_object != connection_route.document_controls_object:
            raise RuntimeError("mRemoteNG document-filter route controls object drifted")
        if mremoteng_document_filter_route.selected_tree_object != connection_route.selected_tree_object:
            raise RuntimeError("mRemoteNG document-filter route tree object drifted")
        if mremoteng_document_filter_route.selected_tree_label != connection_route.selected_tree_label:
            raise RuntimeError("mRemoteNG document-filter route selected tree row drifted")
        if mremoteng_document_filter_route.expected_placeholder != document_chrome.filter_placeholder:
            raise RuntimeError("mRemoteNG document-filter route placeholder drifted")
        if mremoteng_document_filter_route.expected_query.lower() not in connection_route.selected_tree_label.lower():
            raise RuntimeError("mRemoteNG document-filter route query no longer matches selected tree row")
        if connection_route.signal != "clicked":
            raise RuntimeError("mRemoteNG reconnect live route signal drifted")
        if connection_route.handler != "handle_mremoteng_document_reconnect":
            raise RuntimeError("mRemoteNG reconnect live route handler drifted")
        if connection_route.reconnect_state != "reconnected":
            raise RuntimeError("mRemoteNG reconnect live route state drifted")
    if mremoteng_inheritance_route is not None:
        connection_route = gui_design_mremoteng_connection_document_route()
        property_chrome = gui_design_mremoteng_property_grid_chrome()
        workflow_cards = {card.key: card for card in gui_design_workflow_cards("mremoteng")}
        workflow_card = workflow_cards.get(mremoteng_inheritance_route.workflow_card_key)
        inherited_rows = [row for row in property_chrome.rows if row.key == mremoteng_inheritance_route.property_row_key]
        if workflow_card is None:
            raise RuntimeError("mRemoteNG inheritance route workflow card is missing")
        if len(inherited_rows) != 1:
            raise RuntimeError("mRemoteNG inheritance route property row is missing")
        inherited_row = inherited_rows[0]
        if workflow_card.title != mremoteng_inheritance_route.workflow_title:
            raise RuntimeError("mRemoteNG inheritance route workflow title drifted")
        if workflow_card.primary != mremoteng_inheritance_route.inheritance_state:
            raise RuntimeError("mRemoteNG inheritance route workflow state drifted")
        if workflow_card.secondary != "property grid visible":
            raise RuntimeError("mRemoteNG inheritance route workflow grid visibility copy drifted")
        if inherited_row.property_label != mremoteng_inheritance_route.inherited_property_label:
            raise RuntimeError("mRemoteNG inheritance route property label drifted")
        if inherited_row.effective_value != mremoteng_inheritance_route.inherited_value:
            raise RuntimeError("mRemoteNG inheritance route inherited value drifted")
        if inherited_row.source != mremoteng_inheritance_route.inherited_source:
            raise RuntimeError("mRemoteNG inheritance route inherited source drifted")
        if not inherited_row.inherited:
            raise RuntimeError("mRemoteNG inheritance route row must stay inherited")
        if mremoteng_inheritance_route.active_tab_label != connection_route.active_tab_label:
            raise RuntimeError("mRemoteNG inheritance route active tab drifted")
        if mremoteng_inheritance_route.selected_tree_label != connection_route.selected_tree_label:
            raise RuntimeError("mRemoteNG inheritance route selected tree row drifted")
    if reference_surface_route is not None:
        product_identity_route = gui_design_product_identity_route(preset.id)
        if reference_tab_route is None:
            raise RuntimeError(f"{preset.id} reference surface route missing tab route")
        if reference_surface_route.reference_profile != reference_tab_route.reference_profile:
            raise RuntimeError(f"{preset.id} reference surface route profile metadata drifted")
        if reference_surface_route.active_tab_label != reference_tab_route.active_tab_label:
            raise RuntimeError(f"{preset.id} reference surface route active tab metadata drifted")
        if reference_surface_route.command_target_fragment not in product_identity_route.target_label:
            raise RuntimeError(f"{preset.id} reference surface route target metadata drifted")
    if reference_control_route is not None:
        if reference_surface_route is None:
            raise RuntimeError(f"{preset.id} reference control route missing surface route")
        if reference_control_route.reference_profile != reference_surface_route.reference_profile:
            raise RuntimeError(f"{preset.id} reference control route profile metadata drifted")
        if reference_control_route.active_tab_label != reference_surface_route.active_tab_label:
            raise RuntimeError(f"{preset.id} reference control route active tab metadata drifted")
        required_actions = {"start", "restart", "stop", "copy", "clear"}
        if not required_actions.issubset(reference_control_route.action_keys):
            raise RuntimeError(f"{preset.id} reference control route action metadata drifted")
    if reference_input_route is not None:
        if reference_surface_route is None:
            raise RuntimeError(f"{preset.id} reference input route missing surface route")
        if reference_input_route.reference_profile != reference_surface_route.reference_profile:
            raise RuntimeError(f"{preset.id} reference input route profile metadata drifted")
        if reference_input_route.active_tab_label != reference_surface_route.active_tab_label:
            raise RuntimeError(f"{preset.id} reference input route active tab metadata drifted")
        if reference_input_route.placeholder_text != "stdin, shell command or interactive input":
            raise RuntimeError(f"{preset.id} reference input route placeholder drifted")
    if reference_transcript_route is not None:
        if reference_surface_route is None:
            raise RuntimeError(f"{preset.id} reference transcript route missing surface route")
        if reference_transcript_route.reference_profile != reference_surface_route.reference_profile:
            raise RuntimeError(f"{preset.id} reference transcript route profile metadata drifted")
        if reference_transcript_route.active_tab_label != reference_surface_route.active_tab_label:
            raise RuntimeError(f"{preset.id} reference transcript route active tab metadata drifted")
        if reference_transcript_route.terminal_output_object != reference_surface_route.terminal_output_object:
            raise RuntimeError(f"{preset.id} reference transcript route output object drifted")
        if reference_surface_route.command_target_fragment not in reference_transcript_route.required_fragments:
            raise RuntimeError(f"{preset.id} reference transcript route target fragment drifted")
    return {
        "id": preset.id,
        "label": preset.label,
        "description": preset.description,
        "density": preset.density,
        "profile_width": preset.profile_width,
        "log_height": preset.log_height,
        "tab_position": preset.tab_position,
        "preset_catalog_route": catalog_route.to_dict(),
        "preset_isolation_route": isolation_route.to_dict(),
        "preset_keyboard_shortcut_route": (
            keyboard_shortcut_route.to_dict() if keyboard_shortcut_route is not None else {}
        ),
        "preset_command_surface_route": (
            command_surface_route.to_dict() if command_surface_route is not None else {}
        ),
        "preset_focus_interaction_route": (
            focus_interaction_route.to_dict() if focus_interaction_route is not None else {}
        ),
        "preset_home_search_route": home_search_route.to_dict() if home_search_route is not None else {},
        "preset_reference_control_route": (
            reference_control_route.to_dict() if reference_control_route is not None else {}
        ),
        "preset_reference_input_route": (
            reference_input_route.to_dict() if reference_input_route is not None else {}
        ),
        "preset_reference_status_bar_route": (
            reference_status_route.to_dict() if reference_status_route is not None else {}
        ),
        "preset_reference_session_action_route": (
            reference_session_action_route.to_dict() if reference_session_action_route is not None else {}
        ),
        "moba_connected_session_action_route": (
            moba_connected_action_route.to_dict() if moba_connected_action_route is not None else {}
        ),
        "moba_remote_monitoring_control_route": (
            moba_remote_monitoring_control_route.to_dict()
            if moba_remote_monitoring_control_route is not None
            else {}
        ),
        "moba_follow_terminal_folder_control_route": (
            moba_follow_terminal_folder_control_route.to_dict()
            if moba_follow_terminal_folder_control_route is not None
            else {}
        ),
        "moba_ribbon_edge_action_route": (
            moba_ribbon_edge_action_route.to_dict()
            if moba_ribbon_edge_action_route is not None
            else {}
        ),
        "moba_right_utility_action_route": (
            moba_right_utility_action_route.to_dict()
            if moba_right_utility_action_route is not None
            else {}
        ),
        "moba_session_edge_action_route": (
            moba_session_edge_action_route.to_dict()
            if moba_session_edge_action_route is not None
            else {}
        ),
        "moba_sftp_toolbar_action_route": (
            moba_sftp_toolbar_action_route.to_dict()
            if moba_sftp_toolbar_action_route is not None
            else {}
        ),
        "securecrt_session_manager_filter_route": (
            securecrt_session_manager_filter_route.to_dict()
            if securecrt_session_manager_filter_route is not None
            else {}
        ),
        "securecrt_command_window_send_route": (
            securecrt_command_window_send_route.to_dict()
            if securecrt_command_window_send_route is not None
            else {}
        ),
        "securecrt_sftp_tab_route": (
            securecrt_sftp_tab_route.to_dict()
            if securecrt_sftp_tab_route is not None
            else {}
        ),
        "securecrt_sftp_browser_route": (
            securecrt_sftp_browser_route.to_dict()
            if securecrt_sftp_browser_route is not None
            else {}
        ),
        "remmina_profile_filter_route": (
            remmina_profile_filter_route.to_dict()
            if remmina_profile_filter_route is not None
            else {}
        ),
        "remmina_screenshot_route": (
            remmina_screenshot_route.to_dict()
            if remmina_screenshot_route is not None
            else {}
        ),
        "remmina_sftp_transfer_route": (
            remmina_sftp_transfer_route.to_dict()
            if remmina_sftp_transfer_route is not None
            else {}
        ),
        "mremoteng_connection_document_route": (
            mremoteng_connection_document_route.to_dict()
            if mremoteng_connection_document_route is not None
            else {}
        ),
        "termius_port_forward_route": (
            termius_port_forward_route.to_dict()
            if termius_port_forward_route is not None
            else {}
        ),
        "termius_snippet_route": (
            termius_snippet_route.to_dict()
            if termius_snippet_route is not None
            else {}
        ),
        "termius_files_browser_route": (
            termius_files_browser_route.to_dict()
            if termius_files_browser_route is not None
            else {}
        ),
        "mremoteng_document_filter_route": (
            mremoteng_document_filter_route.to_dict()
            if mremoteng_document_filter_route is not None
            else {}
        ),
        "mremoteng_inheritance_route": (
            mremoteng_inheritance_route.to_dict()
            if mremoteng_inheritance_route is not None
            else {}
        ),
        "preset_reference_transcript_route": (
            reference_transcript_route.to_dict() if reference_transcript_route is not None else {}
        ),
        "preset_reference_surface_route": (
            reference_surface_route.to_dict() if reference_surface_route is not None else {}
        ),
        "preset_reference_tab_chrome_route": (
            reference_tab_chrome_route.to_dict() if reference_tab_chrome_route is not None else {}
        ),
        "preset_reference_tab_route": reference_tab_route.to_dict() if reference_tab_route is not None else {},
        "preset_selection_route": selection_route.to_dict(),
        "preset_transition_route": transition_route.to_dict(),
        "preset_visual_signature": visual_signature.to_dict(),
        "image": image_manifest(artifact),
    }


def state_preview_manifest(artifact: PreviewArtifact) -> dict[str, Any]:
    if artifact.preset is None:
        raise ValueError("state preview preset artifact required")
    return {
        "id": f"{artifact.preset.id}-{artifact.variant_id}",
        "preset_id": artifact.preset.id,
        "variant": artifact.variant_id,
        "label": artifact.variant_label,
        "description": artifact.variant_description,
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
    for state_preview in manifest.get("state_previews", []):
        image = state_preview["image"]
        cards.append(
            f"""
      <article class="card state-card">
        <a href="{html.escape(image['path'])}"><img src="{html.escape(image['path'])}" alt="{html.escape(state_preview['label'])} preview"></a>
        <div class="meta">
          <h2>{html.escape(state_preview['label'])}</h2>
          <p>{html.escape(state_preview['description'])}</p>
          <dl>
            <div><dt>Preset</dt><dd>{html.escape(state_preview['preset_id'])}</dd></div>
            <div><dt>Variant</dt><dd>{html.escape(state_preview['variant'])}</dd></div>
            <div><dt>Width</dt><dd>{image['width']} px</dd></div>
            <div><dt>Height</dt><dd>{image['height']} px</dd></div>
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
            "drwx------ 4 operator operator 4096 Jun 06 12:01 .cache",
            "drwx------ 2 operator operator 4096 Jun 06 12:02 .ssh",
            "drwxr-xr-x 3 operator operator 4096 Jun 06 12:03 workspace",
            "-rw------- 1 operator operator 2048 Feb 12 09:13 .bash_history",
            "-rw-r--r-- 1 operator operator 1024 Feb 12 09:13 .bashrc",
            "-rw-r--r-- 1 operator operator 1024 Jun 06 12:04 .profile",
            "-rw------- 1 operator operator 1024 Jun 06 12:05 .viminfo",
        ]
    )
    return build_moba_connected_session_state(
        profile,
        remote_path="/home/operator",
        terminal_cwd="/home/operator",
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
    connected_route = moba_connected_session_route(state)
    identity_route = moba_connected_session_identity_route(state)
    action_route = moba_connected_session_action_route(state)
    folder_route = moba_sftp_terminal_folder_route(state)
    remote_monitoring_control_route = gui_design_moba_remote_monitoring_control_route()
    follow_terminal_folder_control_route = gui_design_moba_follow_terminal_folder_control_route()
    tab_items = moba_connected_tab_chrome_items(state)
    if connected_route.active_tab_key not in {item.key for item in tab_items if item.active}:
        raise RuntimeError("Moba connected-session route active tab key drifted")
    if connected_route.reference_tab_label not in {item.label for item in tab_items}:
        raise RuntimeError("Moba connected-session route reference tab label drifted")
    if connected_route.target != state.target or connected_route.remote_path != state.remote_path:
        raise RuntimeError("Moba connected-session route state metadata drifted")
    if connected_route.telemetry_identity_cell_key != moba_telemetry_cells(state)[0].key:
        raise RuntimeError("Moba connected-session route telemetry identity metadata drifted")
    if identity_route.reference_tab_label not in {item.label for item in tab_items}:
        raise RuntimeError("Moba connected-session identity route reference tab label drifted")
    if identity_route.banner_target != state.banner.title:
        raise RuntimeError("Moba connected-session identity route banner target drifted")
    if identity_route.web_console_line != state.terminal_transcript[0].text:
        raise RuntimeError("Moba connected-session identity route web console line drifted")
    if identity_route.terminal_prompt != state.terminal_transcript[-1].text:
        raise RuntimeError("Moba connected-session identity route terminal prompt drifted")
    if identity_route.telemetry_target != moba_telemetry_cells(state)[0].display_text:
        raise RuntimeError("Moba connected-session identity route telemetry target drifted")
    if action_route.reference_tab_label not in {item.label for item in tab_items}:
        raise RuntimeError("Moba connected-session action route reference tab label drifted")
    if action_route.expected_action_count != len(action_route.expected_action_keys):
        raise RuntimeError("Moba connected-session action route action count drifted")
    if action_route.menu_object != "mobaConnectedSessionTabContextMenu":
        raise RuntimeError("Moba connected-session action route menu object drifted")
    telemetry_route = gui_design_moba_monitoring_telemetry_route()
    if remote_monitoring_control_route.telemetry_route_key != telemetry_route.key:
        raise RuntimeError("Moba remote-monitoring control route telemetry key drifted")
    if remote_monitoring_control_route.target_metric_cell_keys != telemetry_route.target_metric_cell_keys:
        raise RuntimeError("Moba remote-monitoring control route telemetry cells drifted")
    if remote_monitoring_control_route.signal != "toggled":
        raise RuntimeError("Moba remote-monitoring control route signal drifted")
    if remote_monitoring_control_route.handler != "handle_moba_remote_monitoring_toggled":
        raise RuntimeError("Moba remote-monitoring control route handler drifted")
    if follow_terminal_folder_control_route.source_control_key != gui_design_moba_remote_monitoring_dock_chrome().follow_control_key:
        raise RuntimeError("Moba follow-terminal-folder control route source key drifted")
    if follow_terminal_folder_control_route.expected_checked is not state.follow_terminal_folder:
        raise RuntimeError("Moba follow-terminal-folder control route checked state drifted")
    if follow_terminal_folder_control_route.target_path_object != folder_route.target_path_object:
        raise RuntimeError("Moba follow-terminal-folder control route target path drifted")
    if follow_terminal_folder_control_route.target_plan_property != "mobaSftpFollowRoutePlan":
        raise RuntimeError("Moba follow-terminal-folder control route plan property drifted")
    if follow_terminal_folder_control_route.signal != "toggled":
        raise RuntimeError("Moba follow-terminal-folder control route signal drifted")
    if follow_terminal_folder_control_route.handler != "handle_moba_follow_terminal_folder_toggled":
        raise RuntimeError("Moba follow-terminal-folder control route handler drifted")
    if folder_route.remote_path != state.remote_path:
        raise RuntimeError("Moba SFTP terminal-folder route path drifted")
    if folder_route.list_command != state.follow_folder_plan.printable_batch():
        raise RuntimeError("Moba SFTP terminal-folder route plan drifted")
    if folder_route.follow_enabled is not state.follow_terminal_folder:
        raise RuntimeError("Moba SFTP terminal-folder route enabled state drifted")
    if folder_route.target_path_object != connected_route.sftp_path_object:
        raise RuntimeError("Moba SFTP terminal-folder route target path object drifted")
    image = Image.new("RGB", PREVIEW_SIZE, c.window)
    draw = ImageDraw.Draw(image)

    quick_connect_chrome = gui_design_moba_quick_connect_chrome()
    top_stack = gui_design_moba_top_stack_geometry()
    frame = gui_design_moba_connected_dock_frame()
    title_h = top_stack.titlebar_height
    menu_h = top_stack.menu_height
    ribbon_h = top_stack.ribbon_height
    quick_h = frame.quick_connect_height
    status_h = top_stack.status_height
    side_w = frame.side_width
    rail_w = frame.rail_width
    main_y = frame.quick_connect_y

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
    for item in gui_design_moba_top_menu_items():
        geometry = gui_design_moba_top_menu_geometry_for(item.key)
        draw_text(draw, item.label, geometry.static_x, title_h + geometry.label_y, c.control_text, geometry.label_font_size)

    ribbon_y = top_stack.ribbon_y
    draw.rectangle((0, ribbon_y, PREVIEW_SIZE[0], ribbon_y + ribbon_h), fill=c.toolbar)
    for action in gui_design_moba_ribbon_actions():
        icon_key = action.icon_key
        label = action.label
        color = action.color
        geometry = gui_design_moba_ribbon_action_geometry_for(icon_key)
        if geometry.separator_before:
            draw.line(
                (
                    geometry.separator_x,
                    ribbon_y + geometry.separator_top,
                    geometry.separator_x,
                    ribbon_y + geometry.separator_bottom,
                ),
                fill=c.toolbar_border,
            )
        action_state = toolbar_interaction_state(icon_key, interaction)
        icon_fill, icon_outline, text_color = interaction_button_colors(action_state, c)
        icon_fill = color if action_state == "normal" else icon_fill
        if action_state in {"active", "checked"}:
            draw.rectangle(
                (
                    geometry.active_outline_x,
                    ribbon_y + geometry.active_outline_y,
                    geometry.active_outline_x + geometry.active_outline_width,
                    ribbon_y + geometry.active_outline_y + geometry.active_outline_height,
                ),
                outline=c.control_hover,
            )
        draw_moba_ribbon_icon(
            draw,
            icon_key,
            geometry.icon_x,
            ribbon_y + geometry.icon_y,
            geometry.icon_size,
            icon_fill,
            icon_outline,
            c,
        )
        draw_text(draw, label, geometry.label_x, ribbon_y + geometry.label_y, text_color, geometry.label_font_size)
    for action in gui_design_moba_ribbon_edge_actions():
        geometry = gui_design_moba_ribbon_action_geometry_for(action.key)
        if geometry.separator_before:
            draw.line(
                (
                    geometry.separator_x,
                    ribbon_y + geometry.separator_top,
                    geometry.separator_x,
                    ribbon_y + geometry.separator_bottom,
                ),
                fill=c.toolbar_border,
            )
        draw_moba_ribbon_icon(
            draw,
            action.icon_key,
            geometry.icon_x,
            ribbon_y + geometry.icon_y,
            geometry.icon_size,
            action.color,
            action.color,
            c,
        )
        draw_text(draw, action.label, geometry.label_x, ribbon_y + geometry.label_y, c.control_text, geometry.label_font_size)
    draw.line((0, ribbon_y + ribbon_h - 1, PREVIEW_SIZE[0], ribbon_y + ribbon_h - 1), fill=c.toolbar_border)

    draw_moba_quick_connect_chrome(
        draw,
        quick_connect_chrome,
        c,
        0,
        main_y,
        side_w,
        query=quick_connect_chrome.connected_idle_query,
    )

    if frame.dock_y != top_stack.left_dock_y:
        raise ValueError("Moba connected dock frame y must match the top stack left-dock y")
    tree_y = frame.dock_y
    draw.rectangle((0, tree_y, rail_w, tree_y + frame.dock_height), fill="#101010")
    rail_chrome = gui_design_moba_rail_chrome()
    for item in gui_design_moba_rail_items():
        geometry = gui_design_moba_rail_item_geometry_for(item.role)
        icon_y = tree_y + geometry.static_icon_y
        rail_state = toolbar_interaction_state(item.role, interaction)
        if rail_state == "checked":
            draw.rectangle(
                (
                    rail_chrome.active_x,
                    icon_y + rail_chrome.active_y_offset,
                    rail_chrome.active_x + rail_chrome.active_width,
                    icon_y + rail_chrome.active_y_offset + rail_chrome.active_height,
                ),
                fill=c.sidebar_selected,
                outline=c.control_hover,
            )
        draw_moba_rail_icon(
            draw,
            item.rail_icon_key,
            rail_chrome.icon_x,
            icon_y,
            rail_chrome.static_icon_size,
            item.color,
            c,
        )
        if item.label:
            draw_moba_rail_label(
                image,
                item.label,
                0,
                tree_y + geometry.static_label_y,
                rail_chrome.label_width,
                rail_chrome.label_height,
                c,
                rail_chrome.label_font_size,
            )

    draw_moba_connected_sftp_dock(draw, preset, state, frame.dock_x, frame.dock_y, frame.dock_width, frame.dock_height)
    if quick_connect_chrome.connected_suggestions_visible:
        draw_moba_quick_connect_suggestions(draw, preset, 0, main_y + quick_h, side_w, state)
    redraw_moba_sftp_toolbar_metric_edges(draw, preset, frame.dock_x, frame.dock_y, frame.dock_width)

    tab_y = top_stack.tab_y
    workspace_x = frame.workspace_x
    draw.rectangle((workspace_x, tab_y, PREVIEW_SIZE[0], tab_y + top_stack.tab_height), fill=c.tab, outline=c.toolbar_border)
    tx = workspace_x + 10
    for item in moba_connected_tab_chrome_items(state):
        draw_moba_connected_tab(draw, item, tx, tab_y + 3, c)
        geometry = moba_connected_tab_chrome_geometry_for(item.key)
        tx += geometry.width + geometry.gap_after

    content_y = top_stack.terminal_content_y
    draw.rectangle((workspace_x, content_y, PREVIEW_SIZE[0], PREVIEW_SIZE[1] - status_h), fill=c.pane)
    right_rail = gui_design_moba_right_utility_rail_chrome()
    draw_moba_right_utility_rail(
        draw,
        PREVIEW_SIZE[0] - right_rail.static_width,
        content_y,
        right_rail.static_width,
        PREVIEW_SIZE[1] - status_h - content_y,
        c,
    )
    draw_moba_session_edge_controls(draw, PREVIEW_SIZE[0] - right_rail.static_width, c)

    content_bottom = PREVIEW_SIZE[1] - status_h - 24
    term_x = workspace_x
    banner_chrome = gui_design_moba_ssh_banner_chrome()
    banner_x = term_x + banner_chrome.static_left_offset
    banner_y = content_y + banner_chrome.static_top_offset
    draw_moba_ssh_banner_card(draw, preset, state, banner_x, banner_y)
    term_y = banner_y + banner_chrome.static_height + banner_chrome.terminal_gap
    for line in state.terminal_transcript:
        geometry = gui_design_moba_terminal_transcript_row_geometry_for(line.key)
        color = "#7dd3fc" if line.tone == "info" else c.terminal_text
        draw_text(
            draw,
            line.text,
            term_x + geometry.static_x,
            term_y + geometry.static_y,
            color,
            geometry.font_size,
            mono=True,
        )
    draw.rectangle((term_x, content_bottom, PREVIEW_SIZE[0], PREVIEW_SIZE[1] - status_h), fill=c.toolbar, outline=c.toolbar_border)
    telemetry_geometry = moba_telemetry_cell_geometry()
    for cell in moba_telemetry_cells(state):
        geometry = moba_telemetry_cell_geometry_for(cell.key)
        cell_x = term_x + geometry.static_x
        cell_y = content_bottom + geometry.static_y
        cell_right = cell_x + geometry.width
        draw.rectangle((cell_x, cell_y, cell_right, cell_y + geometry.height), fill=c.toolbar)
        draw.line(
            (
                cell_x,
                content_bottom + geometry.separator_top,
                cell_x,
                content_bottom + geometry.separator_bottom,
            ),
            fill=c.toolbar_border,
        )
        draw_moba_telemetry_icon(
            draw,
            cell.icon_key,
            cell_x + geometry.icon_x,
            content_bottom + geometry.icon_y,
            geometry.icon_size,
            c,
            accent=cell.icon_accent,
        )
        draw_text(
            draw,
            cell.display_text,
            cell_x + geometry.label_x,
            content_bottom + geometry.label_y,
            c.control_text,
            geometry.label_font_size,
        )
    last_geometry = telemetry_geometry[-1]
    telemetry_right = term_x + last_geometry.static_x + last_geometry.width
    draw.line(
        (
            telemetry_right,
            content_bottom + last_geometry.separator_top,
            telemetry_right,
            content_bottom + last_geometry.separator_bottom,
        ),
        fill=c.toolbar_border,
    )

    draw_status_bar(draw, preset, 0, PREVIEW_SIZE[1] - status_h, PREVIEW_SIZE[0], status_h)
    return image


def render_mobaxterm_home_preset(preset: GuiDesignPreset):
    from PIL import Image, ImageDraw

    c = preset.colors
    interaction = gui_design_interaction_state(preset.id)
    image = Image.new("RGB", PREVIEW_SIZE, c.window)
    draw = ImageDraw.Draw(image)

    title_h = 22
    menu_h = 22
    ribbon_h = 64
    quick_connect_chrome = gui_design_moba_quick_connect_chrome()
    quick_h = quick_connect_chrome.static_height
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
    draw_text(draw, "Remote Ops Workspace - MobaXterm-style Home", titlebar_chrome.title_left, 5, c.control_text, 12, bold=True)
    control_x = PREVIEW_SIZE[0] - titlebar_chrome.control_right_inset - (
        titlebar_chrome.control_width * len(titlebar_chrome.control_keys)
    )
    for key in titlebar_chrome.control_keys:
        draw_moba_titlebar_control(draw, key, control_x, 0, titlebar_chrome.control_width, title_h, c)
        control_x += titlebar_chrome.control_width
    draw.line((0, title_h - 1, PREVIEW_SIZE[0], title_h - 1), fill=c.toolbar_border)

    draw.rectangle((0, title_h, PREVIEW_SIZE[0], title_h + menu_h), fill="#141414")
    for item in gui_design_moba_top_menu_items():
        geometry = gui_design_moba_top_menu_geometry_for(item.key)
        draw_text(draw, item.label, geometry.static_x, title_h + geometry.label_y, c.control_text, geometry.label_font_size)

    ribbon_y = title_h + menu_h
    draw.rectangle((0, ribbon_y, PREVIEW_SIZE[0], ribbon_y + ribbon_h), fill=c.toolbar)
    for action in gui_design_moba_ribbon_actions():
        geometry = gui_design_moba_ribbon_action_geometry_for(action.icon_key)
        if geometry.separator_before:
            draw.line(
                (
                    geometry.separator_x,
                    ribbon_y + geometry.separator_top,
                    geometry.separator_x,
                    ribbon_y + geometry.separator_bottom,
                ),
                fill=c.toolbar_border,
            )
        action_state = toolbar_interaction_state(action.icon_key, interaction)
        icon_fill, icon_outline, text_color = interaction_button_colors(action_state, c)
        icon_fill = action.color if action_state == "normal" else icon_fill
        if action_state in {"active", "checked"}:
            draw.rectangle(
                (
                    geometry.active_outline_x,
                    ribbon_y + geometry.active_outline_y,
                    geometry.active_outline_x + geometry.active_outline_width,
                    ribbon_y + geometry.active_outline_y + geometry.active_outline_height,
                ),
                outline=c.control_hover,
            )
        draw_moba_ribbon_icon(
            draw,
            action.icon_key,
            geometry.icon_x,
            ribbon_y + geometry.icon_y,
            geometry.icon_size,
            icon_fill,
            icon_outline,
            c,
        )
        draw_text(draw, action.label, geometry.label_x, ribbon_y + geometry.label_y, text_color, geometry.label_font_size)
    for action in gui_design_moba_ribbon_edge_actions():
        geometry = gui_design_moba_ribbon_action_geometry_for(action.key)
        if geometry.separator_before:
            draw.line(
                (
                    geometry.separator_x,
                    ribbon_y + geometry.separator_top,
                    geometry.separator_x,
                    ribbon_y + geometry.separator_bottom,
                ),
                fill=c.toolbar_border,
            )
        draw_moba_ribbon_icon(
            draw,
            action.icon_key,
            geometry.icon_x,
            ribbon_y + geometry.icon_y,
            geometry.icon_size,
            action.color,
            action.color,
            c,
        )
        draw_text(draw, action.label, geometry.label_x, ribbon_y + geometry.label_y, c.control_text, geometry.label_font_size)
    draw.line((0, ribbon_y + ribbon_h - 1, PREVIEW_SIZE[0], ribbon_y + ribbon_h - 1), fill=c.toolbar_border)

    draw_moba_quick_connect_chrome(draw, quick_connect_chrome, c, 0, main_y, side_w, query="")
    tree_y = main_y + quick_h
    draw_moba_home_rail(draw, image, preset, 0, tree_y, rail_w, main_h - quick_h)
    draw_moba_home_session_tree(draw, preset, rail_w, tree_y, side_w - rail_w, main_h - quick_h)

    workspace_x = side_w
    tab_y = main_y
    draw_moba_home_tab_bar(draw, preset, workspace_x, tab_y, PREVIEW_SIZE[0] - workspace_x, 28)
    content_y = tab_y + 28
    draw.rectangle((workspace_x, content_y, PREVIEW_SIZE[0], PREVIEW_SIZE[1] - status_h), fill=c.pane)
    right_rail = gui_design_moba_right_utility_rail_chrome()
    draw_moba_right_utility_rail(
        draw,
        PREVIEW_SIZE[0] - right_rail.static_width,
        content_y,
        right_rail.static_width,
        PREVIEW_SIZE[1] - status_h - content_y,
        c,
    )
    draw_moba_session_edge_controls(draw, PREVIEW_SIZE[0] - right_rail.static_width, c)
    draw_moba_home_welcome_surface(draw, preset, workspace_x, content_y, PREVIEW_SIZE[0] - workspace_x - 30, PREVIEW_SIZE[1] - status_h - content_y)

    draw_status_bar(draw, preset, 0, PREVIEW_SIZE[1] - status_h, PREVIEW_SIZE[0], status_h)
    return image


def draw_moba_home_rail(draw: Any, image: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    interaction = gui_design_interaction_state(preset.id)
    draw.rectangle((x, y, x + w, y + h), fill="#101010")
    rail_chrome = gui_design_moba_rail_chrome()
    for item in gui_design_moba_rail_items():
        geometry = gui_design_moba_rail_item_geometry_for(item.role)
        icon_y = y + geometry.static_icon_y
        rail_state = toolbar_interaction_state(item.role, interaction)
        if rail_state == "checked":
            draw.rectangle(
                (
                    x + rail_chrome.active_x,
                    icon_y + rail_chrome.active_y_offset,
                    x + rail_chrome.active_x + rail_chrome.active_width,
                    icon_y + rail_chrome.active_y_offset + rail_chrome.active_height,
                ),
                fill=c.sidebar_selected,
                outline=c.control_hover,
            )
        draw_moba_rail_icon(
            draw,
            item.rail_icon_key,
            x + rail_chrome.icon_x,
            icon_y,
            rail_chrome.static_icon_size,
            item.color,
            c,
        )
        if item.label:
            draw_moba_rail_label(
                image,
                item.label,
                x,
                y + geometry.static_label_y,
                rail_chrome.label_width,
                rail_chrome.label_height,
                c,
                rail_chrome.label_font_size,
            )


def draw_moba_home_session_tree(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    interaction = gui_design_interaction_state(preset.id)
    chrome = gui_design_moba_session_tree_chrome()
    draw.rectangle((x, y, x + w, y + h), fill=c.sidebar)
    draw.line((x + w, y, x + w, y + h), fill=c.toolbar_border)
    draw.rectangle((x, y, x + w, y + chrome.header_height), fill="#151515")
    draw_sidebar_row_icon(
        draw,
        preset,
        "folder",
        x + chrome.header_icon_x,
        y + chrome.header_icon_y,
        chrome.header_icon_size,
        selected=False,
        group=True,
    )
    draw_text(
        draw,
        "User sessions",
        x + chrome.header_text_x,
        y + chrome.header_text_y,
        c.control_text,
        chrome.header_font_size,
        bold=True,
    )
    row_y = y + chrome.row_start_y
    for name, target, group in gui_design_tree_rows("mobaxterm"):
        label = name.strip()
        selected = bool(label and label == interaction.selected_tree_label)
        if group:
            draw_text(draw, "v", x + chrome.group_arrow_x, row_y + chrome.group_arrow_y_offset, c.control_text, 9, bold=True)
            draw_sidebar_row_icon(
                draw,
                preset,
                "folder",
                x + chrome.group_icon_x,
                row_y + chrome.group_icon_y_offset,
                15,
                selected=False,
                group=True,
            )
            draw_text(
                draw,
                label,
                x + chrome.group_label_x,
                row_y + chrome.group_label_y_offset,
                c.status,
                chrome.group_font_size,
                bold=True,
            )
            row_y += chrome.group_row_height
            continue
        if selected:
            draw.rectangle(
                (
                    x + chrome.selected_left,
                    row_y + chrome.selected_top_offset,
                    x + w - chrome.selected_right_inset,
                    row_y + chrome.selected_top_offset + chrome.selected_height,
                ),
                fill=c.sidebar_selected,
            )
        icon_key = sidebar_row_icon_key("mobaxterm", name, target, group)
        draw_sidebar_row_icon(
            draw,
            preset,
            icon_key,
            x + chrome.profile_icon_x,
            row_y + chrome.profile_icon_y_offset,
            14,
            selected=selected,
            group=False,
        )
        text = c.sidebar_selected_text if selected else c.sidebar_text
        muted = c.sidebar_selected_text if selected else c.sidebar_muted
        draw_text(draw, label, x + chrome.profile_label_x, row_y + chrome.profile_label_y_offset, text, chrome.profile_label_font_size)
        draw_text(draw, target, x + chrome.profile_target_x, row_y + chrome.profile_target_y_offset, muted, chrome.profile_target_font_size)
        row_y += chrome.profile_row_height


def draw_moba_home_tab_bar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.tab, outline=c.toolbar_border)
    rounded(draw, (x + 10, y + 3, x + 48, y + 25), c.tab_selected, c.toolbar_border, 2)
    draw_moba_tab_icon(draw, "home", x + 22, y + 8, 12, c)
    rounded(draw, (x + 54, y + 3, x + 92, y + 25), c.tab, c.toolbar_border, 2)
    draw_text(draw, "+", x + 67, y + 6, c.tab_text, 12, bold=True)


def draw_moba_home_welcome_surface(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_moba_home_welcome_chrome()
    geometry = gui_design_moba_home_welcome_geometry()
    surface = gui_design_workspace_surface("mobaxterm")
    center_w = min(chrome.surface_width, w - geometry.center_side_margin)
    center_x = x + max(0, (w - center_w) // 2)
    hero_y = y + max(geometry.hero_min_y, (h - geometry.hero_height) // 2)

    logo_x = center_x + max(0, (center_w - geometry.logo_cluster_width) // 2)
    draw.rectangle(
        (logo_x, hero_y, logo_x + geometry.logo_size, hero_y + geometry.logo_size),
        fill=c.terminal,
        outline=c.control_text,
        width=2,
    )
    draw_moba_ribbon_icon(
        draw,
        chrome.icon_key,
        logo_x + geometry.logo_inner_padding,
        hero_y + geometry.logo_inner_padding,
        geometry.logo_icon_size,
        c.primary,
        c.control_border,
        c,
    )
    draw_text(
        draw,
        chrome.title,
        logo_x + geometry.logo_size + geometry.title_gap,
        hero_y + geometry.title_y_offset,
        c.control_text,
        geometry.title_font_size,
    )
    draw_centered_text(
        draw,
        chrome.subtitle,
        center_x,
        hero_y + geometry.subtitle_y_offset,
        center_w,
        c.sidebar_muted,
        geometry.subtitle_font_size,
    )

    button_y = hero_y + geometry.button_y_offset
    button_x = center_x + max(
        0,
        (center_w - geometry.primary_width - geometry.secondary_width - geometry.action_gap) // 2,
    )
    draw_moba_home_action_button(
        draw,
        chrome.primary_action_icon_key,
        surface.home_actions[0],
        button_x,
        button_y,
        geometry.primary_width,
        c,
        geometry,
        primary=True,
    )
    draw_moba_home_action_button(
        draw,
        chrome.secondary_action_icon_key,
        surface.home_actions[1],
        button_x + geometry.primary_width + geometry.action_gap,
        button_y,
        geometry.secondary_width,
        c,
        geometry,
        primary=False,
    )

    search_x = center_x + max(0, (center_w - chrome.search_width) // 2)
    search_y = button_y + geometry.search_y_gap
    draw.rectangle(
        (search_x, search_y, search_x + chrome.search_width, search_y + geometry.search_height),
        fill=c.control,
        outline=c.control_border,
    )
    draw_text(
        draw,
        surface.home_search_placeholder,
        search_x + geometry.search_text_x,
        search_y + geometry.search_text_y,
        c.sidebar_muted,
        geometry.search_font_size,
    )

    recent_y = search_y + geometry.recent_y_gap
    draw_centered_text(
        draw,
        chrome.recent_title,
        center_x,
        recent_y,
        center_w,
        c.control_text,
        geometry.recent_title_font_size,
        bold=True,
    )
    col_w = center_w // len(surface.recent_columns)
    for col_index, column in enumerate(surface.recent_columns):
        col_x = center_x + col_index * col_w + geometry.recent_column_padding
        item_y = recent_y + geometry.recent_item_y_offset
        for item in column:
            draw_moba_home_recent_item(draw, preset, item, col_x, item_y)
            item_y += geometry.recent_item_step

    draw_centered_text(
        draw,
        surface.footer,
        center_x,
        recent_y + geometry.footer_y_offset,
        center_w,
        c.control_text,
        geometry.footer_font_size,
    )


def draw_moba_home_action_button(
    draw: Any,
    icon_key: str,
    label: str,
    x: int,
    y: int,
    w: int,
    c: Any,
    geometry: Any,
    *,
    primary: bool,
) -> None:
    fill = c.primary if primary else c.control
    outline = c.control_hover if primary else c.control_border
    text = c.primary_text if primary else c.control_text
    draw.rectangle((x, y, x + w, y + geometry.button_height), fill=fill, outline=outline)
    draw_moba_ribbon_icon(
        draw,
        icon_key,
        x + geometry.button_icon_x,
        y + geometry.button_icon_y,
        geometry.button_icon_size,
        "#55cc7a" if primary else "#202020",
        outline,
        c,
    )
    draw_text(draw, label, x + geometry.button_label_x, y + geometry.button_label_y, text, geometry.button_font_size)


def draw_moba_home_recent_item(draw: Any, preset: GuiDesignPreset, label: str, x: int, y: int) -> None:
    c = preset.colors
    if label == "...":
        draw.rectangle((x, y + 4, x + 12, y + 16), outline=c.toolbar_border)
        draw_text(draw, label, x + 20, y + 3, c.control_text, 10, bold=True)
        return
    icon_key = sidebar_row_icon_key("mobaxterm", label, label, False)
    draw_sidebar_row_icon(draw, preset, icon_key, x, y + 2, 13, selected=False, group=False)
    draw_text(draw, label, x + 20, y + 3, c.control_text, 10)


def draw_moba_ssh_banner_card(
    draw: Any,
    preset: Any,
    state: MobaConnectedSessionState,
    x: int,
    y: int,
) -> None:
    c = preset.colors
    chrome = gui_design_moba_ssh_banner_chrome()
    draw.rectangle(
        (x, y, x + chrome.static_width, y + chrome.static_height),
        fill=c.terminal,
        outline=c.terminal_accent,
    )
    title_geometry = gui_design_moba_ssh_banner_row_geometry_for("title")
    draw_centered_text(
        draw,
        f"{chrome.heading_prefix}{chrome.title}{chrome.heading_suffix}",
        x + title_geometry.static_x,
        y + title_geometry.static_y,
        title_geometry.static_width,
        c.status,
        12,
        mono=True,
        bold=True,
    )
    subtitle_geometry = gui_design_moba_ssh_banner_row_geometry_for("subtitle")
    draw_centered_text(
        draw,
        chrome.subtitle,
        x + subtitle_geometry.static_x,
        y + subtitle_geometry.static_y,
        subtitle_geometry.static_width,
        c.status,
        12,
        mono=True,
    )
    target_geometry = gui_design_moba_ssh_banner_row_geometry_for("target")
    draw_text(
        draw,
        f"> {chrome.target_intro} {state.banner.title}",
        x + target_geometry.static_x,
        y + target_geometry.static_y,
        c.control_text,
        12,
        mono=True,
    )
    for row in state.banner.capability_rows():
        row_geometry = gui_design_moba_ssh_banner_row_geometry_for(row.key)
        value_color = c.control_text if row.status == "ok" else c.status
        draw_text(
            draw,
            f"  * {row.line(label_width=chrome.capability_label_width)}",
            x + row_geometry.static_x,
            y + row_geometry.static_y,
            value_color,
            12,
            mono=True,
        )
    help_link, website_link = state.banner.footer_links()
    footer_geometry = gui_design_moba_ssh_banner_row_geometry_for("footer")
    footer = f"> {chrome.footer_prefix} {help_link} or visit our {website_link}."
    draw_text(
        draw,
        footer,
        x + footer_geometry.static_x,
        y + footer_geometry.static_y,
        c.control_text,
        12,
        mono=True,
    )


def draw_moba_quick_connect_chrome(draw: Any, chrome: Any, c: Any, x: int, y: int, w: int, *, query: str = "") -> None:
    interaction = gui_design_interaction_state("mobaxterm")
    h = chrome.static_height
    draw.rectangle((x, y, x + w, y + h), fill=c.control, outline=c.toolbar_border)
    if interaction.focused_control == "quick-connect":
        draw.rectangle((x + 2, y + 2, x + w - 2, y + h - 2), outline=c.control_hover, width=2)
    input_right = x + w - chrome.marker_width
    draw_text(
        draw,
        query or chrome.placeholder,
        x + chrome.input_left + 8,
        y + 5,
        c.control_text if query else c.sidebar_muted,
        12,
    )
    draw.line((input_right, y + 3, input_right, y + h - 3), fill=c.toolbar_border)
    draw_text(draw, chrome.dropdown_marker, input_right + 8, y + 6, c.sidebar_muted, 10, bold=True)


def draw_moba_quick_connect_suggestions(
    draw: Any,
    preset: GuiDesignPreset,
    x: int,
    y: int,
    w: int,
    state: MobaConnectedSessionState,
) -> None:
    c = preset.colors
    chrome = gui_design_moba_quick_connect_suggestion_chrome()
    profiles = [
        Profile(
            name="edge-prod",
            protocol="ssh",
            host=state.target.split(":", maxsplit=1)[0],
            port=22,
            username="operator",
            group="prod",
            tags=["ssh", "demo"],
        ),
        Profile(
            name="files-prod",
            protocol="sftp",
            host="files.example.invalid",
            port=22,
            username="operator",
            group="files",
            tags=["sftp"],
        ),
    ]
    candidates = quick_connect_candidates(chrome.preview_query, profiles, limit=chrome.max_visible_rows)
    if not candidates:
        return
    height = min(chrome.max_visible_rows, len(candidates)) * chrome.row_height + 8
    draw.rectangle((x, y, x + w, y + height), fill=c.sidebar, outline=c.toolbar_border)
    for index, candidate in enumerate(candidates[: chrome.max_visible_rows]):
        row_y = y + 4 + index * chrome.row_height
        if index == 0:
            draw.rectangle((x + 4, row_y, x + w - 4, row_y + chrome.row_height - 2), fill=c.sidebar_selected)
            text_color = c.sidebar_selected_text
            detail_color = c.sidebar_selected_text
        else:
            text_color = c.sidebar_text
            detail_color = c.sidebar_muted
        icon_key = "session" if candidate.kind == "profile" else "terminal-key"
        draw_moba_tab_icon(draw, icon_key, x + 8, row_y + 4, 12, c)
        draw_text(draw, candidate.label, x + 26, row_y + 5, text_color, 9, bold=index == 0)
        draw_text(draw, candidate.detail, x + 196, row_y + 5, detail_color, 9)


def redraw_moba_sftp_toolbar_metric_edges(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int) -> None:
    c = preset.colors
    density = gui_design_moba_sftp_dock_layout()
    toolbar_y = y + density.inner_margin
    dock_left = x + density.inner_margin
    dock_right = x + w - density.inner_margin
    draw.line(
        (dock_left, toolbar_y + density.toolbar_height, dock_right, toolbar_y + density.toolbar_height),
        fill=c.toolbar_border,
    )
    for geometry in gui_design_moba_sftp_toolbar_action_geometry():
        if not geometry.separator_after:
            continue
        separator_x = dock_left + geometry.separator_x
        draw.line(
            (separator_x, toolbar_y + 5, separator_x, toolbar_y + density.toolbar_height - 5),
            fill=c.toolbar_border,
        )


def draw_moba_telemetry_icon(
    draw: Any,
    icon_key: str,
    x: int,
    y: int,
    size: int,
    c: Any,
    *,
    accent: str,
) -> None:
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
    for action in gui_design_moba_right_utility_actions():
        draw_moba_right_utility_icon(
            draw,
            action.icon_key,
            x + action.static_x,
            y + action.static_y,
            action.static_size,
            action.color,
            c,
        )


def draw_moba_session_edge_controls(draw: Any, x: int, c: Any) -> None:
    rail = gui_design_moba_right_utility_rail_chrome()
    for action in gui_design_moba_session_edge_actions():
        control_y = rail.session_edge_top_y + action.relative_y(rail.session_edge_top_y)
        draw_moba_right_utility_icon(
            draw,
            action.icon_key,
            x + rail.session_edge_icon_x,
            control_y,
            action.static_size,
            action.color,
            c,
        )


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
    geometry = moba_connected_tab_chrome_geometry_for(item.key)
    fill = c.tab_selected if item.active else c.tab
    text = c.tab_selected_text if item.active else c.tab_text
    rounded(draw, (x, y, x + geometry.width, y + geometry.height), fill, c.toolbar_border, geometry.corner_radius)
    icon_x = x + geometry.icon_x
    if item.key == "new-session":
        draw_text(draw, "+", x + geometry.plus_x, y + geometry.plus_y, text, 13, bold=True)
        return
    draw_moba_tab_icon(draw, item.icon_key, icon_x, y + geometry.icon_y, geometry.icon_size, c)
    if item.label:
        draw_text(draw, item.label, x + geometry.label_x, y + geometry.label_y, text, 8, bold=item.active)
    if item.closeable:
        draw_text(draw, "x", x + geometry.width - geometry.close_right_offset, y + geometry.close_y, c.sidebar_muted, 9, bold=True)


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


def draw_moba_rail_label(image: Any, text: str, x: int, y: int, w: int, h: int, c: Any, font_size: int) -> None:
    from PIL import Image, ImageDraw

    label = Image.new("RGBA", (h, w), (0, 0, 0, 0))
    label_draw = ImageDraw.Draw(label)
    label_font = font(font_size, bold=True)
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
    for action in gui_design_moba_sftp_dock_actions():
        geometry = gui_design_moba_sftp_toolbar_action_geometry_for(action.key)
        draw_moba_sftp_toolbar_icon(
            draw,
            action.icon_key,
            dock_left + geometry.icon_x,
            toolbar_y + geometry.icon_y,
            geometry.icon_size,
            action.color,
            c,
        )
        if geometry.separator_after:
            separator_x = dock_left + geometry.separator_x
            draw.line(
                (separator_x, toolbar_y + 5, separator_x, toolbar_y + density.toolbar_height - 5),
                fill=c.toolbar_border,
            )

    chrome = gui_design_moba_sftp_browser_chrome()
    follow_route = gui_design_moba_sftp_follow_folder_route()
    routed_rows = gui_design_moba_sftp_routed_file_rows()
    if routed_rows.follow_route_key != follow_route.key:
        raise ValueError("MobaXterm routed SFTP rows must target the follow-folder route")
    if routed_rows.target_table_object != follow_route.target_table_object:
        raise ValueError("MobaXterm routed SFTP rows must target the follow-folder file table")
    if routed_rows.parent_row_name != chrome.parent_row_label:
        raise ValueError("MobaXterm routed SFTP rows must share the parent-row label")
    if routed_rows.selected_row_kind != chrome.selected_row_kind:
        raise ValueError("MobaXterm routed SFTP rows must share selected parent-row metadata")
    if state.follow_terminal_folder and not state.remote_path.startswith("/"):
        raise ValueError("MobaXterm follow-folder SFTP rows require an absolute remote path")
    path_source_key = follow_route.source_control_key if state.follow_terminal_folder else "profile-path"
    path_outline = c.toolbar_border if follow_route.target_path_object == "mobaSftpPath" else c.danger
    path_text = state.remote_path if path_source_key == follow_route.source_control_key else state.remote_path
    path_y = toolbar_y + density.toolbar_height + density.path_gap
    draw.rectangle((dock_left, path_y, dock_right, path_y + density.path_height), fill=c.control, outline=path_outline)
    draw_text(
        draw,
        path_text or chrome.path_placeholder,
        x + chrome.path_text_x,
        path_y + chrome.path_text_y,
        c.control_text,
        chrome.path_font_size,
        mono=True,
    )
    draw_text(
        draw,
        chrome.dropdown_marker,
        x + w - chrome.dropdown_right_offset,
        path_y + chrome.dropdown_y,
        c.sidebar_muted,
        chrome.dropdown_font_size,
        bold=True,
    )

    header_y = path_y + density.path_height + density.table_header_gap
    draw.rectangle(
        (dock_left, header_y, dock_right, header_y + density.table_header_height),
        fill="#2b2b2b",
        outline=c.toolbar_border,
    )
    for column in chrome.columns:
        draw_text(
            draw,
            column.label,
            x + column.static_x,
            header_y + chrome.header_label_y,
            c.control_text,
            chrome.header_font_size,
            bold=True,
        )
    file_rows = [
        (chrome.parent_row_kind, chrome.parent_row_label, "", ""),
        *[(entry.kind, entry.name, str(entry.size_kb), entry.modified) for entry in state.file_entries],
    ]
    row_y = header_y + density.table_header_height + density.file_row_gap
    column_separator_x: list[int] = []
    separator_x = dock_left
    for column in chrome.columns[:-1]:
        separator_x += column.static_width
        column_separator_x.append(separator_x)
    for row_index, (kind, name, size, modified) in enumerate(file_rows[: density.static_max_rows]):
        row_top = row_y + chrome.row_top_offset
        row_bottom = row_top + density.file_row_height
        selected = kind == chrome.selected_row_kind
        row_fill = "#1f2f3f" if selected else "#171717" if row_index % 2 else c.sidebar
        draw.rectangle((dock_left + 1, row_top, dock_right - 1, row_bottom), fill=row_fill)
        if selected:
            draw.rectangle((dock_left + 1, row_top, dock_right - 1, row_bottom), outline="#477ab0")
        else:
            draw.line((dock_left + 1, row_bottom, dock_right - 1, row_bottom), fill="#252525")
        for separator_x in column_separator_x:
            draw.line((separator_x, row_top, separator_x, row_bottom), fill="#262626")
        row_icon = gui_design_moba_sftp_file_row_icon(kind)
        draw_moba_sftp_file_icon(
            draw,
            row_icon.icon_key,
            x + chrome.row_icon_x,
            row_y + chrome.row_icon_y_offset,
            row_icon.static_size,
            c,
        )
        row_text_y = row_y + chrome.row_text_y_offset
        draw_text(draw, name, x + chrome.row_name_x, row_text_y, c.control_text, chrome.row_text_font_size)
        draw_text(draw, size, x + chrome.row_size_x, row_text_y, c.control_text, chrome.row_text_font_size)
        draw_text(draw, modified, x + chrome.row_modified_x, row_text_y, c.sidebar_muted, chrome.row_modified_font_size)
        row_y += density.file_row_height

    chrome = gui_design_moba_remote_monitoring_dock_chrome()
    telemetry_route = gui_design_moba_monitoring_telemetry_route()
    monitor_y = y + h - chrome.static_height
    controls = list(gui_design_moba_monitoring_controls())
    draw.line(
        (
            x + chrome.divider_left_inset,
            monitor_y - chrome.divider_offset,
            x + w - chrome.divider_right_inset,
            monitor_y - chrome.divider_offset,
        ),
        fill=c.sidebar_muted,
    )
    visible_metric_keys = (
        telemetry_route.visible_dock_metric_keys if telemetry_route.telemetry_surface == "left-dock" else ()
    )
    remote_control = controls[0]
    follow_control = controls[1]
    draw_moba_monitoring_control(
        draw,
        remote_control,
        x,
        monitor_y,
        c,
        checked=remote_control.checked,
        geometry=gui_design_moba_monitoring_control_geometry_for(remote_control.key),
    )
    metrics = [moba_monitoring_metric_text(state, metric) for metric in gui_design_moba_monitoring_metrics()]
    visible_metrics = [
        text
        for text, metric in zip(metrics, gui_design_moba_monitoring_metrics(), strict=True)
        if metric.key in visible_metric_keys
    ]
    if visible_metrics:
        draw_text(draw, "   ".join(visible_metrics[:2]), x + chrome.content_left, monitor_y + 28, c.sidebar_text, 10)
        draw_text(
            draw,
            "   ".join(visible_metrics[2:4]),
            x + chrome.content_left,
            monitor_y + 28 + chrome.metric_row_gap,
            c.sidebar_text,
            10,
        )
    draw_moba_monitoring_control(
        draw,
        follow_control,
        x,
        monitor_y,
        c,
        checked=state.follow_terminal_folder,
        geometry=gui_design_moba_monitoring_control_geometry_for(follow_control.key),
    )


def draw_moba_monitoring_control(
    draw: Any,
    control: Any,
    x: int,
    y: int,
    c: Any,
    *,
    checked: bool,
    geometry: Any,
) -> None:
    if control.control_type == "checkbox":
        check_x = x + geometry.anchor_x
        check_y = y + geometry.static_y + geometry.check_y_offset
        draw.rectangle(
            (check_x, check_y, check_x + geometry.check_size, check_y + geometry.check_size),
            outline=c.control_text,
            fill=c.window,
        )
        if checked and len(geometry.checkmark_points) >= 3:
            start, middle, end = geometry.checkmark_points[:3]
            draw.line(
                (check_x + start[0], check_y + start[1], check_x + middle[0], check_y + middle[1]),
                fill=c.control_text,
                width=1,
            )
            draw.line(
                (check_x + middle[0], check_y + middle[1], check_x + end[0], check_y + end[1]),
                fill=c.control_text,
                width=1,
            )
        draw_moba_monitoring_control_icon(
            draw,
            control.icon_key,
            x + geometry.icon_x,
            y + geometry.static_y,
            geometry.icon_size,
            c,
        )
        draw_text(
            draw,
            control.label,
            x + geometry.label_x,
            y + geometry.static_y + geometry.label_y_offset,
            c.control_text,
            geometry.label_font_size,
            bold=geometry.label_bold,
        )
        return
    draw_moba_monitoring_control_icon(
        draw,
        control.icon_key,
        x + geometry.icon_x,
        y + geometry.static_y,
        geometry.icon_size,
        c,
    )
    draw_text(
        draw,
        control.label,
        x + geometry.label_x,
        y + geometry.static_y + geometry.label_y_offset,
        c.control_text,
        geometry.label_font_size,
        bold=geometry.label_bold,
    )


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


def draw_moba_sftp_file_icon(draw: Any, icon_key: str, x: int, y: int, size: int, c: Any) -> None:
    if icon_key in {"folder", "folder-up"}:
        fill = "#f2c744" if icon_key == "folder" else "#f5d96a"
        draw.rectangle((x, y + 4, x + size, y + size - 1), fill=fill, outline=c.pane_border)
        draw.rectangle((x + 2, y + 2, x + 8, y + 5), fill="#ffe58a", outline=c.pane_border)
        if icon_key == "folder-up":
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
    if preset.id == "securecrt":
        draw_securecrt_title_bar(draw, preset, x, y, w, h)
        return
    if preset.id == "termius":
        draw_termius_title_bar(draw, preset, x, y, w, h)
        return
    if preset.id == "remmina":
        draw_remmina_title_bar(draw, preset, x, y, w, h)
        return
    if preset.id == "mremoteng":
        draw_mremoteng_title_bar(draw, preset, x, y, w, h)
        return
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)
    draw_text(draw, "Remote Ops Workspace", x + 14, y + 9, c.control_text, 14, bold=True)
    draw_text(draw, preset.label, x + 190, y + 9, c.sidebar_muted, 13)
    for index, token in enumerate(("-", "+", "x")):
        bx = x + w - 92 + index * 30
        draw_text(draw, token, bx, y + 8, c.sidebar_muted, 14, bold=True)


def draw_termius_title_bar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    """A quiet app switcher, rather than the generic desktop-window heading."""
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.window)
    draw.ellipse((x + 14, y + 9, x + 23, y + 18), fill=c.primary)
    draw_text(draw, "Remote Ops", x + 30, y + 9, c.control_text, 12, bold=True)
    nav_x = x + 166
    for label in ("Vaults", "Keychain", "Port forwarding", "Snippets"):
        draw_text(draw, label, nav_x, y + 10, c.sidebar_muted, 9)
        nav_x += len(label) * 6 + 26
    rounded(draw, (x + w - 118, y + 6, x + w - 48, y + 27), c.control, c.control_border, 10)
    draw_text(draw, "⌘  K", x + w - 104, y + 11, c.sidebar_muted, 8, bold=True)
    draw.ellipse((x + w - 35, y + 7, x + w - 14, y + 27), fill=c.status)
    draw_text(draw, "O", x + w - 29, y + 11, c.primary_text, 8, bold=True)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)


def draw_remmina_title_bar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    """A compact GTK-like header without the shared application marketing copy."""
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.rectangle((x + 14, y + 10, x + 26, y + 22), fill=c.primary)
    draw_text(draw, "Remote Desktop Client", x + 34, y + 10, c.control_text, 12, bold=True)
    menu_x = x + 220
    for label in ("Connection", "Edit", "View", "Tools", "Help"):
        draw_text(draw, label, menu_x, y + 11, c.sidebar_muted, 9)
        menu_x += len(label) * 6 + 18
    for index, token in enumerate(("−", "□", "×")):
        draw_text(draw, token, x + w - 85 + index * 26, y + 9, c.sidebar_muted, 12, bold=True)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)


def draw_securecrt_title_bar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_securecrt_top_chrome()
    draw.rectangle((x, y, x + w, y + h), fill=c.window)
    draw_text(draw, chrome.window_title, x + 8, y + 3, c.control_text, 10, bold=True)
    for index, token in enumerate(("-", "[]", "x")):
        bx = x + w - 82 + index * 27
        draw_text(draw, token, bx, y + 2, c.sidebar_muted, 10, bold=True)
    menu_x = x + 7
    menu_y = y + max(18, h - 14)
    for item in chrome.menu_items:
        draw_text(draw, item.label, menu_x, menu_y, c.control_text, 10)
        menu_x += max(36, len(item.label) * 7 + 13)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)


def draw_mremoteng_title_bar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_mremoteng_top_chrome()
    draw.rectangle((x, y, x + w, y + h), fill=c.window)
    draw_text(draw, chrome.window_title, x + 8, y + 3, c.control_text, 10, bold=True)
    for index, token in enumerate(("-", "[]", "x")):
        bx = x + w - 82 + index * 27
        draw_text(draw, token, bx, y + 2, c.sidebar_muted, 10, bold=True)
    menu_x = x + 7
    menu_y = y + max(18, h - 14)
    for item in chrome.menu_items:
        draw_text(draw, item.label, menu_x, menu_y, c.control_text, 10)
        menu_x += max(42, len(item.label) * 7 + 15)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)


def draw_toolbar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    if preset.id == "securecrt":
        draw_securecrt_toolbar(draw, preset, x, y, w, h)
        return
    if preset.id == "mremoteng":
        draw_mremoteng_toolbar(draw, preset, x, y, w, h)
        return
    if preset.id == "termius":
        draw_termius_toolbar(draw, preset, x, y, w, h)
        return
    if preset.id == "remmina":
        draw_remmina_toolbar(draw, preset, x, y, w, h)
        return
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


def draw_termius_toolbar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)
    for label, bx in (("Hosts", x + 20), ("Recent", x + 83)):
        draw_text(draw, label, bx, y + 20, c.control_text if label == "Hosts" else c.sidebar_muted, 10, bold=label == "Hosts")
    draw.rectangle((x + 18, y + 42, x + 58, y + 44), fill=c.primary)
    search_x = x + 315
    rounded(draw, (search_x, y + 12, search_x + 310, y + 40), c.terminal, c.control_border, 8)
    draw_text(draw, "⌕  Find a host", search_x + 12, y + 20, c.sidebar_muted, 10)
    rounded(draw, (x + w - 236, y + 12, x + w - 132, y + 40), c.primary, c.primary, 8)
    draw_text(draw, "+  New Host", x + w - 220, y + 20, c.primary_text, 9, bold=True)
    rounded(draw, (x + w - 120, y + 12, x + w - 18, y + 40), c.control, c.control_border, 8)
    draw_text(draw, "Terminal", x + w - 106, y + 20, c.control_text, 9, bold=True)


def draw_remmina_toolbar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)
    for index, icon in enumerate(("+", "▣", "✎", "⊟")):
        rounded(draw, (x + 16 + index * 34, y + 12, x + 42 + index * 34, y + 38), c.control, c.control_border, 3)
        draw_text(draw, icon, x + 24 + index * 34, y + 19, c.primary, 10, bold=True)
    protocol_x = x + 170
    draw.rectangle((protocol_x, y + 12, protocol_x + 90, y + 39), fill="#ffffff", outline=c.control_border)
    draw_text(draw, "RDP  ▾", protocol_x + 10, y + 20, c.control_text, 9)
    draw.rectangle((protocol_x + 98, y + 12, protocol_x + 365, y + 39), fill="#ffffff", outline=c.control_border)
    draw_text(draw, "Server or hostname", protocol_x + 108, y + 20, c.sidebar_muted, 9)
    rounded(draw, (protocol_x + 373, y + 12, protocol_x + 454, y + 39), "#3d8b3d", "#327232", 3)
    draw_text(draw, "Connect!", protocol_x + 385, y + 20, "#ffffff", 9, bold=True)


def draw_securecrt_toolbar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)
    # Native SecureCRT toolbar: tiny action glyphs, host and keyword fields.
    for index, icon in enumerate(("session-manager", "new-session", "connect", "properties")):
        draw_securecrt_toolbar_icon(draw, icon, x + 12 + index * 27, y + 12, 15, c, disabled=False)
    host_x = x + 126
    draw.rectangle((host_x, y + 10, host_x + 150, y + 31), fill="#ffffff", outline="#adadad")
    draw_text(draw, "Enter host <Alt+P>", host_x + 7, y + 16, "#888888", 8)
    key_x = host_x + 160
    draw.rectangle((key_x, y + 10, key_x + 142, y + 31), fill="#ffffff", outline="#adadad")
    draw_text(draw, "Keyword <Alt+/>", key_x + 7, y + 16, "#888888", 8)
    draw_text(draw, "⌕", key_x + 120, y + 13, c.primary, 13)
    for index, glyph in enumerate(("▣", "⚙", "▤", "⚑", "?")):
        draw_text(draw, glyph, key_x + 158 + index * 27, y + 13, "#3f4b56", 13, bold=True)


def draw_mremoteng_toolbar(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.toolbar)
    draw.line((x, y + h - 1, x + w, y + h - 1), fill=c.toolbar_border)
    # Small legacy toolbar matching the compact mRemoteNG window chrome.
    draw_text(draw, "Connect:", x + 12, y + 17, "#425364", 9)
    draw.rectangle((x + 62, y + 10, x + 180, y + 31), fill="#ffffff", outline="#b7c0c9")
    draw_text(draw, "", x + 70, y + 16, "#333333", 8)
    for index, icon in enumerate(("new-connection", "open-connection", "external-tool", "refresh-tree", "config")):
        draw_mremoteng_toolbar_icon(draw, icon, x + 193 + index * 31, y + 12, 15, c, disabled=False)
    draw_text(draw, "RDP", x + 365, y + 17, "#3f6f98", 9, bold=True)
    draw_text(draw, "⌄", x + 391, y + 16, "#3f6f98", 9)


def draw_securecrt_toolbar_icon(
    draw: Any,
    icon_key: str,
    x: int,
    y: int,
    size: int,
    c: Any,
    *,
    disabled: bool,
) -> None:
    color = c.sidebar_muted if disabled else c.primary
    dark = c.window
    white = c.control_text if not disabled else c.sidebar_muted
    mid = size // 2
    if icon_key == "session-manager":
        draw.rectangle((x + 2, y + 6, x + size - 2, y + size - 2), fill=color, outline=white)
        draw.rectangle((x + 4, y + 4, x + 11, y + 7), fill=color, outline=white)
        return
    if icon_key == "new-session":
        draw.rectangle((x + 2, y + 2, x + size - 2, y + size - 4), fill=dark, outline=color)
        draw.line((x + mid, y + 5, x + mid, y + size - 8), fill=color, width=2)
        draw.line((x + 5, y + mid - 1, x + size - 5, y + mid - 1), fill=color, width=2)
        return
    if icon_key == "properties":
        draw.rectangle((x + 4, y + 3, x + size - 4, y + size - 3), outline=color, width=2)
        draw_text(draw, "P", x + 7, y + 5, color, 9, bold=True)
        return
    if icon_key == "delete":
        draw.line((x + 4, y + 4, x + size - 4, y + size - 4), fill=color, width=2)
        draw.line((x + size - 4, y + 4, x + 4, y + size - 4), fill=color, width=2)
        return
    if icon_key == "connect":
        draw.polygon([(x + 4, y + 3), (x + size - 3, y + mid), (x + 4, y + size - 3)], fill=color)
        return
    if icon_key == "sftp":
        draw.rectangle((x + 2, y + 6, x + size - 2, y + size - 2), fill=color, outline=white)
        draw.line((x + 5, y + 11, x + size - 5, y + 11), fill=dark, width=1)
        return
    if icon_key == "transfer":
        draw.line((x + 3, y + 6, x + size - 4, y + 6), fill=color, width=2)
        draw.polygon([(x + size - 4, y + 3), (x + size - 1, y + 6), (x + size - 4, y + 9)], fill=color)
        draw.line((x + size - 3, y + 12, x + 4, y + 12), fill=color, width=2)
        draw.polygon([(x + 4, y + 9), (x + 1, y + 12), (x + 4, y + 15)], fill=color)
        return
    if icon_key == "command":
        draw.rectangle((x + 2, y + 3, x + size - 2, y + size - 3), fill=dark, outline=color)
        draw.line((x + 5, y + 7, x + 9, y + 10), fill=color, width=2)
        draw.line((x + 9, y + 10, x + 5, y + 13), fill=color, width=2)
        return
    if icon_key == "tools":
        draw.line((x + 4, y + 4, x + size - 5, y + size - 5), fill=color, width=2)
        draw.line((x + size - 5, y + 4, x + 5, y + size - 4), fill=color, width=2)
        return
    if icon_key in {"tile-h", "tile-v"}:
        draw.rectangle((x + 2, y + 3, x + size - 2, y + size - 3), outline=color, width=2)
        if icon_key == "tile-h":
            draw.line((x + 2, y + mid, x + size - 2, y + mid), fill=color, width=2)
        else:
            draw.line((x + mid, y + 3, x + mid, y + size - 3), fill=color, width=2)
        return
    draw.rectangle((x + 3, y + 3, x + size - 3, y + size - 3), outline=color)


def draw_mremoteng_toolbar_icon(
    draw: Any,
    icon_key: str,
    x: int,
    y: int,
    size: int,
    c: Any,
    *,
    disabled: bool,
) -> None:
    color = c.sidebar_muted if disabled else c.primary
    dark = c.window
    mid = size // 2
    if icon_key == "refresh-tree":
        draw.arc((x + 3, y + 3, x + size - 3, y + size - 3), 35, 320, fill=color, width=2)
        draw.polygon([(x + size - 4, y + 5), (x + size - 1, y + 8), (x + size - 6, y + 10)], fill=color)
        return
    if icon_key == "new-connection":
        draw.rectangle((x + 2, y + 3, x + size - 3, y + size - 3), fill=dark, outline=color)
        draw.line((x + mid, y + 5, x + mid, y + size - 6), fill=color, width=2)
        draw.line((x + 5, y + mid, x + size - 6, y + mid), fill=color, width=2)
        return
    if icon_key == "config":
        draw.rectangle((x + 3, y + 3, x + size - 4, y + size - 4), outline=color, width=2)
        draw_text(draw, "C", x + 6, y + 5, color, 8, bold=True)
        return
    if icon_key == "open-connection":
        draw.polygon([(x + 4, y + 3), (x + size - 3, y + mid), (x + 4, y + size - 3)], fill=color)
        draw.rectangle((x + 1, y + 5, x + 5, y + size - 5), fill=dark, outline=color)
        return
    if icon_key == "external-tool":
        draw.rectangle((x + 2, y + 4, x + size - 5, y + size - 3), fill=dark, outline=color)
        draw.line((x + 7, y + size - 7, x + size - 2, y + 3), fill=color, width=2)
        draw.polygon([(x + size - 2, y + 3), (x + size - 3, y + 8), (x + size - 7, y + 4)], fill=color)
        return
    if icon_key == "script":
        draw.rectangle((x + 2, y + 3, x + size - 2, y + size - 3), fill=dark, outline=color)
        draw.line((x + 5, y + 7, x + 8, y + mid), fill=color, width=2)
        draw.line((x + 8, y + mid, x + 5, y + size - 7), fill=color, width=2)
        draw.line((x + 10, y + size - 6, x + size - 4, y + size - 6), fill=color, width=1)
        return
    draw_securecrt_toolbar_icon(draw, icon_key, x, y, size, c, disabled=disabled)


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
    if preset.id == "securecrt":
        draw_securecrt_command_manager(draw, preset, x, y, w, h)
        return
    if preset.id == "mremoteng":
        draw_mremoteng_docks(draw, preset, x, y, w, h)
        return
    rounded(draw, (x, y, x + w, y + h), c.sidebar, c.pane_border, 5)
    title, subtitle = gui_design_sidebar_copy(preset.id)
    draw_text(draw, title, x + 14, y + 14, c.sidebar_text, 14, bold=True)
    draw_text(draw, subtitle, x + 14, y + 34, c.sidebar_muted, 10)
    draw_text(draw, preset.density, x + w - 86, y + 15, c.sidebar_muted, 11)
    rows = gui_design_tree_rows(preset.id)
    row_y = y + 66
    if preset.id == "termius":
        draw_termius_hosts_chrome(draw, preset, x + 10, y + 58, w - 20, 72)
        row_y = y + 150
    elif preset.id == "remmina":
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


def draw_securecrt_command_manager(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    """Native Command Manager dock patterned after the supplied SecureCRT view."""
    draw.rectangle((x, y, x + w, y + h), fill="#f5f5f5", outline="#a9a9a9")
    draw.rectangle((x, y, x + w, y + 25), fill="#e7eef5", outline="#a9a9a9")
    draw_text(draw, "Command Manager", x + 8, y + 7, "#243342", 10, bold=True)
    draw_text(draw, "⚑", x + w - 32, y + 7, "#202020", 10)
    draw_text(draw, "×", x + w - 15, y + 7, "#202020", 11)
    button_x = x + 10
    for icon in ("➤", "+", "✂", "□", "×", "⚙"):
        draw_text(draw, icon, button_x, y + 34, "#3b4650", 14, bold=True)
        button_x += 28
    draw.rectangle((x + 7, y + 58, x + w - 7, y + 80), fill="#ffffff", outline="#b7b7b7")
    draw_text(draw, "Filter by folder/command name <Alt+Y>", x + 13, y + 65, "#777777", 8)
    draw_text(draw, "⌕", x + w - 22, y + 63, "#3c78b4", 12)
    tree_y = y + 92
    rows = (
        ("⌄", "Commands", "#3c78b4", True),
        ("⌄", "Admin", "#d1a737", True),
        ("●", "df", "#d21616", False),
        ("●", "free", "#d21616", False),
        ("●", "netstat", "#d21616", False),
        ("⌄", "General", "#d1a737", True),
        ("●", "ps all", "#17b330", False),
        ("●", "top", "#17b330", False),
        ("●", "cal", "#17b330", False),
    )
    indent = 0
    for icon, label, color, folder in rows:
        if label == "Admin":
            indent = 17
        elif label == "General":
            indent = 17
        elif label == "ps all":
            indent = 36
        draw_text(draw, icon, x + 10 + indent, tree_y, color, 12, bold=folder)
        draw_text(draw, label, x + 28 + indent, tree_y + 1, "#222222", 10)
        tree_y += 22
    draw.rectangle((x, y + h - 26, x + w, y + h), fill="#ffffff", outline="#b7b7b7")
    draw_text(draw, "Session Manager", x + 9, y + h - 18, "#222222", 9)
    draw_text(draw, "Command Manager", x + 112, y + h - 18, "#222222", 9)


def draw_mremoteng_docks(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    """Recreate the compact Connections/Search/Config dock stack of mRemoteNG."""
    top_h = int(h * 0.47)
    draw.rectangle((x, y, x + w, y + top_h), fill="#f4f4f4", outline="#a7b1bc")
    draw.rectangle((x, y, x + w, y + 24), fill="#0078c8", outline="#0078c8")
    draw_text(draw, "Connections", x + 8, y + 7, "#ffffff", 10, bold=True)
    draw_text(draw, "⚑  ×", x + w - 40, y + 6, "#ffffff", 10)
    for index, icon in enumerate(("◉", "⌂", "+", "−", "A", "★")):
        draw_text(draw, icon, x + 10 + index * 23, y + 33, "#356f9e", 11, bold=True)
    tree_y = y + 59
    for icon, label, depth, selected in (
        ("◉", "Connections", 0, False),
        ("▣", "Windows", 1, False),
        ("▣", "Exchange 1", 2, True),
        ("▣", "Exchange 2", 2, False),
        ("▣", "Linux", 1, False),
        ("●", "Proxy Server", 2, False),
    ):
        if selected:
            draw.rectangle((x + 4 + depth * 17, tree_y - 2, x + w - 5, tree_y + 16), fill="#d9e8f6")
        draw_text(draw, icon, x + 10 + depth * 17, tree_y, "#3471a0" if icon != "▣" else "#d6a62a", 10)
        draw_text(draw, label, x + 26 + depth * 17, tree_y + 1, "#1f1f1f", 9)
        tree_y += 19
    draw.rectangle((x, y + top_h - 23, x + w, y + top_h), fill="#ffffff", outline="#c0c0c0")
    draw_text(draw, "⌕  Search", x + 8, y + top_h - 16, "#52606e", 9)
    config_y = y + top_h + 7
    draw.rectangle((x, config_y, x + w, y + h), fill="#f8f8f8", outline="#a7b1bc")
    draw.rectangle((x, config_y, x + w, config_y + 23), fill="#e7edf3", outline="#a7b1bc")
    draw_text(draw, "Config", x + 8, config_y + 7, "#253544", 10, bold=True)
    draw_text(draw, "⚑  ×", x + w - 40, config_y + 6, "#253544", 10)
    for index, icon in enumerate(("☷", "A", "▤", "⊞", "⌘")):
        draw_text(draw, icon, x + 10 + index * 23, config_y + 32, "#4f86b1", 10)
    prop_y = config_y + 55
    for group, rows in (("Display", (("Name", "Proxy Server"), ("Description", ""))), ("Connection", (("Hostname/IP", "edge-prod.example.invalid"), ("Port", "22"), ("Username", "operator")))):
        draw_text(draw, "⌄", x + 8, prop_y, "#333333", 9)
        draw_text(draw, group, x + 22, prop_y, "#273747", 9, bold=True)
        prop_y += 18
        for key, value in rows:
            draw_text(draw, key, x + 28, prop_y, "#444444", 8)
            draw_text(draw, value, x + 105, prop_y, "#111111", 8, bold=bool(value))
            prop_y += 17


def draw_remmina_profile_list_chrome(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_remmina_profile_list_chrome()
    route = gui_design_remmina_profile_viewer_route()
    filter_route = gui_design_remmina_profile_filter_route()
    selected_rows = [row for row in chrome.rows if row.selected]
    if len(selected_rows) != 1 or selected_rows[0].key != route.selected_profile_key:
        raise RuntimeError("Remmina profile-viewer route selected profile metadata drifted")
    if selected_rows[0].protocol != route.protocol or selected_rows[0].status != route.profile_status:
        raise RuntimeError("Remmina profile-viewer route protocol/status metadata drifted")
    if filter_route.selected_profile_key != route.selected_profile_key:
        raise RuntimeError("Remmina profile-filter route selected profile metadata drifted")
    if filter_route.expected_placeholder != chrome.filter_placeholder:
        raise RuntimeError("Remmina profile-filter route placeholder metadata drifted")
    if filter_route.expected_query.lower() not in selected_rows[0].protocol.lower():
        raise RuntimeError("Remmina profile-filter route query no longer matches selected protocol")
    interaction = gui_design_interaction_state(preset.id)
    rounded(draw, (x, y, x + w, y + h), c.pane, c.pane_border, 4)
    draw_text(draw, chrome.title, x + chrome.static_title_x, y + chrome.static_title_y, c.control_text, 10, bold=True)
    filter_x = x + chrome.static_filter_x
    filter_box = (
        filter_x,
        y + chrome.static_filter_y,
        x + w - chrome.static_filter_right_margin,
        y + chrome.static_filter_y + chrome.static_filter_height,
    )
    rounded(draw, filter_box, c.control, c.control_border, 3)
    if interaction.focused_control == "profile-filter":
        fx1, fy1, fx2, fy2 = filter_box
        draw.rectangle((fx1 - 2, fy1 - 2, fx2 + 2, fy2 + 2), outline=c.primary, width=1)
    draw_text(
        draw,
        chrome.filter_placeholder,
        filter_x + chrome.static_filter_placeholder_x,
        y + chrome.static_filter_placeholder_y,
        c.sidebar_muted,
        8,
    )
    header_y = y + chrome.static_header_y
    col_x = x + chrome.static_column_start_x
    for column in chrome.columns:
        draw_text(draw, column.label, col_x, header_y, c.sidebar_muted, 8, bold=True)
        col_x += column.static_width
    row_y = y + chrome.static_row_start_y
    for row in chrome.rows:
        fill = c.sidebar_selected if row.selected else c.control
        outline = c.primary if row.selected or row.key == route.selected_profile_key else c.control_border
        rounded(
            draw,
            (
                x + chrome.static_row_x_margin,
                row_y,
                x + w - chrome.static_row_x_margin,
                row_y + chrome.static_row_height,
            ),
            fill,
            outline,
            3,
        )
        values = {"name": row.name, "protocol": row.protocol, "server": row.server}
        col_x = x + chrome.static_cell_start_x
        for column in chrome.columns:
            text_color = c.sidebar_selected_text if row.selected else c.control_text
            if column.key == "protocol":
                text_color = c.primary
            draw_text(
                draw,
                values[column.key],
                col_x,
                row_y + chrome.static_cell_y,
                text_color,
                8,
                bold=column.key == "name",
            )
            col_x += column.static_width
        draw_text(draw, row.status, x + chrome.static_cell_start_x, row_y + chrome.static_status_y, c.sidebar_muted, 7)
        row_y += chrome.static_row_step


def draw_securecrt_session_manager_chrome(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_securecrt_session_manager_chrome()
    route = gui_design_securecrt_session_manager_route()
    filter_route = gui_design_securecrt_session_manager_filter_route()
    interaction = gui_design_interaction_state(preset.id)
    if route.session_manager_object != "secureCrtSessionManagerChrome":
        raise RuntimeError("SecureCRT session-manager route object drifted")
    if filter_route.filter_object != "secureCrtSessionFilter":
        raise RuntimeError("SecureCRT Session Manager filter route object drifted")
    if filter_route.expected_placeholder != chrome.filter_placeholder:
        raise RuntimeError("SecureCRT Session Manager filter placeholder drifted")
    if filter_route.matched_result_label != route.selected_tree_label:
        raise RuntimeError("SecureCRT Session Manager filter match drifted")
    if filter_route.expected_query.lower() not in route.selected_tree_label.lower():
        raise RuntimeError("SecureCRT Session Manager filter query no longer matches selected row")
    rounded(draw, (x, y, x + w, y + h), c.pane, c.control_border, 3)
    draw_text(draw, chrome.title, x + chrome.static_title_x, y + chrome.static_title_y, c.control_text, 10, bold=True)
    for action in chrome.actions:
        routed = action.key == route.session_manager_action_key
        bx = x + action.static_x
        by = y + action.static_y
        border = c.primary if routed else c.control_border
        rounded(draw, (bx, by, bx + action.static_button_size, by + action.static_button_size), c.control, border, 2)
        draw_securecrt_session_manager_action_icon(
            draw,
            preset,
            action.icon_key,
            bx + action.static_icon_x,
            by + action.static_icon_y,
            action.static_icon_size,
        )
    filter_y = y + chrome.static_filter_y
    filter_box = (
        x + chrome.static_filter_x_margin,
        filter_y,
        x + w - chrome.static_filter_x_margin,
        filter_y + chrome.static_filter_height,
    )
    rounded(draw, filter_box, c.terminal, c.primary, 2)
    if interaction.focused_control == "session-filter":
        fx1, fy1, fx2, fy2 = filter_box
        draw.rectangle((fx1 - 2, fy1 - 2, fx2 + 2, fy2 + 2), outline=c.control_hover, width=1)
    draw_text(
        draw,
        chrome.filter_placeholder,
        x + chrome.static_filter_placeholder_x,
        filter_y + chrome.static_filter_placeholder_y,
        c.sidebar_muted,
        9,
    )


def draw_securecrt_session_manager_action_icon(
    draw: Any,
    preset: GuiDesignPreset,
    icon_key: str,
    x: int,
    y: int,
    size: int,
) -> None:
    c = preset.colors
    if icon_key == "folder":
        draw_sidebar_row_icon(draw, preset, "folder", x, y, size, selected=False, group=True)
        return
    if icon_key == "properties":
        draw_text(draw, "P", x, y, c.primary, size, bold=True)
        return
    draw_text(draw, ">", x, y, c.primary, size, bold=True)


def draw_securecrt_session_tree(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    interaction = gui_design_interaction_state(preset.id)
    sftp_route = gui_design_securecrt_sftp_tab_route()
    root_title, root_subtitle = gui_design_tree_root_copy(preset.id)
    root_icon = gui_design_tree_root_icon(preset.id)
    draw.rectangle((x, y, x + w, y + h), fill=c.sidebar)
    draw_sidebar_row_icon(draw, preset, root_icon.icon_key, x + 3, y + 3, root_icon.static_size, selected=False, group=True)
    draw_text(draw, root_title, x + 26, y + 3, c.status, 11, bold=True)
    draw_text(draw, root_subtitle, x + 26, y + 18, c.sidebar_muted, 8)

    row_y = y + 44
    branch_x = x + 18
    for name, target, group in gui_design_tree_rows(preset.id):
        label = name.strip()
        selected = label == interaction.selected_tree_label
        if group:
            icon_key = sidebar_row_icon_key(preset.id, name, target, group)
            draw.line((branch_x, row_y + 14, branch_x + 12, row_y + 14), fill=c.toolbar_border)
            draw_sidebar_row_icon(draw, preset, icon_key, x + 4, row_y + 2, 14, selected=False, group=True)
            draw_text(draw, label, x + 26, row_y + 1, c.status, 11, bold=True)
            draw.line((branch_x, row_y + 21, branch_x, row_y + 52), fill=c.toolbar_border)
            row_y += 28
            continue
        row_top = row_y - 3
        row_bottom = row_top + 33
        if selected:
            rounded(draw, (x + 18, row_top, x + w - 2, row_bottom), c.sidebar_selected, c.sidebar_selected, 4)
            draw.rectangle((x + 18, row_top, x + 22, row_bottom), fill=c.primary)
        elif label == sftp_route.selected_tree_label:
            rounded(draw, (x + 18, row_top, x + w - 2, row_bottom), c.sidebar, c.primary, 4)
        draw.line((branch_x, row_y + 11, branch_x + 20, row_y + 11), fill=c.toolbar_border)
        draw_sidebar_row_icon(draw, preset, sidebar_row_icon_key(preset.id, name, target, group), x + 28, row_y, 13, selected=selected, group=False)
        text = c.sidebar_selected_text if selected else c.sidebar_text
        muted = c.sidebar_selected_text if selected else c.sidebar_muted
        draw_text(draw, label, x + 49, row_y - 1, text, 11)
        draw_text(draw, target, x + 49, row_y + 13, muted, 8)
        row_y += 34


def draw_termius_hosts_chrome(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_termius_hosts_chrome()
    sync_route = gui_design_termius_sync_route()
    if not any(action.key == sync_route.hosts_action_key for action in chrome.actions):
        raise RuntimeError("Termius sync route Hosts action metadata drifted")
    interaction = gui_design_interaction_state(preset.id)
    rounded(draw, (x, y, x + w, y + h), c.pane, c.control_border, 3)
    draw_text(draw, chrome.title, x + 8, y + 8, c.control_text, 10, bold=True)
    for action in chrome.actions:
        bx = x + action.static_x
        by = y + 5
        rounded(draw, (bx, by, bx + 20, by + 20), c.control, c.control_border, 2)
        draw_termius_hosts_action_icon(draw, action.icon_key, bx + 5, by + 5, 10, c.primary)
    filter_y = y + 35
    rounded(draw, (x + 8, filter_y, x + w - 8, filter_y + 24), c.terminal, c.primary, 2)
    if interaction.focused_control == "host-search":
        draw.rectangle((x + 6, filter_y - 2, x + w - 6, filter_y + 26), outline=c.control_hover, width=1)
    draw_text(draw, chrome.filter_placeholder, x + 17, filter_y + 7, c.sidebar_muted, 9)


def draw_termius_hosts_action_icon(draw: Any, icon_key: str, x: int, y: int, size: int, color: str) -> None:
    if icon_key == "plus":
        mid = x + size // 2
        draw.line((mid, y + 2, mid, y + size - 2), fill=color, width=2)
        draw.line((x + 2, y + size // 2, x + size - 2, y + size // 2), fill=color, width=2)
        return
    if icon_key == "key":
        draw.ellipse((x, y + 2, x + 5, y + 7), outline=color, width=2)
        draw.line((x + 5, y + 5, x + size, y + 5), fill=color, width=2)
        draw.line((x + size - 3, y + 5, x + size - 3, y + 8), fill=color, width=2)
        return
    if icon_key == "sync":
        draw.arc((x + 1, y + 1, x + size - 1, y + size - 1), 35, 270, fill=color, width=2)
        draw.polygon([(x + 2, y + 3), (x + 5, y + 1), (x + 5, y + 5)], fill=color)
        return
    draw.rectangle((x + 2, y + 2, x + size - 2, y + size - 2), outline=color)


def sidebar_row_icon_key(preset_id: str, name: str, target: str, group: bool) -> str:
    return gui_design_tree_row_icon_key(preset_id, name, target, group)


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
    if icon_key == "ssh2":
        draw.rectangle((x, y + 2, x + size, y + size - 1), fill="#101820", outline=fill)
        draw.line((x + 3, y + 5, x + 6, y + 8), fill=fill, width=1)
        draw.line((x + 6, y + 8, x + 3, y + 11), fill=fill, width=1)
        draw.line((x + 8, y + 11, x + size - 3, y + 11), fill=fill, width=1)
        draw_text(draw, "2", x + size - 5, y + 2, fill, 6, bold=True)
        return
    if icon_key == "command":
        draw.rectangle((x, y + 2, x + size, y + size - 1), fill="#101820", outline=fill)
        draw.line((x + 3, y + 5, x + 7, y + 8), fill=fill, width=1)
        draw.line((x + 7, y + 8, x + 3, y + 11), fill=fill, width=1)
        draw.rectangle((x + size - 5, y + 4, x + size - 2, y + 7), outline=fill)
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
    product_identity_route = gui_design_product_identity_route(preset.id)
    if product_identity_route.selected_profile_name != reference.profile_name:
        raise RuntimeError(f"{preset.id} product identity route profile metadata drifted")
    if product_identity_route.active_tab_label != reference.active_tab_label:
        raise RuntimeError(f"{preset.id} product identity route active tab metadata drifted")
    if product_identity_route.target_label != reference.target_label:
        raise RuntimeError(f"{preset.id} product identity route target metadata drifted")
    if product_identity_route.protocol_label != reference.protocol_label:
        raise RuntimeError(f"{preset.id} product identity route protocol metadata drifted")
    if product_identity_route.status_segments != reference.status_segments:
        raise RuntimeError(f"{preset.id} product identity route status segment metadata drifted")
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
    route = gui_design_securecrt_session_manager_route()
    reference = gui_design_reference_state(preset.id)
    if route.active_tab_label != reference.active_tab_label or route.target_value != reference.target_label:
        raise RuntimeError("SecureCRT reference session metadata drifted")
    # The supplied SecureCRT screens are native and terminal-led: document tabs
    # directly above one Session / SFTP surface, with no dashboard cards or activity log.
    tabs_h = 31
    draw_tabs(draw, preset, x, y, w, tabs_h)
    pane_y = y + tabs_h
    pane_h = h - tabs_h
    draw.rectangle((x, pane_y, x + w, pane_y + pane_h), fill="#ffffff", outline="#b5b5b5")
    draw_rectangle = draw.rectangle
    draw_rectangle((x + 8, pane_y + 7, x + w - 8, pane_y + 31), fill="#f7f7f7", outline="#c5c5c5")
    draw_text(draw, "SSH2: edge-prod.example.invalid", x + 16, pane_y + 14, "#202020", 10, bold=True)
    draw_text(draw, "Connected", x + w - 84, pane_y + 14, "#297137", 9, bold=True)
    draw_securecrt_reference_terminal(draw, x + 9, pane_y + 38, w - 18, pane_h - 47)


def draw_securecrt_reference_terminal(draw: Any, x: int, y: int, w: int, h: int) -> None:
    """Single full document session with the native terminal palette in image #1."""
    draw.rectangle((x, y, x + w, y + h), fill="#003b45", outline="#888888")
    draw_text(draw, "show interface serial 0", x + 10, y + 10, "#fff65c", 11, mono=True)
    lines = (
        ("Serial0 is up, line protocol is up", "#fff65c"),
        ("  Hardware is MCI Serial", "#d3e6e3"),
        ("  Internet address is 155.155.155.90/28, subnet mask is 255.255.255.240", "#d3e6e3"),
        ("  MTU 1500 bytes, BW 1544 Kbit, DLY 20000 usec,", "#d3e6e3"),
        ("     76762 drops; input queue 0/75, 301 drops", "#e9a000"),
        ("  54283 packets output, 65566998 bytes, 0 underruns", "#d3e6e3"),
        ("  2 carrier transitions", "#ff3d35"),
        ("Router#", "#fff65c"),
    )
    line_y = y + 31
    for text, color in lines:
        draw_text(draw, text, x + 10, line_y, color, 10, mono=True)
        line_y += 18


def draw_securecrt_sftp_browser(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    route = gui_design_securecrt_sftp_browser_route()
    tab_route = gui_design_securecrt_sftp_tab_route()
    if route.sftp_tab_route_key != tab_route.key:
        raise RuntimeError("SecureCRT SFTP browser route tab key drifted")
    if route.sftp_tab_label != tab_route.sftp_tab_label:
        raise RuntimeError("SecureCRT SFTP browser route tab label drifted")
    if route.selected_tree_label != tab_route.selected_tree_label:
        raise RuntimeError("SecureCRT SFTP browser route selected tree label drifted")
    if route.action_key not in route.toolbar_actions:
        raise RuntimeError("SecureCRT SFTP browser live action missing from toolbar actions")
    if route.signal != "clicked":
        raise RuntimeError("SecureCRT SFTP browser live action signal drifted")
    if route.handler != "handle_securecrt_sftp_browser_action":
        raise RuntimeError("SecureCRT SFTP browser live action handler drifted")
    rounded(draw, (x, y, x + w, y + h), c.log, c.control_border, 3)
    draw_text(draw, f"SFTP - {route.sftp_tab_label}", x + 10, y + 8, c.log_text, 10, bold=True)
    draw_text(draw, route.transfer_queue_label, x + w - 58, y + 8, c.terminal_accent, 8, mono=True)
    action_x = x + 10
    action_y = y + 28
    for action in route.toolbar_actions:
        action_w = 52
        rounded(draw, (action_x, action_y, action_x + action_w, action_y + 18), c.control, c.control_border, 2)
        draw_text(draw, action.title(), action_x + 7, action_y + 5, c.control_text, 8)
        action_x += action_w + 5
    path_y = action_y + 24
    rounded(draw, (x + 10, path_y, x + w - 10, path_y + 18), c.terminal, c.control_border, 2)
    draw_text(draw, route.remote_path, x + 18, path_y + 5, c.terminal_accent, 8, mono=True)
    header_y = path_y + 24
    draw_text(draw, "Name", x + 12, header_y, c.sidebar_muted, 8, bold=True)
    draw_text(draw, "Size", x + w - 104, header_y, c.sidebar_muted, 8, bold=True)
    draw_text(draw, "Modified", x + w - 64, header_y, c.sidebar_muted, 8, bold=True)
    row_y = header_y + 14
    for row in route.file_rows:
        row_h = 15
        fill = c.control if row.selected else c.log
        border = c.primary if row.selected else c.control_border
        rounded(draw, (x + 10, row_y, x + w - 10, row_y + row_h), fill, border, 2)
        icon = "[D]" if row.kind == "folder" else "[F]"
        draw_text(draw, icon, x + 14, row_y + 4, c.terminal_accent, 7, mono=True)
        draw_text(draw, row.name, x + 36, row_y + 4, c.log_text, 7, mono=True)
        draw_text(draw, row.size, x + w - 104, row_y + 4, c.log_text, 7, mono=True)
        draw_text(draw, row.modified, x + w - 64, row_y + 4, c.log_text, 7, mono=True)
        row_y += row_h + 3


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
    host_route = gui_design_termius_host_selection_route()
    reference = gui_design_reference_state(preset.id)
    if host_route.active_tab_label != reference.active_tab_label:
        raise RuntimeError("Termius host-selection route active tab metadata drifted")
    if host_route.selected_profile_name != reference.profile_name:
        raise RuntimeError("Termius host-selection route profile metadata drifted")
    if host_route.target_value != reference.target_label:
        raise RuntimeError("Termius host-selection route target metadata drifted")
    if host_route.protocol_value != reference.protocol_label:
        raise RuntimeError("Termius host-selection route protocol metadata drifted")
    draw_termius_hosts_reference(draw, preset, x, y, w, h)
    return
    tabs_w = 86
    log_y = y + h - log_h
    draw_termius_navigation_rail(draw, preset, x, y, tabs_w, log_y - y - 8)
    pane_x = x + tabs_w
    pane_w = w - tabs_w
    pane_h = log_y - y - 8
    rounded(draw, (pane_x, y, pane_x + pane_w, y + pane_h), c.pane, c.pane_border, 5)
    draw_text(draw, "edge-prod", pane_x + 20, y + 18, c.control_text, 17, bold=True)
    draw_text(draw, "prod  ·  SSH  ·  edge-prod.example.invalid", pane_x + 20, y + 43, c.sidebar_muted, 10)
    rounded(draw, (pane_x + pane_w - 124, y + 16, pane_x + pane_w - 22, y + 47), c.primary, c.primary, 9)
    draw_text(draw, "Connect", pane_x + pane_w - 96, y + 26, c.primary_text, 10, bold=True)
    tab_x = pane_x + 18
    for tab in ("Terminal", "Files", "Tunnels", "SFTP"):
        active = tab == "Terminal"
        draw_text(draw, tab, tab_x, y + 78, c.control_text if active else c.sidebar_muted, 10, bold=active)
        if active:
            draw.rectangle((tab_x, y + 96, tab_x + 51, y + 98), fill=c.primary)
        tab_x += len(tab) * 7 + 32
    strip_y = y + 108
    draw_termius_host_identity_strip(draw, preset, pane_x + 12, strip_y, pane_w - 24, 30)

    term_w = int(pane_w * 0.64)
    main_h = pane_h - 196
    flow_y = y + 98 + main_h
    terminal_y = strip_y + 38
    terminal_h = flow_y - terminal_y - 10
    draw_product_terminal(draw, preset, surface, pane_x + 12, terminal_y, term_w - 18, terminal_h)
    detail_x = pane_x + term_w + 4
    files_h = max(132, min(152, terminal_h // 2))
    detail_h = terminal_h - files_h - 8
    draw_detail_panel(
        draw,
        preset,
        surface,
        detail_x,
        terminal_y,
        pane_w - term_w - 16,
        detail_h,
        heading="Vault / Snippets",
    )
    draw_termius_files_browser(
        draw,
        preset,
        detail_x,
        terminal_y + detail_h + 8,
        pane_w - term_w - 16,
        files_h,
    )
    draw_termius_session_workflow(draw, preset, pane_x + 12, flow_y, pane_w - 24, y + pane_h - flow_y - 10)
    draw_product_activity_log(draw, preset, surface, x, log_y, w, y + h - log_y, "Connection log")


def draw_termius_navigation_rail(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    draw.rectangle((x, y, x + w, y + h), fill=c.sidebar)
    items = (("●", "Hosts", True), ("◆", "Vaults", False), ("⌘", "Snippets", False), ("↔", "Tunnels", False), ("◌", "Known", False))
    item_y = y + 20
    for icon, label, active in items:
        if active:
            rounded(draw, (x + 8, item_y - 7, x + w - 8, item_y + 25), c.sidebar_selected, c.sidebar_selected, 5)
        draw_text(draw, icon, x + 15, item_y, c.primary if active else c.sidebar_muted, 11, bold=True)
        draw_text(draw, label, x + 32, item_y + 1, c.sidebar_selected_text if active else c.sidebar_muted, 8, bold=active)
        item_y += 48
    draw.line((x + w - 1, y, x + w - 1, y + h), fill=c.pane_border)


def draw_termius_hosts_reference(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    """Host and vault manager based on the supplied Termius desktop hierarchy."""
    c = preset.colors
    rail_w = 62
    details_w = 282
    draw_termius_navigation_rail(draw, preset, x, y, rail_w, h)
    center_x = x + rail_w + 1
    center_w = w - rail_w - details_w - 8
    detail_x = center_x + center_w + 8
    draw.rectangle((center_x, y, center_x + center_w, y + h), fill=c.pane, outline=c.pane_border)
    draw.rectangle((detail_x, y, x + w, y + h), fill="#171c1f", outline=c.pane_border)
    draw_text(draw, "All vaults", center_x + 18, y + 18, c.control_text, 16, bold=True)
    draw_text(draw, "Personal vault", center_x + 18, y + 42, c.sidebar_muted, 9)
    draw_text(draw, "Groups", center_x + 18, y + 80, c.sidebar_muted, 10, bold=True)
    card_y = y + 104
    cards = (("AWS", "12 hosts"), ("Development", "8 hosts"), ("Staging", "4 hosts"), ("Production", "3 hosts"))
    for index, (name, count) in enumerate(cards):
        card_x = center_x + 18 + (index % 2) * ((center_w - 54) // 2)
        card_top = card_y + (index // 2) * 74
        card_w = (center_w - 54) // 2
        rounded(draw, (card_x, card_top, card_x + card_w, card_top + 58), c.control, c.control_border, 7)
        draw.ellipse((card_x + 13, card_top + 16, card_x + 30, card_top + 33), fill=c.primary)
        draw_text(draw, name, card_x + 41, card_top + 13, c.control_text, 11, bold=True)
        draw_text(draw, count, card_x + 41, card_top + 31, c.sidebar_muted, 8)
    hosts_y = card_y + 170
    draw_text(draw, "Hosts", center_x + 18, hosts_y, c.sidebar_muted, 10, bold=True)
    rows = (("edge-prod", "ssh · operator · Production"), ("api-dev", "ssh · deploy · Development"), ("db-staging", "ssh · readonly · Staging"))
    row_y = hosts_y + 25
    for index, (name, sub) in enumerate(rows):
        selected = index == 0
        fill = c.sidebar_selected if selected else c.control
        outline = c.primary if selected else c.control_border
        rounded(draw, (center_x + 16, row_y, center_x + center_w - 16, row_y + 48), fill, outline, 6)
        draw.ellipse((center_x + 29, row_y + 14, center_x + 48, row_y + 33), fill="#e6a93d")
        draw_text(draw, name, center_x + 62, row_y + 10, c.sidebar_selected_text if selected else c.control_text, 11, bold=True)
        draw_text(draw, sub, center_x + 62, row_y + 27, c.sidebar_muted, 8)
        draw_text(draw, "⋮", center_x + center_w - 38, row_y + 14, c.sidebar_muted, 13)
        row_y += 56
    draw_text(draw, "Host Details", detail_x + 16, y + 18, "#eef5f1", 12, bold=True)
    draw_text(draw, "Production vault", detail_x + 16, y + 42, c.primary, 9)
    draw_text(draw, "edge-prod", detail_x + 16, y + 83, "#ffffff", 15, bold=True)
    draw_text(draw, "137.184.95.44", detail_x + 16, y + 108, c.sidebar_muted, 10)
    rounded(draw, (detail_x + 16, y + 136, x + w - 16, y + 169), c.primary, c.primary, 8)
    draw_centered_text(draw, "Connect", detail_x + 16, y + 146, details_w - 32, c.primary_text, 10, bold=True)
    field_y = y + 198
    for label, value in (("Hostname", "edge-prod.example.invalid"), ("Protocol", "SSH"), ("Port", "22"), ("Username", "operator")):
        draw_text(draw, label, detail_x + 16, field_y, c.sidebar_muted, 8)
        draw_text(draw, value, detail_x + 16, field_y + 14, "#ffffff", 9)
        draw.line((detail_x + 16, field_y + 31, x + w - 16, field_y + 31), fill=c.control_border)
        field_y += 49


def draw_termius_files_browser(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    route = gui_design_termius_files_browser_route()
    host_route = gui_design_termius_host_selection_route()
    if route.host_selection_route_key != host_route.key:
        raise RuntimeError("Termius files browser route host-selection key drifted")
    if route.active_tab_label != host_route.active_tab_label:
        raise RuntimeError("Termius files browser route active tab drifted")
    if route.selected_profile_name != host_route.selected_profile_name:
        raise RuntimeError("Termius files browser route selected profile drifted")
    if route.action_key not in route.toolbar_actions:
        raise RuntimeError("Termius files browser live action missing from toolbar actions")
    if route.signal != "clicked":
        raise RuntimeError("Termius files browser live action signal drifted")
    if route.handler != "handle_termius_files_sync":
        raise RuntimeError("Termius files browser live action handler drifted")
    rounded(draw, (x, y, x + w, y + h), c.log, c.control_border, 5)
    draw_text(draw, f"Files - {route.selected_profile_name}", x + 10, y + 8, c.log_text, 10, bold=True)
    draw_text(draw, route.transfer_queue_label, x + w - 66, y + 8, c.terminal_accent, 8, mono=True)
    action_x = x + 10
    action_y = y + 28
    for action in route.toolbar_actions:
        action_w = 58
        rounded(draw, (action_x, action_y, action_x + action_w, action_y + 18), c.control, c.control_border, 6)
        draw_text(draw, action.title(), action_x + 8, action_y + 5, c.control_text, 8)
        action_x += action_w + 6
    path_y = action_y + 24
    rounded(draw, (x + 10, path_y, x + w - 10, path_y + 18), c.terminal, c.control_border, 5)
    draw_text(draw, route.remote_path, x + 18, path_y + 5, c.terminal_accent, 8, mono=True)
    header_y = path_y + 24
    draw_text(draw, "Name", x + 12, header_y, c.sidebar_muted, 8, bold=True)
    draw_text(draw, "Size", x + w - 104, header_y, c.sidebar_muted, 8, bold=True)
    draw_text(draw, "Modified", x + w - 64, header_y, c.sidebar_muted, 8, bold=True)
    row_y = header_y + 14
    for row in route.file_rows:
        row_h = 15
        fill = c.control if row.selected else c.log
        border = c.primary if row.selected else c.control_border
        rounded(draw, (x + 10, row_y, x + w - 10, row_y + row_h), fill, border, 4)
        icon = "[D]" if row.kind == "folder" else "[F]"
        draw_text(draw, icon, x + 14, row_y + 4, c.terminal_accent, 7, mono=True)
        draw_text(draw, row.name, x + 36, row_y + 4, c.log_text, 7, mono=True)
        draw_text(draw, row.size, x + w - 104, row_y + 4, c.log_text, 7, mono=True)
        draw_text(draw, row.modified, x + w - 64, row_y + 4, c.log_text, 7, mono=True)
        row_y += row_h + 3


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
    draw_text(draw, "RDP viewer", x + 22, toolbar_y + 10, c.control_text, 12, bold=True)
    route = gui_design_remmina_profile_viewer_route()
    clipboard_route = gui_design_remmina_clipboard_route()
    screenshot_route = gui_design_remmina_screenshot_route()
    sftp_transfer_route = gui_design_remmina_sftp_transfer_route()
    reference = gui_design_reference_state("remmina")
    if route.active_tab_label != reference.active_tab_label:
        raise RuntimeError("Remmina profile-viewer route active tab metadata drifted")
    if route.profile_status != surface.primary_state or route.profile_status != reference.workspace_state:
        raise RuntimeError("Remmina profile-viewer route scale state metadata drifted")
    if clipboard_route.active_tab_label != reference.active_tab_label:
        raise RuntimeError("Remmina clipboard route active tab metadata drifted")
    if clipboard_route.status_segment not in reference.status_segments:
        raise RuntimeError("Remmina clipboard route status segment metadata drifted")
    if clipboard_route.clipboard_state != surface.secondary_state:
        raise RuntimeError("Remmina clipboard route workspace state metadata drifted")
    if clipboard_route.detail_line not in surface.detail_lines:
        raise RuntimeError("Remmina clipboard route detail-line metadata drifted")
    if clipboard_route.activity_line not in surface.activity_lines:
        raise RuntimeError("Remmina clipboard route activity-line metadata drifted")
    if screenshot_route.active_tab_label != reference.active_tab_label:
        raise RuntimeError("Remmina screenshot route active tab metadata drifted")
    if screenshot_route.status_segment not in reference.status_segments:
        raise RuntimeError("Remmina screenshot route status segment metadata drifted")
    if screenshot_route.detail_line not in surface.detail_lines:
        raise RuntimeError("Remmina screenshot route detail-line metadata drifted")
    if screenshot_route.activity_line not in surface.activity_lines:
        raise RuntimeError("Remmina screenshot route activity-line metadata drifted")
    if not screenshot_route.capture_artifact.endswith(".png"):
        raise RuntimeError("Remmina screenshot route capture artifact must be a PNG filename")
    if screenshot_route.signal != "clicked":
        raise RuntimeError("Remmina screenshot route live capture signal drifted")
    if screenshot_route.handler != "handle_remmina_screenshot_capture":
        raise RuntimeError("Remmina screenshot route live capture handler drifted")
    if screenshot_route.live_triggered_property != "remminaScreenshotRouteLiveTriggered":
        raise RuntimeError("Remmina screenshot route live capture trigger property drifted")
    if sftp_transfer_route.detail_line not in surface.detail_lines:
        raise RuntimeError("Remmina SFTP transfer route detail-line metadata drifted")
    if sftp_transfer_route.activity_line not in surface.activity_lines:
        raise RuntimeError("Remmina SFTP transfer route activity-line metadata drifted")
    if sftp_transfer_route.active_tab_label not in {label for label, _status, _active in gui_design_tab_items("remmina")}:
        raise RuntimeError("Remmina SFTP transfer route tab metadata drifted")
    if sftp_transfer_route.toolbar_action_label != {
        key: label for key, label, _tooltip in gui_design_toolbar_actions("remmina")
    }.get(sftp_transfer_route.toolbar_action_key):
        raise RuntimeError("Remmina SFTP transfer route toolbar metadata drifted")
    draw_remmina_home_reference(draw, preset, x, y, w, h)
    return
    controls = gui_design_remmina_viewer_controls()
    if route.viewer_control_key not in {control.key for control in controls}:
        raise RuntimeError("Remmina profile-viewer route target control is missing")
    if clipboard_route.viewer_control_key not in {control.key for control in controls}:
        raise RuntimeError("Remmina clipboard route target control is missing")
    if screenshot_route.viewer_control_key not in {control.key for control in controls}:
        raise RuntimeError("Remmina screenshot route target control is missing")
    control_x = x + w - 410
    for control in controls:
        routed_control = control.key in {
            route.viewer_control_key,
            clipboard_route.viewer_control_key,
            screenshot_route.viewer_control_key,
        }
        rounded(
            draw,
            (
                control_x,
                toolbar_y + control.static_y,
                control_x + control.static_width,
                toolbar_y + control.static_y + control.static_height,
            ),
            c.toolbar if routed_control else c.control,
            c.primary if routed_control else c.control_border,
            2,
        )
        draw_remmina_viewer_control_icon(
            draw,
            control.icon_key,
            control_x + control.static_icon_x,
            toolbar_y + control.static_y + 3,
            control.static_icon_size,
            c.primary,
            c.control_text,
        )
        draw_text(draw, control.label, control_x + control.static_label_x, toolbar_y + control.static_y + 5, c.control_text, 8)
        control_x += control.static_step
    viewer_x = x + 18
    viewer_y = toolbar_y + 48
    viewer_w = int(w * 0.72)
    viewer_h = pane_h - 66
    draw_remote_viewer(draw, preset, surface, viewer_x, viewer_y, viewer_w, viewer_h)
    transfer_h = max(132, min(150, viewer_h // 2))
    options_h = viewer_h - transfer_h - 8
    detail_x = viewer_x + viewer_w + 12
    detail_w = w - viewer_w - 42
    draw_detail_panel(
        draw,
        preset,
        surface,
        detail_x,
        viewer_y,
        detail_w,
        options_h,
        heading="Profile Options",
    )
    draw_remmina_sftp_transfer_panel(
        draw,
        preset,
        detail_x,
        viewer_y + options_h + 8,
        detail_w,
        transfer_h,
    )
    draw_product_activity_log(draw, preset, surface, x, log_y, w, y + h - log_y, "Connection activity")


def draw_remmina_home_reference(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    """Saved-connection home screen with Remmina's compact GTK list workflow."""
    c = preset.colors
    tabs_h = 30
    draw.rectangle((x, y, x + w, y + h), fill="#f6f7f8", outline="#c3cbd2")
    draw.rectangle((x, y, x + w, y + tabs_h), fill="#eef1f4", outline="#c3cbd2")
    for index, (label, active) in enumerate((("Quick Connect", True), ("win-admin", False), ("linux-console", False))):
        tab_x = x + 10 + index * 135
        draw.rectangle((tab_x, y + 4, tab_x + 126, y + 29), fill="#ffffff" if active else "#e2e7ec", outline="#b8c2cc")
        draw_text(draw, label, tab_x + 10, y + 12, c.control_text, 9, bold=active)
    list_y = y + tabs_h + 16
    draw_text(draw, "Saved connections", x + 18, list_y, c.control_text, 13, bold=True)
    draw_text(draw, "Create a new connection or select a profile to connect.", x + 18, list_y + 21, c.sidebar_muted, 9)
    table_x = x + 18
    table_y = list_y + 53
    table_w = w - 36
    draw.rectangle((table_x, table_y, table_x + table_w, table_y + 31), fill="#e5e9ed", outline="#bac4cc")
    columns = (("Name", 0), ("Group", 235), ("Server", 410), ("Protocol", 650))
    for label, offset in columns:
        draw_text(draw, label, table_x + 12 + offset, table_y + 10, "#44515c", 9, bold=True)
    row_y = table_y + 31
    rows = (("win-admin", "Windows", "admin-win.example.invalid", "RDP"), ("linux-console", "Linux", "edge-prod.example.invalid", "SSH"), ("lab-desktop", "Lab", "lab.example.invalid", "VNC"))
    for index, row in enumerate(rows):
        fill = "#dcecff" if index == 0 else "#ffffff"
        draw.rectangle((table_x, row_y, table_x + table_w, row_y + 38), fill=fill, outline="#d2d9df")
        draw_text(draw, "▣", table_x + 12, row_y + 12, c.primary if index == 0 else "#657381", 10)
        for value, (_label, offset) in zip(row, columns, strict=True):
            draw_text(draw, value, table_x + 32 + offset, row_y + 12, c.control_text, 9, bold=index == 0 and offset == 0)
        row_y += 38
    action_y = row_y + 24
    draw_text(draw, "Recent connections", table_x, action_y, c.sidebar_muted, 10, bold=True)
    for index, label in enumerate(("Connect", "Edit", "Delete", "Import")):
        bx = table_x + index * 88
        rounded(draw, (bx, action_y + 18, bx + 76, action_y + 46), c.control, c.control_border, 3)
        draw_centered_text(draw, label, bx, action_y + 27, 76, c.control_text, 9, bold=label == "Connect")
    draw_text(draw, "Total 3 items", x + 18, y + h - 24, c.sidebar_muted, 9)


def draw_remmina_sftp_transfer_panel(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    route = gui_design_remmina_sftp_transfer_route()
    profile_chrome = gui_design_remmina_profile_list_chrome()
    rows_by_key = {row.key: row for row in profile_chrome.rows}
    profile_row = rows_by_key.get(route.selected_profile_key)
    if profile_row is None:
        raise RuntimeError("Remmina SFTP transfer route selected profile row missing")
    if profile_row.protocol != route.selected_profile_protocol:
        raise RuntimeError("Remmina SFTP transfer route profile protocol drifted")
    if route.action_key not in route.toolbar_actions:
        raise RuntimeError("Remmina SFTP transfer route action key must be part of toolbar actions")
    if route.signal != "clicked":
        raise RuntimeError("Remmina SFTP transfer route live signal metadata drifted")
    if route.handler != "handle_remmina_sftp_transfer_action":
        raise RuntimeError("Remmina SFTP transfer route live handler metadata drifted")
    if route.live_triggered_property != "remminaSftpTransferRouteLiveTriggered":
        raise RuntimeError("Remmina SFTP transfer route live trigger metadata drifted")
    rounded(draw, (x, y, x + w, y + h), c.log, c.control_border, 4)
    draw_text(draw, f"SFTP - {route.selected_profile_name}", x + 10, y + 8, c.log_text, 10, bold=True)
    draw_text(draw, route.transfer_queue_label, x + w - 58, y + 8, c.terminal_accent, 8, mono=True)
    action_x = x + 10
    action_y = y + 28
    for action in route.toolbar_actions:
        action_w = 58
        rounded(draw, (action_x, action_y, action_x + action_w, action_y + 18), c.control, c.control_border, 2)
        draw_text(draw, action.title(), action_x + 7, action_y + 5, c.control_text, 8)
        action_x += action_w + 5
    path_y = action_y + 24
    rounded(draw, (x + 10, path_y, x + w - 10, path_y + 18), c.terminal, c.control_border, 3)
    draw_text(draw, route.remote_path, x + 18, path_y + 5, c.terminal_accent, 8, mono=True)
    header_y = path_y + 24
    draw_text(draw, "Name", x + 12, header_y, c.sidebar_muted, 8, bold=True)
    draw_text(draw, "Size", x + w - 104, header_y, c.sidebar_muted, 8, bold=True)
    draw_text(draw, "Modified", x + w - 64, header_y, c.sidebar_muted, 8, bold=True)
    row_y = header_y + 14
    for row in route.file_rows:
        row_h = 15
        fill = c.control if row.selected else c.log
        border = c.primary if row.selected else c.control_border
        rounded(draw, (x + 10, row_y, x + w - 10, row_y + row_h), fill, border, 3)
        icon = "[D]" if row.kind == "folder" else "[F]"
        draw_text(draw, icon, x + 14, row_y + 4, c.terminal_accent, 7, mono=True)
        draw_text(draw, row.name, x + 36, row_y + 4, c.log_text, 7, mono=True)
        draw_text(draw, row.size, x + w - 104, row_y + 4, c.log_text, 7, mono=True)
        draw_text(draw, row.modified, x + w - 64, row_y + 4, c.log_text, 7, mono=True)
        row_y += row_h + 3


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
    route = gui_design_mremoteng_connection_document_route()
    reference = gui_design_reference_state("mremoteng")
    if route.active_tab_label != reference.active_tab_label or route.selected_profile_name != reference.profile_name:
        raise RuntimeError("mRemoteNG reference connection metadata drifted")
    # mRemoteNG's document surface is a docked multi-session canvas: two document
    # panes and a Notifications dock, not a dashboard/property-table workspace.
    tabs_h = 30
    draw_tabs(draw, preset, x, y, w, tabs_h)
    pane_y = y + tabs_h
    notification_h = 104
    document_h = h - tabs_h - notification_h - 8
    draw.rectangle((x, pane_y, x + w, pane_y + document_h), fill="#ececf1", outline="#a9a9b0")
    left_w = int(w * 0.56)
    left_x = x + 7
    right_x = x + left_w + 4
    draw_mremoteng_remote_desktop(draw, left_x, pane_y + 7, left_w - 10, document_h - 14)
    draw_mremoteng_ssh_document(draw, right_x, pane_y + 7, w - left_w - 11, document_h - 14)
    notify_y = pane_y + document_h + 6
    draw.rectangle((x, notify_y, x + w, y + h), fill="#ffffff", outline="#a7b1bc")
    draw.rectangle((x, notify_y, x + w, notify_y + 23), fill="#e9edf2", outline="#a7b1bc")
    draw_text(draw, "Notifications", x + 8, notify_y + 7, "#34485a", 9, bold=True)
    draw_text(draw, "⚑  ×", x + w - 39, notify_y + 6, "#34485a", 9)
    draw_text(draw, "Connected to Proxy Server via SSH2", x + 12, notify_y + 37, "#4a4a4a", 9)
    draw_text(draw, "Exchange 1 opened in a tabbed document", x + 12, notify_y + 54, "#4a4a4a", 9)


def draw_mremoteng_remote_desktop(draw: Any, x: int, y: int, w: int, h: int) -> None:
    draw.rectangle((x, y, x + w, y + h), fill="#000000", outline="#777777")
    draw_text(draw, "Exchange 1", x + 12, y + 12, "#f2f2f2", 10)
    draw.rectangle((x + 18, y + 47, x + 47, y + 76), fill="#dfe8f0", outline="#ffffff")
    draw_text(draw, "Recycle Bin", x + 10, y + 80, "#ffffff", 8)
    draw.rectangle((x + 18, y + h - 28, x + w - 18, y + h - 1), fill="#111111")
    draw_text(draw, "⊞     ⌕     □", x + 25, y + h - 20, "#ffffff", 12)
    draw_text(draw, "19:08", x + w - 64, y + h - 21, "#ffffff", 8)


def draw_mremoteng_ssh_document(draw: Any, x: int, y: int, w: int, h: int) -> None:
    draw.rectangle((x, y, x + w, y + h), fill="#000000", outline="#777777")
    draw_text(draw, "Proxy Server", x + 10, y + 10, "#f3f3f3", 10)
    lines = (
        "Using username 'operator'.",
        "Authenticated with public key from agent",
        "Welcome to Ubuntu 22.04 LTS",
        "",
        " * Documentation:  https://help.ubuntu.com",
        " * Management:     https://landscape.canonical.com",
        "",
        "System information as of 19:08:24 UTC",
        "System load:  0.01      Processes: 173",
        "Memory usage: 37%       Users logged in: 0",
        "IP address for ens160: 10.32.0.42",
        "",
        "operator@edge-prod:~$",
    )
    line_y = y + 31
    for line in lines:
        draw_text(draw, line, x + 14, line_y, "#e8dfad" if line.startswith(" *") else "#e4e4e4", 9, mono=True)
        line_y += 17


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
    send_route = gui_design_securecrt_command_window_send_route()
    if (
        send_route.command_input_object != "secureCrtCommandInput"
        or send_route.send_control_object != "secureCrtCommandSend"
        or send_route.command_property != "secureCrtCommandRouteCommand"
        or send_route.signal != "clicked"
        or send_route.secondary_signal != "returnPressed"
        or send_route.handler != "handle_securecrt_command_window_send"
    ):
        raise RuntimeError("SecureCRT command-window send route metadata drifted")
    rounded(draw, (x, y, x + w, y + h), c.log, c.pane_border, 2)
    draw.rectangle((x + 1, y + 1, x + w - 1, y + chrome.static_header_height), fill=c.toolbar)
    draw_text(draw, chrome.title, x + chrome.static_title_x, y + chrome.static_title_y, c.control_text, 10, bold=True)
    draw_text(draw, chrome.helper, x + chrome.static_helper_x, y + chrome.static_helper_y, c.sidebar_muted, 9)
    control_y = y + chrome.static_control_y
    control_bottom = y + h - chrome.static_control_bottom_margin
    target_x = x + chrome.static_target_x
    rounded(
        draw,
        (target_x, control_y, target_x + chrome.static_target_width, control_bottom),
        c.control,
        c.control_border,
        2,
    )
    draw_sidebar_row_icon(
        draw,
        preset,
        "database",
        x + chrome.static_target_icon_x,
        control_y + chrome.static_target_icon_y,
        chrome.static_target_icon_size,
        selected=False,
        group=False,
    )
    draw_text(
        draw,
        chrome.target_scope,
        x + chrome.static_target_label_x,
        control_y + chrome.static_target_label_y,
        c.control_text,
        9,
    )
    input_x = x + chrome.static_input_x
    send_x = x + w - chrome.static_send_width - chrome.static_send_right_margin
    draw.rectangle(
        (input_x, control_y, x + w - chrome.static_send_width - chrome.static_send_input_gap, control_bottom),
        fill=c.terminal,
        outline=c.primary,
    )
    draw_text(
        draw,
        chrome.command,
        input_x + chrome.static_input_text_x,
        control_y + chrome.static_input_text_y,
        c.terminal_accent,
        10,
        mono=True,
    )
    rounded(draw, (send_x, control_y, x + w - chrome.static_send_right_margin, control_bottom), c.primary, c.primary, 2)
    draw_text(
        draw,
        chrome.send_label,
        send_x + chrome.static_send_label_x,
        control_y + chrome.static_send_label_y,
        c.primary_text,
        9,
        bold=True,
    )


def draw_securecrt_session_status_strip(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_securecrt_session_status_strip()
    route = gui_design_securecrt_session_manager_route()
    sftp_route = gui_design_securecrt_sftp_tab_route()
    if route.status_strip_object != "secureCrtSessionStatusStrip":
        raise RuntimeError("SecureCRT session-manager route status-strip object drifted")
    rounded(draw, (x, y, x + w, y + h), c.pane, c.control_border, 2)
    draw_text(draw, chrome.title, x + chrome.static_title_x, y + chrome.static_title_y, c.sidebar_muted, 9, bold=True)
    cell_x = x + chrome.static_cell_start_x
    for field in chrome.fields:
        if field.key == route.status_field_key and field.value != route.target_value:
            raise RuntimeError("SecureCRT session-manager route status value drifted")
        cell_w = field.static_width
        if cell_x + cell_w > x + w - 6:
            break
        is_status = field.role == "status"
        cell_fill = c.primary if is_status else c.terminal
        cell_text = c.primary_text if is_status else c.control_text
        border = c.primary if field.key in {route.status_field_key, sftp_route.status_field_key} else c.control_border
        rounded(
            draw,
            (cell_x, y + field.static_y, cell_x + cell_w, y + field.static_y + field.static_height),
            cell_fill,
            border,
            2,
        )
        label_color = c.primary_text if is_status else c.sidebar_muted
        draw_text(draw, field.label, cell_x + field.static_label_x, y + field.static_label_y, label_color, 8)
        draw_text(
            draw,
            field.value,
            cell_x + field.static_value_x,
            y + field.static_value_y,
            cell_text,
            8,
            mono=True,
            bold=is_status,
        )
        cell_x += cell_w + chrome.static_cell_gap


def draw_termius_session_workflow(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    port_forward_route = gui_design_termius_port_forward_route()
    snippet_route = gui_design_termius_snippet_route()
    rounded(draw, (x, y, x + w, y + h), c.log, c.pane_border, 5)
    draw_text(draw, "Host workflow", x + 12, y + 10, c.log_text, 12, bold=True)
    card_y = y + 34
    card_h = max(44, h - 44)
    gap = 10
    card_w = (w - gap * 2 - 24) // 3
    cards = [
        ("host", "Vault identity", "prod-ed25519 unlocked", "agent key chained"),
        ("sftp", "Port forward", port_forward_route.forward_value, "local tunnel ready"),
        ("snippet", snippet_route.workflow_title, snippet_route.snippet_command, snippet_route.snippet_state),
    ]
    if port_forward_route.forward_state != "ready":
        raise RuntimeError("Termius port-forward route workflow state drifted")
    if snippet_route.workflow_card_key != "snippet":
        raise RuntimeError("Termius snippet route workflow key drifted")
    if snippet_route.snippet_state != "one-click command":
        raise RuntimeError("Termius snippet route workflow state drifted")
    if snippet_route.action_label != "Run" or snippet_route.shortcut_sequence != "Return":
        raise RuntimeError("Termius snippet route live action metadata drifted")
    for index, (icon_key, title, primary, secondary) in enumerate(cards):
        cx = x + 12 + index * (card_w + gap)
        rounded(draw, (cx, card_y, cx + card_w, card_y + card_h), c.control, c.control_border, 8)
        draw_sidebar_row_icon(draw, preset, icon_key, cx + 12, card_y + 14, 18, selected=False, group=False)
        draw_text(draw, title, cx + 40, card_y + 10, c.control_text, 10, bold=True)
        draw_text(draw, primary, cx + 40, card_y + 28, c.terminal_accent, 9, mono=True)
        draw_text(draw, secondary, cx + 40, card_y + 45, c.sidebar_muted, 8)
        if icon_key == snippet_route.workflow_card_key:
            action_x = cx + card_w - 54
            action_y = card_y + card_h - 25
            rounded(draw, (action_x, action_y, action_x + 42, action_y + 18), c.primary, c.primary, 5)
            draw_text(draw, snippet_route.action_label, action_x + 12, action_y + 4, c.primary_text, 8, bold=True)


def draw_termius_host_identity_strip(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    strip = gui_design_termius_host_identity_strip()
    sync_route = gui_design_termius_sync_route()
    host_route = gui_design_termius_host_selection_route()
    port_forward_route = gui_design_termius_port_forward_route()
    snippet_route = gui_design_termius_snippet_route()
    if host_route.host_identity_object != "termiusHostIdentityStrip":
        raise RuntimeError("Termius host-selection route identity object drifted")
    if port_forward_route.host_identity_object != "termiusHostIdentityStrip":
        raise RuntimeError("Termius port-forward route identity object drifted")
    if snippet_route.host_identity_object != "termiusHostIdentityStrip":
        raise RuntimeError("Termius snippet route identity object drifted")
    rounded(draw, (x, y, x + w, y + h), c.pane, c.control_border, 2)
    draw_text(draw, strip.title, x + strip.static_title_x, y + strip.static_title_y, c.sidebar_muted, 9, bold=True)
    cell_x = x + strip.static_cell_start_x
    for field in strip.fields:
        if field.key == host_route.identity_field_key and field.value != host_route.host_value:
            raise RuntimeError("Termius host-selection route host value drifted")
        if field.key == sync_route.identity_field_key and field.value != sync_route.sync_state:
            raise RuntimeError("Termius sync route identity field metadata drifted")
        if field.key == port_forward_route.identity_field_key and field.value != port_forward_route.forward_value:
            raise RuntimeError("Termius port-forward route identity field metadata drifted")
        if field.key == snippet_route.identity_field_key and field.value != snippet_route.snippet_command:
            raise RuntimeError("Termius snippet route identity field metadata drifted")
        cell_w = field.static_width
        if cell_x + cell_w > x + w - 6:
            break
        is_status = field.role == "status"
        cell_fill = c.primary if is_status else c.terminal
        cell_text = c.primary_text if is_status else c.control_text
        routed_field_keys = {
            host_route.identity_field_key,
            port_forward_route.identity_field_key,
            snippet_route.identity_field_key,
        }
        border = c.primary if field.key in routed_field_keys else c.control_border
        rounded(
            draw,
            (cell_x, y + field.static_y, cell_x + cell_w, y + field.static_y + field.static_height),
            cell_fill,
            border,
            2,
        )
        label_color = c.primary_text if is_status else c.sidebar_muted
        draw_text(draw, field.label, cell_x + field.static_label_x, y + field.static_label_y, label_color, 8)
        draw_text(
            draw,
            field.value,
            cell_x + field.static_value_x,
            y + field.static_value_y,
            cell_text,
            8,
            mono=True,
            bold=is_status,
        )
        cell_x += cell_w + strip.static_cell_gap


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
    route = gui_design_mremoteng_connection_document_route()
    filter_route = gui_design_mremoteng_document_filter_route()
    interaction = gui_design_interaction_state(preset.id)
    toolbar_h = min(h, chrome.static_height)
    draw.rectangle((x, y, x + w, y + toolbar_h), fill=c.control, outline=c.pane_border)
    draw_text(draw, chrome.title, x + chrome.static_margin_x, y + 8, c.control_text, 10, bold=True)
    button_x = x + chrome.static_button_start_x
    controls = gui_design_mremoteng_document_controls()
    if route.document_control_key not in {control.key for control in controls}:
        raise RuntimeError("mRemoteNG connection-document route target control is missing")
    if route.signal != "clicked":
        raise RuntimeError("mRemoteNG reconnect live route signal drifted")
    if route.handler != "handle_mremoteng_document_reconnect":
        raise RuntimeError("mRemoteNG reconnect live route handler drifted")
    if route.reconnect_state != "reconnected":
        raise RuntimeError("mRemoteNG reconnect live route state drifted")
    if filter_route.selected_tree_label != route.selected_tree_label:
        raise RuntimeError("mRemoteNG document-filter route selected tree metadata drifted")
    if filter_route.expected_placeholder != chrome.filter_placeholder:
        raise RuntimeError("mRemoteNG document-filter route placeholder metadata drifted")
    if filter_route.expected_query.lower() not in route.selected_tree_label.lower():
        raise RuntimeError("mRemoteNG document-filter route query no longer matches selected tree row")
    for control in controls:
        state = "checked" if control.key == "external-tool" and interaction.checked_toolbar_key == "files" else "normal"
        _fill, outline, text = interaction_button_colors(state, c)
        routed_control = control.key == route.document_control_key
        button_box = (
            button_x,
            y + control.static_y,
            button_x + control.static_width,
            y + control.static_y + control.static_height,
        )
        rounded(draw, button_box, c.control if routed_control else c.toolbar, c.primary if routed_control else c.control_border, 2)
        if state == "checked" or routed_control:
            draw.rectangle(
                (
                    button_x - 2,
                    y + control.static_y - 2,
                    button_x + control.static_width + 2,
                    y + control.static_y + control.static_height + 2,
                ),
                outline=c.primary if routed_control else outline,
                width=1,
            )
        draw_mremoteng_document_control_icon(
            draw,
            control.icon_key,
            button_x + control.static_icon_x,
            y + control.static_icon_y,
            control.static_icon_size,
            c.primary,
            c.control_text,
        )
        draw_text(
            draw,
            control.label,
            button_x + control.static_label_x,
            y + control.static_label_y,
            text,
            9,
            bold=state == "checked",
        )
        button_x += control.static_width + chrome.static_button_gap
    filter_box = (
        x + w - chrome.static_filter_width - chrome.static_margin_x,
        y + chrome.static_filter_y,
        x + w - chrome.static_margin_x,
        y + chrome.static_filter_y + chrome.static_filter_height,
    )
    draw.rectangle(filter_box, fill=c.window, outline=c.control_border)
    if interaction.focused_control == "tree-filter":
        fx1, fy1, fx2, fy2 = filter_box
        draw.rectangle((fx1 - 2, fy1 - 2, fx2 + 2, fy2 + 2), outline=c.primary, width=1)
    draw_text(draw, chrome.filter_placeholder, filter_box[0] + 10, y + 9, c.sidebar_muted, 9)


def draw_mremoteng_document_control_icon(
    draw: Any,
    icon_key: str,
    x: int,
    y: int,
    size: int,
    color: str,
    text_color: str,
) -> None:
    if icon_key == "database":
        draw.ellipse((x + 1, y, x + size - 1, y + 5), outline=color)
        draw.rectangle((x + 1, y + 3, x + size - 1, y + size - 3), fill=None, outline=color)
        draw.arc((x + 1, y + size - 6, x + size - 1, y + size - 1), 0, 180, fill=color)
        draw.line((x + 2, y + 7, x + size - 2, y + 7), fill=color)
        return
    if icon_key == "ssh":
        draw.ellipse((x, y + 3, x + 5, y + 8), fill=None, outline=color)
        draw.line((x + 5, y + 6, x + size, y + 6), fill=color, width=2)
        draw.line((x + size - 4, y + 6, x + size - 4, y + 10), fill=color)
        draw.line((x + size - 1, y + 6, x + size - 1, y + 9), fill=color)
        return
    if icon_key == "external":
        draw.rectangle((x, y + 4, x + size - 6, y + size), fill=None, outline=color)
        draw.line((x + size - 7, y + 2, x + size, y + 2), fill=text_color)
        draw.line((x + size, y + 2, x + size, y + 8), fill=text_color)
        draw.line((x + size - 8, y + 9, x + size, y + 2), fill=text_color, width=2)
        return
    if icon_key == "rdp":
        draw.rectangle((x, y + 2, x + size, y + size - 4), fill=None, outline=color)
        draw.line((x + 3, y + 6, x + size - 3, y + 6), fill=text_color)
        draw.line((x + size // 2, y + size - 4, x + size // 2, y + size), fill=color)
        draw.line((x + 3, y + size, x + size - 3, y + size), fill=color)
        return
    draw_text(draw, icon_key[:1].upper(), x, y - 2, text_color, 9, bold=True)


def draw_mremoteng_config_grid(draw: Any, preset: GuiDesignPreset, surface: Any, x: int, y: int, w: int, h: int) -> None:
    draw_mremoteng_property_grid(draw, preset, x, y, w, h)


def draw_mremoteng_property_grid(draw: Any, preset: GuiDesignPreset, x: int, y: int, w: int, h: int) -> None:
    c = preset.colors
    chrome = gui_design_mremoteng_property_grid_chrome()
    route = gui_design_mremoteng_connection_document_route()
    inheritance_route = gui_design_mremoteng_inheritance_route()
    route_rows = [row for row in chrome.rows if row.key == route.property_row_key]
    if len(route_rows) != 1 or route_rows[0].effective_value != route.property_value:
        raise RuntimeError("mRemoteNG connection-document route property row metadata drifted")
    inheritance_rows = [row for row in chrome.rows if row.key == inheritance_route.property_row_key]
    if len(inheritance_rows) != 1:
        raise RuntimeError("mRemoteNG inheritance route property row metadata drifted")
    inheritance_row = inheritance_rows[0]
    if (
        inheritance_row.property_label != inheritance_route.inherited_property_label
        or inheritance_row.effective_value != inheritance_route.inherited_value
        or inheritance_row.source != inheritance_route.inherited_source
        or not inheritance_row.inherited
    ):
        raise RuntimeError("mRemoteNG inheritance route inherited-row metadata drifted")
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
        row_outline = (
            c.status
            if row.key == inheritance_route.property_row_key
            else c.primary
            if row.key == route.property_row_key
            else c.pane_border
        )
        draw.rectangle((table_x, ry, x + w - 10, ry + row_h), fill=fill, outline=row_outline)
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
        draw_text(draw, chrome.notice, x + chrome.notice_x, y + chrome.notice_y, c.control_text, chrome.text_font_size, bold=True)
        draw_text(
            draw,
            f" - {chrome.product_note}",
            x + chrome.product_note_x,
            y + chrome.product_note_y,
            c.sidebar_muted,
            chrome.text_font_size,
        )
        draw_status_segments(
            draw,
            tuple(segment.text for segment in gui_design_moba_status_segments()),
            x + w - chrome.segment_start_right_offset,
            y,
            c,
        )
        draw_moba_bottom_edge_controls(draw, y + 3, c)
        marker_right = x + w - chrome.marker_right_inset
        marker_left = marker_right - chrome.marker_width
        marker_top = y + chrome.marker_y
        draw.rectangle(
            (marker_left, marker_top, marker_right, marker_top + chrome.marker_height),
            outline=c.sidebar_muted,
        )
        return
    draw_text(draw, preset.description, x + 14, y + 6, c.sidebar_muted, 10)
    draw_status_segments(draw, segments, x + w - 430, y, c)


def draw_status_segments(draw: Any, segments: tuple[str, ...], x: int, y: int, c) -> None:
    segment_x = x
    for text in segments:
        draw.line((segment_x - 8, y + 4, segment_x - 8, y + 20), fill=c.toolbar_border)
        draw_text(draw, text, segment_x, y + 6, c.sidebar_muted, 10)
        segment_x += max(116, len(text) * 7 + 20)


def draw_moba_bottom_edge_controls(draw: Any, y: int, c: Any) -> None:
    for action in gui_design_moba_bottom_edge_controls():
        draw_moba_bottom_edge_icon(draw, action.icon_key, action.static_x, y, 14, action.color, c)


def draw_moba_bottom_edge_icon(draw: Any, icon_key: str, x: int, y: int, size: int, color: str, c: Any) -> None:
    draw.rectangle((x - 2, y, x + size + 2, y + size + 2), outline=c.toolbar_border)
    mid_y = y + size // 2 + 1
    if icon_key == "arrow-left":
        draw.line((x + size - 2, y + 4, x + 5, mid_y), fill=color, width=2)
        draw.line((x + 5, mid_y, x + size - 2, y + size - 2), fill=color, width=2)
        draw.line((x + 5, mid_y, x + size, mid_y), fill=color, width=2)
        return
    if icon_key == "arrow-right":
        draw.line((x + 2, y + 4, x + size - 5, mid_y), fill=color, width=2)
        draw.line((x + size - 5, mid_y, x + 2, y + size - 2), fill=color, width=2)
        draw.line((x, mid_y, x + size - 5, mid_y), fill=color, width=2)
        return
    if icon_key == "close":
        draw.line((x + 4, y + 4, x + size - 4, y + size - 4), fill=color, width=2)
        draw.line((x + size - 4, y + 4, x + 4, y + size - 4), fill=color, width=2)
        return
    draw.rectangle((x + 3, y + 3, x + size - 3, y + size - 3), outline=c.control_hover)


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

# GUI Design Presets

The desktop shell exposes six view presets: Native, MobaXterm-style,
SecureCRT-style, Termius-style, Remmina-style and mRemoteNG-style.

The presets are intentionally not exact product clones. They keep the same
operator workflow while changing density, sidebar width, tab placement,
terminal contrast, toolbar treatment and log area height so each option feels
like a real working surface instead of a recolored screenshot.

Preset definitions live in `src/remote_ops_workspace/gui_designs.py`. The PyQt6
window applies the selected preset to toolbar icon sizing, profile-list spacing,
document tab behavior, split-pane sizing and the stylesheet hooks for primary
actions, terminal panes, the profile tree and the activity log.

Static previews can be regenerated without launching PyQt6:

```bash
python scripts/render_gui_design_previews.py
```

The command writes per-preset PNGs, a contact sheet, a deterministic manifest
and a local HTML gallery to `artifacts/gui-design-previews/`:

- `artifacts/gui-design-previews/index.html` is the easiest Windows-side gallery
  view for comparing every preset.
- `artifacts/gui-design-previews/all-gui-designs-contact-sheet.png` is the
  single-image overview.
- `artifacts/gui-design-previews/preview-manifest.json` records the expected
  preset order, image dimensions, file sizes and SHA-256 hashes.

Useful renderer commands:

```bash
python scripts/render_gui_design_previews.py --list
python scripts/render_gui_design_previews.py --preset termius
python scripts/render_gui_design_previews.py --check
python scripts/check_gui_design_previews.py
```

`--check` re-renders in memory and reports stale generated outputs. The
standalone checker is lighter: it does not require Pillow, and verifies that the
tracked preview files, manifest and gallery are internally consistent with the
current preset inventory. These images are preview artifacts only; the actual
desktop UI still uses the PyQt6 preset metadata.

When PyQt6 is installed, `python scripts/check_optional_dependencies.py` creates
the real main window offscreen and applies every preset through the live design
selector. In dependency-light environments, the same check verifies that the GUI
factory fails closed with a clear install hint.

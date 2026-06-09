# GUI Design Presets

The desktop shell exposes six view presets: Native, MobaXterm-style,
SecureCRT-style, Termius-style, Remmina-style and mRemoteNG-style.

The product-style presets target 100% measured parity against the approved
reference dimensions for operator workflow, chrome, navigation, panes, tabs,
sidebars, toolbars, session trees, connected-session behavior, file/monitoring
panels, status bars, density, spacing and interaction states. They remain
independent implementations: no proprietary artwork, copied binaries or
user-specific sample data are used.

Preset definitions live in `src/remote_ops_workspace/gui_designs.py`. The PyQt6
window applies the selected preset to toolbar icon sizing, product-specific
toolbar action names, profile-list spacing, document tab behavior,
product-specific sidebar titles, split-pane sizing and the stylesheet hooks for
primary actions, terminal panes, the profile tree and the activity log. The
product-style sidebars use Session Manager, Hosts, Connection Profiles and
Connections labels where those labels better match the selected workflow. The
same shared preset metadata feeds the live PyQt toolbar and the static preview
renderer so SecureCRT-style, Termius-style, Remmina-style and mRemoteNG-style
chrome uses product-appropriate action vocabulary. Status-bar segments are
shared the same way, keeping live and rendered evidence aligned for SSH/session,
vault/sync, remote-desktop scaling, clipboard and connection-tree state. The
session tree uses shared root and row metadata too: MobaXterm keeps compact user
sessions, SecureCRT uses a Session Database, Termius uses a Personal Vault,
Remmina groups profiles by protocol family, and mRemoteNG renders nested
connection containers. The static preview sidebar renderer also draws
independent protocol and workflow glyphs for those product-style trees, so the
Session Manager, Hosts, Connection Profiles and Connections panes are not
text-only placeholders. Tab labels and tab sublabels are also shared metadata:
SecureCRT separates SSH2/SFTP/local/start tabs, Termius uses a west host/file/
vault rail, Remmina uses viewer protocol tabs, and mRemoteNG uses document-style
connection tabs. Central workspace surfaces now share metadata as well:
SecureCRT renders a terminal-first Session Manager surface with SFTP detail,
an explicit command-window strip for send-to-session workflows, Termius renders
host/vault/snippet state with vault identity, port-forward and snippet workflow
cards, Remmina renders a remote-desktop viewer with scaling, clipboard,
fullscreen and screenshot control glyphs plus connection-state cards, and
mRemoteNG renders document tabs with SSH/RDP panes, a document toolbar and
grid-like config/inheritance state. The PyQt6 home tab rebuilds
from the same metadata when the selected preset changes, so start-page actions,
search placeholders, recent items, product workflow evidence cards and the
primary/secondary workspace surface follow the active product workflow. The
live render checker requires the workflow-card strip, verifies the expected card
titles for every preset and checks the workspace-surface text from the shared
metadata, keeping the real PyQt window aligned with the static preview evidence.
Interaction-state metadata is shared too: each product preset defines an active
toolbar/ribbon action, a checked action, a guarded disabled-looking action, the
focused search/quick-connect control, the active tab state and the selected tree
row. The live GUI applies those values through `interactionState` widget
properties while the static renderer draws the same focused, checked, disabled
and active affordances.
For SecureCRT-style, Termius-style, Remmina-style and mRemoteNG-style, shared
reference-state metadata also ties the active profile, target, protocol, tab,
sidebar identity, workspace state and status segments together. The static
preview draws those values as compact reference-state chips, while the live PyQt
home surface exposes matching `productReferenceStateItem` labels with stable
`referenceKey` properties for the live render checker.
The MobaXterm-style home welcome surface intentionally follows a separate,
leaner contract: `gui_design_moba_home_welcome_chrome()` defines the centered
title/subtitle, generated logo key, Start/Recover action icon keys, fixed
search width and recent-session title, while the live PyQt Home tab exposes
`mobaHomeWelcomeSurface`, `mobaHomeTitle`, `homeSearch` and
`mobaRecentSession` widgets with stable metadata. The static gallery also
tracks `mobaxterm-home.png` as a dedicated `state_previews` entry, keeping the
Home/welcome reference state visible without replacing the connected
SFTP/monitoring `mobaxterm.png` evidence. Static visual metrics measure this
home-state preview separately, including the Quick Connect strip, session tree,
centered action/search/recent-session surface and bottom status edge. Moba keeps
the workflow evidence in the connected SFTP/monitoring tab instead of showing
generic product cards on the reference Home screen.
SecureCRT-style Command Window chrome is tracked the same way: title, helper
copy, target scope, command input, send action and status live in shared
metadata, the static preview draws them, the PyQt home surface exposes stable
`secureCrtCommandWindow`/`secureCrtCommandWindowKey` evidence, and CI verifies
that the PNG still contains a measured command-input strip.
The SecureCRT-style session status strip is shared metadata too. Session,
target, protocol, cipher, attached SFTP tab, log file and connected state are
defined once, drawn above the terminal panes in the static preview, exposed as
live `secureCrtSessionStatusStrip`/`secureCrtSessionStatusKey` evidence and
checked in the render manifest without using user-specific endpoints.
SecureCRT-style Session Manager filter/action chrome is also shared metadata.
The filter placeholder and Connect, New Folder and Properties actions are drawn
in the static sidebar, exposed as live `secureCrtSessionManagerChrome` actions
plus the focused `secureCrtSessionFilter`, and checked in CI as required
Session Manager navigation evidence.
The static SecureCRT Session Manager tree now has a dedicated renderer for the
Session Database root, foldered Sessions/Local Shells/Pinned groups, selected
SSH2 row and connector lines. Visual metrics pin those regions and color
anchors so the left pane cannot drift back to a generic flat profile list.
The same tree now carries shared row-icon metadata for the database root, folder
groups, SSH2 sessions, SFTP sessions, shell/command rows and pinned sessions.
The live `profileTree` stores each row's icon key, row kind, static icon size and
`generated-pixmap` render source, and CI rejects SecureCRT rows that fall back to
text-only or platform-default glyph evidence.
The same generated-tree-glyph contract now covers Termius, Remmina and
mRemoteNG: Termius host/vault/snippet rows, Remmina RDP/VNC/SFTP protocol rows
and mRemoteNG Connections.xml/container/protocol nodes all use shared icon
metadata in the static renderer and live `profileTree` evidence.
SecureCRT interaction-state visual metrics now pin those same controls in the
generated PNG: the focused Session Manager filter outline, active SSH2 tab
outline, command-window input focus outline and Send control fill are sampled as
regions, color anchors, line anchors and topology relationships.
SecureCRT-style top menu and toolbar chrome is shared metadata as well. File,
Edit, View, Options, Transfer, Script, Tools, Window and Help menus are exposed
through live `secureCrtTopMenuKey` actions, while icon-keyed session toolbar
actions expose `secureCrtTopToolbarIconKey` and static sizing metadata so the
static preview and real PyQt window no longer reuse the generic top bar.
Remmina-style viewer control chrome now has shared metadata too. Fit,
Scale 100%, Clipboard, Fullscreen and Screenshot are drawn in the static
viewer toolbar and exposed as live `remminaViewerControl` buttons with stable
control keys, generated icon keys, static strip widths/offsets and live button
sizing. The live checker validates `remminaViewerControlStaticWidth`,
`remminaViewerControlLiveButtonHeight` and
`remminaViewerControlRenderSource`, while the visual metrics pin the
control-strip region.
Remmina-style profile-list chrome is shared metadata as well. The connection
list title, filter placeholder, Name/Protocol/Server columns and generic
RDP/VNC/SFTP rows are drawn in the static sidebar, exposed as live
`remminaProfileListChrome`/`remminaProfileRowKey` evidence and checked in the
render manifest.
Remmina interaction-state visual metrics now pin the focused profile filter,
selected connection-list row, selected protocol-tree row, active RDP viewer tab,
checked Transfer toolbar action and viewer-control glyph cluster. The live
interaction checker also expects the focused state on `remminaProfileFilter`
rather than the generic toolbar search.
Termius-style Hosts sidebar chrome is shared metadata: the Hosts title, Search
hosts field, Add Host, Keychain and Sync actions are drawn in the static
sidebar, exposed as live `termiusHostsChrome`/`termiusHostSearch` widgets with
stable action and icon keys, and checked so host-search focus belongs to the
sidebar rather than the generic toolbar.
Termius-style host header chips are also shared metadata: Vault unlocked,
Sync current and Port fwd ready are rendered in the static host header,
exposed as live `termiusHeaderChip` labels with stable chip keys and pinned by
the static visual metrics.
Termius-style host identity strip is shared metadata too. Host, vault
identity, jump chain, SFTP file state, port-forward, snippet and sync status
are drawn above the terminal/detail panes, exposed as live
`termiusHostIdentityStrip`/`termiusHostIdentityKey` evidence and checked in the
render manifest with generic host and key labels.
Termius interaction-state visual metrics also pin the focused Hosts search
outline, selected vault host row, active west host tab, checked Vault toolbar
button, identity-strip Sync control and workflow-card action row as measured
regions, color anchors, line anchors and topology contracts.
mRemoteNG-style document controls now use shared metadata for the
Connections.xml title, Save, Reconnect, External tool and Dock view actions,
plus the connection-tree filter placeholder. The static document toolbar and
live PyQt `mRemoteNgDocumentControl` buttons expose the same keys, and visual
metrics pin the document-control button strip. The mRemoteNG-style document-control geometry
contract also pins generated icon rendering, button widths, icon offsets, label
offsets, filter width and live button dimensions through the shared metadata
and real-GUI checker. mRemoteNG interaction-state
metrics now pin the focused `mRemoteNgDocumentFilter`, selected connection-tree
row, active document tab, checked External tool actions, guarded Delete toolbar
button, embedded RDP control glyphs and inherited property-grid rows.
mRemoteNG-style top menu and toolbar chrome is shared metadata too. File,
View, Connections, Tools, Window and Help menus expose stable
`mRemoteNgTopMenuKey` values, while top toolbar buttons expose
`mRemoteNgTopToolbarIconKey`, static position and static width metadata for
Refresh, New Conn, Config, Delete, Open, External, Transfer, Script, Tools and
Tile controls. The static preview and live PyQt menu bar are checked from the
same source.
mRemoteNG-style property grid chrome is also shared metadata. The Config /
Inheritance title, active document scope, Property/Inherited/Effective value/
Source columns, inherited row state and generic effective values are drawn in
the static config table, exposed as live `mRemoteNgPropertyGrid` and
`mRemoteNgPropertyRowKey` evidence, and checked in the render manifest.

The MobaXterm-style preset also has a connected-session tab for SSH/SFTP
profiles. In that mode the live left dock switches from the saved-session tree
to an SFTP file browser with remote path toolbar, follow-terminal-folder
checkbox and remote monitoring, while `gui.MobaConnectedSessionPanel` keeps the
SSH connection banner, terminal pane and bottom telemetry strip. Its state and
executable SSH/SFTP plans live in `src/remote_ops_workspace/moba_connected.py`.
The static and live MobaXterm-style ribbons share action metadata and use drawn
pictograms for the main actions instead of placeholder letters or copied product
artwork. The live render checker verifies the `mobaIconKey` widget properties
and non-null generated icons in the dedicated PyQt6 CI job.
The top titlebar is shared Moba-style chrome too. `GuiMobaTitlebarChrome`
defines the generated app mark, compact control order and title offsets; the
static preview draws those pieces, while the live PyQt window exposes
`mobaTitlebarTitle`, `mobaTitlebarIconKey` and `mobaTitlebarControlKeys` tied to
the active connected-session title.
The top menu row is shared metadata as well: Terminal, Sessions, View, X server,
Tools, Games, Settings, Macros and Help are generated from
`GuiMobaTopMenuItem` records in both the static preview and live PyQt menu bar.
The live checker validates `mobaTopMenuKey` and `mobaTopMenuLabel` order, while
the static visual metrics pin the top-menu strip.
The connected left rail also shares section metadata for the Sessions, Tools,
Macros and SFTP vertical labels; the static preview renders those labels
rotated in the narrow rail, while the live PyQt rail exposes matching
`mobaRailLabel` widgets for the render contract.
The connected SFTP preview also uses drawn toolbar, file, folder and monitoring
glyphs rather than bracketed text placeholders, while the live SFTP dock keeps
icon-bearing action buttons and file rows.
MobaXterm-style connected visual metrics now pin the smaller reference details
that make the screen feel native to the target workflow: titlebar window
controls, right-side X server/Exit ribbon actions, the session-edge shortcut
cluster, SFTP toolbar action strip, dense file row, compact monitoring and
follow-folder rows, right utility stack, CPU telemetry cell and bottom-edge
navigation controls.
Connected MobaXterm-style mode now checks the SFTP rail item when the left dock
is the active SFTP browser, and the static preview uses a generic home-directory
listing with selected/striped rows instead of an application log demo table.
The SFTP dock chrome is also shared metadata now: the static preview and live
PyQt dock use the same parent/download/upload/reconnect/new-folder/new-file/
delete/ASCII/split/tools/terminal action order, generated icon keys, remote
path strip, file-table columns, monitoring metric keys and
follow-terminal-folder state. The live render checker verifies those
`mobaSftpActionKey`, `mobaSftpIconKey` and `mobaMonitoringMetricKey` properties,
while the static visual metrics pin the monitoring dock region and divider.
The toolbar actions also carry `group_key` and `separator_after` metadata for
navigation, transfer, manage, mode and terminal groups. The static preview draws
the separator marks, while the live PyQt toolbar exposes
`mobaSftpActionGroupKey`, `mobaSftpToolbarSeparator` and
`mobaSftpSeparatorAfterActionKey` for the render checker.
The dock density is shared metadata too. `GuiMobaSftpDockLayout` defines the
compact inner margin, toolbar height, path row height, table-header height, file
row height, maximum static rows, monitoring panel height and divider offset.
The static renderer uses those values for the left-dock stack, the live PyQt
dock exposes matching `mobaSftpDockInnerMargin`, `mobaSftpToolbarHeight`,
`mobaSftpRowHeight` and `mobaSftpMonitoringHeight` properties, and the visual
metrics pin the SFTP toolbar/path/header rules.
The SFTP browser path and table header chrome are tracked as their own shared
metadata too. `GuiMobaSftpBrowserChrome` defines the path placeholder, dropdown
marker, selected `..` parent-folder row and keyed Name/Size/Last modified
columns with fixed reference widths; the static preview uses the same column
offsets and selected parent row as the live PyQt file table exposes through
`mobaSftpColumnKeys`, `mobaSftpColumnWidths`, `mobaSftpParentRowKind` and
`mobaSftpSelectedRowKind`. The live checker rejects auto-sized column drift, and
the visual metrics pin the path/header strip plus the selected parent-row fill
and outline so the dock cannot drift back to an unselected generic file list.
SFTP file-row glyphs now use shared generated metadata too:
`GuiMobaSftpFileRowIcon` defines parent-folder, folder and file icons with
stable icon keys, row kinds, sizes and `generated-pixmap` render evidence. The
static preview draws those icons through `draw_moba_sftp_file_icon`, while the
live PyQt `mobaSftpFileTable` stores matching row roles and rejects fallback to
platform-default folder/file icons in the real GUI checker.
The remote-monitoring controls are tracked separately as shared metadata too:
Remote monitoring and Follow terminal folder now expose stable keys, icon keys,
control types, checked state, tooltips and compact dock geometry in both the
static PNG renderer and the live PyQt dock. `GuiMobaMonitoringControlGeometry`
defines each control's reference anchor, y offset, icon size, label offset,
checkbox size and row height; the live checker validates
`mobaMonitoringControlStaticX`, `mobaMonitoringControlIconSize` and the related
geometry properties, and the visual metrics pin the bottom-left
monitoring-controls region.
The connected left dock also has a compact MobaXterm-style remote-monitoring dock
contract. `GuiMobaRemoteMonitoringDockChrome` keeps the visible dock to the
reference-like Remote monitoring control plus Follow terminal folder checkbox,
while telemetry metric keys, refresh cadence, SSH monitoring command evidence
and follow-folder SFTP plan evidence are exposed as `mobaRemoteMonitoring*`
properties. The compact dock additionally exposes
`mobaMonitoringControlGeometryKeys` so static previews, live PyQt controls and
the render manifest report the same Moba-style monitoring row geometry instead
of drifting independently.
Connected MobaXterm-style chrome now uses a shared SSH/SFTP state model for the
window title, active tab label and bottom telemetry segments, so the static
preview and live PyQt window show the same target-centric example identity and
icon-backed CPU, memory, disk, network, connection and process indicators.
Those indicators now use a shared bottom telemetry cell model instead of loose
labels: `moba_telemetry_cells()` defines the ordered cell keys, icon keys,
project-owned icon accents, icon size, display text and widths; the static
preview draws separator lines and reference-like cells; and the live PyQt bar
uses generated pixmap glyphs exposed through `mobaTelemetryIconRender`,
`mobaTelemetryCellWidth` and `mobaTelemetryDisplayText` for the render checker,
which rejects text-placeholder telemetry icons.
The SSH banner chrome has its own shared title, subtitle, target-line,
capability-row, footer-link and geometry metadata; the static renderer uses it
for the centered banner header and terminal spacing, while the live PyQt banner
exposes `mobaSshBannerTitle`, `mobaSshBannerSubtitle`, `mobaBannerWidth`,
`mobaSshBannerTargetLine`, `mobaSshBannerCapabilityKey` and
`mobaSshBannerFooter` properties for the render contract. The MobaXterm-style SSH banner capability card is now checked as keyed rows for Direct SSH, SSH
compression, SSH-browser and X11-forwarding status, plus the help/website footer
links, so static and live evidence cannot drift independently.
The connected terminal transcript is shared state too. `moba_connected.py`
builds keyed transcript lines for the web-console URL, last-login notice and
ready shell prompt from the generic reference profile; the static preview
renders `state.terminal_transcript`, while the live terminal output exposes
`mobaTerminalTranscriptKeys` and `mobaTerminalTranscriptTones` for the render
checker.
The connected tab strip is also state-driven: the static preview renders home,
inactive SSH, active SSH and plus tabs with generated icons and close markers,
while the live PyQt tabs expose matching `mobaTabChromeKey` and
`mobaTabIconKey` properties for the render checker.
The connected terminal workspace also includes a right utility rail backed by
shared action metadata; the static preview draws clip/settings/tool icons from
shared right-edge stack coordinates instead of text placeholders, and the live
PyQt panel exposes `mobaRightUtilityAction` widgets with stable
`mobaRightUtilityKey`, `mobaRightUtilityIconKey`,
`mobaRightUtilityStaticY`, `mobaRightUtilityButtonSize` and
`mobaRightUtilityRenderSource` properties.
The small session edge shortcut cluster beside the connected tab/terminal edge
is tracked separately with `gui_design_moba_session_edge_actions()`: static
previews draw the paperclip/settings icons from shared `static_y` coordinates,
and the live rail exposes `mobaSessionEdgeControls` plus
`mobaSessionEdgeAction` buttons with `mobaSessionEdgeKey` and
`mobaSessionEdgeIconKey` properties.
The bottom status bar has shared Moba-style chrome metadata too. Static and live
evidence use project-owned notice text, a compact product note, keyed SFTP/CPU/
SSH-browser workflow segments and a right-side marker instead of copying
proprietary status wording. The live PyQt status labels expose
`productStatusNotice`, `productStatusMarker` and `productStatusKey` properties,
and static visual metrics measure the status-notice region.
The MobaXterm-style bottom-edge navigation controls are shared metadata as well:
`gui_design_moba_bottom_edge_controls()` defines previous-tab, next-tab and
close-active actions with generated arrow/close glyphs. Static previews draw the
same controls at the bottom-right status edge, while the live PyQt status bar
exposes `mobaBottomEdgeControls` and `mobaBottomEdgeControl` buttons with stable
`mobaBottomEdgeKey` and `mobaBottomEdgeIconKey` properties.
The MobaXterm-style Quick Connect top strip is also shared metadata:
`gui_design_moba_quick_connect_chrome()` defines the placeholder, dropdown
marker, fixed strip height and input padding. Static previews draw the same
focused strip above the left dock, while the live PyQt UI exposes
`mobaQuickConnectChrome`, `quickConnect` and `mobaQuickConnectDropdown` with
stable metadata properties.
The MobaXterm-style Quick Connect suggestion dropdown is tracked separately:
`gui_design_moba_quick_connect_suggestion_chrome()` defines the preview query,
expected saved-profile/direct-target candidate kinds, row height, visible-row
limit and detail separator. Static previews draw the opened dropdown with
generic `edge-prod.example.invalid` evidence, while the live PyQt UI exposes
`quickConnectSuggestions`, `mobaQuickConnectSuggestionKinds`,
`mobaQuickConnectSuggestionLabels` and `mobaQuickConnectSuggestionDetails` for
the render checker.
The connected Quick Connect idle state is now tracked independently from the
typed dropdown. The connected MobaXterm-style reference starts with the
placeholder-only `Quick connect...` strip and hidden suggestions so the SFTP
toolbar, path row, file browser and compact monitoring controls are visible
immediately, matching the connected reference view. Typing the generic preview
query still opens the saved-profile/direct-target suggestion evidence and is
checked as a separate interaction state.
The Termius-style renderer follows its west-tab preset metadata with vertical
session tabs in the generated preview.

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
  preset order, additional `state_previews` such as `mobaxterm-home.png`, image
  dimensions, file sizes and SHA-256 hashes.

Product-style parity is tracked separately from image freshness in
`configs/gui_parity_criteria.json`. Run `python scripts/check_gui_parity.py` to
verify that the MobaXterm-style, SecureCRT-style, Termius-style, Remmina-style
and mRemoteNG-style presets each have explicit reference-basis notes and
source-backed layout/workflow evidence. The same JSON also maps every required
dimension to concrete requirement IDs for each product preset, so a preset only
passes 100% when both requirement coverage and dimension coverage are complete.
The checker prints overall GUI parity coverage, overall dimension coverage and
per-preset percentages, then fails if any row is below the configured 100%
target. `python scripts/check_gui_parity.py --json` emits the same audit as
structured JSON for release evidence. Each parity requirement must be backed by
at least two repository evidence files, so a lone metadata token or renderer
token cannot satisfy a product-style claim by itself. Each requirement must also
include evidence outside the package implementation tree, such as a renderer,
checker, config, doc or test file, so pure `src/remote_ops_workspace` claims do
not pass the parity gate. The checker intentionally tracks independent
resemblance and workflow coverage; it does not use proprietary assets or
personal sample data. It also scans the GUI parity evidence files, including the
visual metrics config, GUI docs, static renderer and visual/live checker scripts,
for prohibited user-specific sample tokens.

Static visual metrics live in `configs/gui_visual_metrics.json`. Run
`python scripts/check_gui_visual_metrics.py` to sample the generated preview PNGs
with the standard library and verify that each major region has the expected
brightness band and nonblank visual complexity. The checker covers both primary
preset screenshots and manifest `state_previews`, so `mobaxterm-home.png` is
measured separately from the connected MobaXterm-style state. Product-style
previews also define color anchors for reference landmarks such as accent
toolbar actions, active tabs, tree identity glyphs, workflow cards, monitoring
accents and viewer panes. Product-style previews also define line anchors for
structural boundaries such as toolbar baselines, sidebar/workspace dividers, tab
edges, viewer frames, workflow surfaces, activity/log separators, telemetry and
status-bar rules. This catches geometry drift that would still pass broad region
sampling. Product-style previews also define topology contracts between named
regions, such as left-dock before terminal, tab rail before workspace, viewer
controls above viewer and log panes below document surfaces. These relationships
catch stale, collapsed or structurally reordered layouts that still have correct
source tokens.

Useful renderer commands:

```bash
python scripts/render_gui_design_previews.py --list
python scripts/render_gui_design_previews.py --preset termius
python scripts/render_gui_design_previews.py --check
python scripts/check_gui_design_previews.py
python scripts/check_gui_visual_metrics.py
python scripts/check_gui_parity.py
python scripts/check_gui_parity.py --json
python scripts/check_real_gui_render.py
python scripts/check_real_gui_render.py --out-dir artifacts/gui-real
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

`python scripts/check_real_gui_render.py` is the live screenshot contract. With
the desktop extra installed it opens the real PyQt6 main window offscreen,
switches through the selected presets, checks the expected controls are visible,
verifies preset-specific tabs, side panel copy, toolbar/ribbon labels, status
segments, interaction states, live layout geometry contracts, live widget
topology contracts and product-specific tab/session-tree content labels, then
rejects blank or placeholder captures by sampling screenshot pixels. For the
MobaXterm-style preset the live checker opens the bundled `edge-prod` demo profile
into a connected reference tab before capture, so the SFTP/monitoring dock,
SSH banner and bottom telemetry strip are verified in the real PyQt window.
For the other product-style presets, the checker opens a representative example
profile tab and returns to the home tab so the tab strip, sidebar tree, workflow
evidence and product-specific workspace surface are all present in one live
contract.
Passing
`--out-dir artifacts/gui-real` writes per-preset live PNGs plus
`real-gui-render-manifest.json`; the manifest records the selected preset ids,
captured preset ids, expected and actual capture counts, and whether the capture
set is complete. It also records a per-preset live contract summary with
required widgets, present-widget expectations, layout contract ids, topology
contract ids and widget pairs, reference profile/tab labels, expected tree
labels, workflow card titles, status segments and workspace surface text
expectations. Each successful capture also stores measured contract evidence:
live widget bounds for layout contracts plus topology gaps, containment or
overlap values for widget-to-widget relationships. The manifest audits that
measured evidence with top-level complete, missing, incomplete and failed preset
lists, and the live capture gate fails if any product preset lacks a full passing
measurement set. These captures are diagnostic outputs and are not the same as
the tracked static preview gallery. Without PyQt6, the checker does not fake
screenshots: it verifies that the GUI factory raises the expected dependency
error unless `--require-pyqt6` is used.

CI enforces both paths. The normal matrix runs `python scripts/verify.py --lint`,
which includes the fail-closed render smoke in dependency-light jobs. A
dedicated `gui-render` job installs the desktop extra and runs
`python scripts/check_real_gui_render.py --require-pyqt6 --out-dir
artifacts/gui-real`, then uploads the captured PNG manifest as a workflow
artifact. Because no `--preset` filter is passed, that job captures Native,
MobaXterm-style, SecureCRT-style, Termius-style, Remmina-style and
mRemoteNG-style in one all-preset gate.

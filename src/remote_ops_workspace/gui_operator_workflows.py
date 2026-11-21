from __future__ import annotations

from typing import TYPE_CHECKING

from .gui_designs import get_gui_design_preset
from .moba_multiexec import DEFAULT_MOBA_MULTIEXEC_COMMAND, build_moba_multiexec_plan
from .moba_servers import build_moba_server_gui_config_surface
from .moba_smartcards import MobaSmartCardCertificate, build_smartcard_management_gui_surface
from .smartcard_keys import PINNED_SMARTCARD_KEY

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from PyQt6.QtWidgets import QStatusBar

    from .gui_dialogs import WorkflowDialog
    from .layouts import LayoutStore
    from .models import Profile
    from .storage import ProfileStore


class OperatorWorkflows:
    """Present operator workflow status and link to the workspace actions."""

    if TYPE_CHECKING:
        layout_store: LayoutStore
        store: ProfileStore

        def connect_selected(self, dry_run: bool) -> None: ...
        def create_layout(self) -> None: ...
        def create_profile(self) -> None: ...
        def create_workflow_dialog(
            self,
            title: str,
            subtitle: str,
            rows: list[tuple[str, str, str]],
            detail: str,
            *,
            actions: Sequence[tuple[str, Callable[..., object]]] | None = None,
        ) -> WorkflowDialog: ...
        def current_design_id(self) -> str: ...
        def cycle_design_preset(self, *_args) -> None: ...
        def edit_selected_profile(self) -> None: ...
        def open_files_selected(self) -> None: ...
        def open_local_terminal_tab(self) -> None: ...
        def open_moba_pkcs11_inventory(self, provider: str, profile: Profile | None) -> None: ...
        def open_transfer_queue_selected(self) -> None: ...
        def selected_profile_for_workflow(self) -> Profile | None: ...
        def set_moba_rail_active(self, active: str) -> None: ...
        def setProperty(self, name: str, value: object) -> bool: ...
        def show_doctor(self) -> None: ...
        def statusBar(self) -> QStatusBar: ...

    def show_moba_session_attachment(self, *_args) -> None:
        self.show_workflow_dialog(
            "Session attachment",
            "Active-tab attachment helpers for the connected terminal.",
            [
                ("SFTP browser", "attached", "The left dock follows the active SSH session."),
                ("Transfer hints", "available", "Clipboard and file-transfer helper routes are ready."),
                ("Session context", "active tab", "Attachment shortcuts stay scoped to the selected terminal tab."),
            ],
            "\n".join(
                [
                    "Session-edge attachment workflow",
                    "Use the connected SFTP browser and helper actions without exposing personal paths.",
                    "The route is measured separately from the larger right utility rail.",
                ]
            ),
        )

    def show_moba_session_settings(self, *_args) -> None:
        self.show_workflow_dialog(
            "Session settings",
            "Active-tab terminal settings for the connected MobaXterm-style workspace.",
            [
                ("Terminal", "active", "Settings apply to the selected connected terminal tab."),
                ("SSH browser", "enabled", "The SFTP browser remains attached while settings are inspected."),
                ("X11 forwarding", "tracked", "The SSH banner keeps X11 status visible for the session."),
            ],
            "\n".join(
                [
                    "Session-edge settings workflow",
                    "Keep tab-local settings, SSH-browser state and terminal identity together.",
                    "Preview evidence stays generic and does not include user credentials.",
                ]
            ),
        )

    def show_moba_clipboard_hints(self, *_args) -> None:
        self.show_workflow_dialog(
            "Clipboard and transfer hints",
            "Clipboard, paste and transfer helper routes for the active terminal.",
            [
                ("Clipboard", "available", "Copy selected terminal text or paste into the active session."),
                ("SFTP browser", "attached", "Use the left file browser for transfer previews."),
                ("Follow folder", "checked", "Keep the file browser aligned with the terminal working directory."),
            ],
            "\n".join(
                [
                    "Right utility rail clipboard workflow",
                    "Use project-owned controls for copy/paste hints and transfer routing.",
                    "No captured clipboard content or user-specific data is stored in previews.",
                ]
            ),
        )

    def show_moba_terminal_settings(self, *_args) -> None:
        self.show_workflow_dialog(
            "Terminal settings",
            "Terminal appearance, interaction and session-edge settings for the active tab.",
            [
                ("Font", "monospace", "Reference terminal rows use fixed-width text geometry."),
                ("Session edge", "enabled", "Attachment and settings controls remain on the right edge."),
                ("Telemetry", "bottom strip", "Remote monitoring metrics stay routed to bottom status cells."),
            ],
            "\n".join(
                [
                    "Right utility rail settings workflow",
                    "Adjust terminal-facing view options without changing the active connection identity.",
                    "The route is measured separately from generic toolbar settings.",
                ]
            ),
        )

    def show_moba_servers_status(self, *_args) -> None:
        self.set_moba_rail_active("tools")
        surface = build_moba_server_gui_config_surface(selected_service="http")
        self.setProperty("mobaEmbeddedServerGuiConfigSchema", surface.schema)
        self.setProperty("mobaEmbeddedServerGuiConfigServices", [row.service for row in surface.rows])
        self.setProperty("mobaEmbeddedServerGuiConfigControls", list(surface.gui_controls))
        self.setProperty("mobaEmbeddedServerRuntimeRoots", list(surface.runtime_roots))
        self.setProperty("mobaEmbeddedServerPackagedServiceCount", surface.packaged_service_count)
        rows = [
            (
                row.label,
                row.status,
                f"port {row.default_port} runtime={row.selected_runtime} auth={'yes' if row.auth_required else 'no'}",
            )
            for row in surface.rows
        ]
        selected = surface.selected_config
        detail = "\n".join(
            [
                "Embedded server suite configuration",
                f"Schema: {surface.schema}",
                f"Selected: {selected.service} {selected.host}:{selected.port}",
                f"Hardening: {selected.hardening_profile}",
                f"Auth required: {'yes' if selected.auth_required else 'no'}",
                f"TLS required: {'yes' if selected.tls_required else 'no'}",
                f"Packaged daemon services: {surface.packaged_service_count}/{len(surface.rows)}",
                "GUI controls: " + ", ".join(surface.gui_controls),
                "",
                "Selected service commands:",
                next(row.config_action for row in surface.rows if row.service == surface.selected_service),
                next(row.start_action for row in surface.rows if row.service == surface.selected_service),
                next(row.stop_action for row in surface.rows if row.service == surface.selected_service),
            ]
        )
        self.show_workflow_dialog(
            "Servers",
            "MobaXterm-style local server suite status, hardening configuration and lifecycle actions.",
            rows,
            detail,
            actions=[("Run doctor", self.show_doctor), ("Tools", self.show_moba_tools_status)],
        )

    def show_moba_smartcards_status(self, *_args) -> None:
        self.set_moba_rail_active("tools")
        profile = self.selected_profile_for_workflow()
        certificates: list[MobaSmartCardCertificate] = []
        selected_id = ""
        provider = "microsoft-capi"
        add_to_mobagent = False
        if profile is not None:
            selected_id = str(profile.options.get("smartcard_certificate_id") or "")
            provider = str(profile.options.get("smartcard_provider") or profile.options.get("pkcs11_provider") or provider)
            add_to_mobagent = str(profile.options.get("add_smartcard_to_mobagent") or "").lower() == "true"
            if selected_id:
                certificates.append(
                    MobaSmartCardCertificate(
                        certificate_id=selected_id,
                        label=str(profile.options.get("smartcard_certificate_label") or selected_id),
                        provider=provider,
                        public_key=str(profile.options.get("smartcard_public_key") or ""),
                        fingerprint_sha256=str(profile.options.get("smartcard_fingerprint_sha256") or ""),
                        source="profile-options",
                    )
                )
        surface = build_smartcard_management_gui_surface(
            provider=provider,
            certificates=certificates,
            selected_certificate_id=selected_id,
            profile=(profile if profile is not None and selected_id and profile.protocol == "ssh"
                     and PINNED_SMARTCARD_KEY not in profile.options else None),
            add_to_mobagent=add_to_mobagent,
            force=True,
        )
        self.setProperty("mobaSmartcardGuiManagementSchema", surface.schema)
        self.setProperty("mobaSmartcardGuiProvider", surface.provider)
        self.setProperty("mobaSmartcardGuiCertificateCount", len(surface.certificate_rows))
        self.setProperty("mobaSmartcardGuiSelectedCertificateId", surface.selected_certificate_id)
        self.setProperty("mobaSmartcardGuiControls", list(surface.gui_controls))
        if surface.certificate_rows:
            rows = [
                (
                    row.label,
                    row.provider,
                    f"id={row.certificate_id} public-key={'yes' if row.public_key_available else 'no'}",
                )
                for row in surface.certificate_rows
            ]
        else:
            rows = [
                (
                    "Certificate inventory",
                    surface.provider,
                    "Open PKCS#11 inventory to read public keys from an installed provider.",
                )
            ]
        detail = "\n".join(
            [
                "Smart-card management",
                f"Schema: {surface.schema}",
                f"Provider: {surface.provider}",
                f"Selected profile: {profile.name if profile is not None else 'none'}",
                f"Selected certificate: {surface.selected_certificate_id}",
                "GUI controls: " + ", ".join(surface.gui_controls),
                "",
                "Command contracts:",
                *surface.commands,
            ]
        )
        self.show_workflow_dialog(
            "Smart cards",
            "MobaXterm 26.4-style certificate inventory, OpenSSH public-key export, SSH selection and MobAgent handoff.",
            rows,
            detail,
            actions=[
                ("PKCS#11 inventory", lambda: self.open_moba_pkcs11_inventory(surface.provider, profile)),
                ("Edit profile", self.edit_selected_profile),
                ("Run doctor", self.show_doctor),
            ],
        )

    def show_moba_games_status(self, *_args) -> None:
        self.show_workflow_dialog(
            "Games",
            "The compatibility skin exposes this reference entry without pretending to ship third-party games.",
            [
                (
                    "Bundled games",
                    "not included",
                    "Remote Ops Workspace does not download or execute game packages.",
                ),
                (
                    "Local terminal",
                    "available",
                    "Open a local terminal for ordinary operator workflows.",
                ),
                (
                    "Security",
                    "modern defaults kept",
                    "No legacy executable or network exception is enabled by this entry.",
                ),
            ],
            "Games is an intentionally unsupported compatibility entry.\n"
            "It opens this explicit status instead of silently routing to an unrelated tool.",
            actions=[
                ("New terminal", self.open_local_terminal_tab),
                ("Help", self.show_moba_help_dialog),
            ],
        )

    def show_moba_settings_status(self, *_args) -> None:
        preset = get_gui_design_preset(self.current_design_id())
        self.show_workflow_dialog(
            "Settings",
            "Workspace, profile, layout and diagnostics entry points.",
            [
                ("Interface style", preset.label, preset.description),
                (
                    "Profiles",
                    str(len(self.store.load())),
                    "Edit the selected connection profile.",
                ),
                (
                    "Layouts",
                    str(len(self.layout_store.load())),
                    "Create or edit saved multi-pane layouts.",
                ),
                (
                    "Security",
                    "defaults enforced",
                    "Legacy protocol use still requires explicit opt-in.",
                ),
            ],
            "Settings routes to real editable workspace objects.\n"
            "Use View to cycle the compatibility skin without weakening runtime security defaults.",
            actions=[
                ("Edit profile", self.edit_selected_profile),
                ("New layout", self.create_layout),
                ("Next interface style", self.cycle_design_preset),
                ("Run doctor", self.show_doctor),
            ],
        )

    def show_securecrt_script_status(self, *_args) -> None:
        profile = self.selected_profile_for_workflow()
        self.show_workflow_dialog(
            "Run Script",
            "SecureCRT-style script entry point with an explicit capability boundary.",
            [
                (
                    "Selected session",
                    profile.name if profile is not None else "none",
                    "Select a profile before preparing a session-scoped command.",
                ),
                (
                    "Script editor",
                    "not bundled",
                    "Use terminal input or macro capture; arbitrary script execution is not implied.",
                ),
                (
                    "Dry run",
                    "available",
                    "Preview the selected profile launch without connecting.",
                ),
            ],
            "This entry does not silently launch a connection.\n"
            "It exposes the supported macro and dry-run workflows and keeps execution explicit.",
            actions=[
                ("Dry run selected", lambda: self.connect_selected(True)),
                ("Macros", self.show_moba_macros_status),
            ],
        )

    def show_key_manager_status(self, *_args) -> None:
        profile = self.selected_profile_for_workflow()
        identity = (
            profile.identity_file
            if profile is not None and profile.identity_file
            else "not configured"
        )
        credential = (
            profile.credential_ref
            if profile is not None and profile.credential_ref
            else "not configured"
        )
        self.show_workflow_dialog(
            "Key Manager",
            "Identity and credential references for the selected session.",
            [
                (
                    "Selected session",
                    profile.name if profile is not None else "none",
                    "Select a profile to edit keys.",
                ),
                (
                    "Identity file",
                    identity,
                    "Private key material is referenced, never displayed here.",
                ),
                (
                    "Credential reference",
                    credential,
                    "Secrets remain in the configured credential provider.",
                ),
            ],
            "Key operations route to the profile editor and diagnostics.\n"
            "No private key contents are copied into the activity log.",
            actions=[
                ("Edit profile", self.edit_selected_profile),
                ("Run doctor", self.show_doctor),
            ],
        )

    def show_external_tools_status(self, *_args) -> None:
        self.show_workflow_dialog(
            "External Tools",
            "mRemoteNG-style entry point for supported local tools and diagnostics.",
            [
                ("Local terminal", "available", "Launch the platform default shell."),
                (
                    "Protocol diagnostics",
                    "available",
                    "Run doctor against installed native clients.",
                ),
                (
                    "Third-party executables",
                    "not auto-installed",
                    "Profiles retain explicit commands and security policy.",
                ),
            ],
            "External tools are opt-in and never downloaded or executed implicitly.",
            actions=[
                ("New terminal", self.open_local_terminal_tab),
                ("Run doctor", self.show_doctor),
            ],
        )

    def show_moba_tools_status(self, *_args) -> None:
        self.set_moba_rail_active("tools")
        profiles = self.store.load()
        self.show_workflow_dialog(
            "Tools",
            "Operational tools for profiles, transfers, diagnostics and saved layouts.",
            [
                ("Profile editor", f"{len(profiles)} saved", "Create, edit or remove connection profiles."),
                ("Transfer queue", "available", "Preview SFTP get, put, mkdir and delete operations."),
                ("Embedded servers", "configurable", "Inspect local daemons, hardening and start/stop commands."),
                ("Smart cards", "manageable", "Inventory certificates, export public keys and configure MobAgent handoff."),
                ("Layouts", f"{len(self.layout_store.load())} saved", "Open grid, horizontal or vertical multi-pane layouts."),
                ("Doctor", "available", "Inspect local protocol clients and launch readiness."),
            ],
            "\n".join(
                [
                    "Tools workflow",
                    f"Profiles: {len(profiles)}",
                    f"Layouts: {len(self.layout_store.load())}",
                    "Use the action buttons below to open the most common tools.",
                ]
            ),
            actions=[
                ("New profile", self.create_profile),
                ("New layout", self.create_layout),
                ("Servers", self.show_moba_servers_status),
                ("Smart cards", self.show_moba_smartcards_status),
                ("Run doctor", self.show_doctor),
            ],
        )

    def show_moba_multiexec_status(self, *_args) -> None:
        self.set_moba_rail_active("macros")
        ssh_profiles = [profile for profile in self.store.load() if profile.protocol.lower() == "ssh"]
        if not ssh_profiles:
            self.show_workflow_dialog(
                "MultiExec",
                "Broadcast one command to multiple SSH sessions.",
                [
                    ("Target profiles", "none", "Create or import SSH profiles before using MultiExec."),
                    ("Command", DEFAULT_MOBA_MULTIEXEC_COMMAND, "Default preview command for broadcast planning."),
                ],
                "No SSH profiles are available.\nMultiExec uses the same safe argv broadcast engine as row broadcast.",
                actions=[("New profile", self.create_profile), ("Run doctor", self.show_doctor)],
            )
            return

        plan = build_moba_multiexec_plan(ssh_profiles, DEFAULT_MOBA_MULTIEXEC_COMMAND)
        preview_lines = list(plan.printable_commands()[:4])
        if plan.profile_count > len(preview_lines):
            preview_lines.append(f"... {plan.profile_count - len(preview_lines)} more broadcast target(s)")
        self.show_workflow_dialog(
            "MultiExec",
            "Broadcast one command to all SSH profiles using safe argv launch plans.",
            [
                ("Target profiles", str(plan.profile_count), ", ".join(plan.profiles[:3])),
                ("Command", plan.command, "Validated as a single-line remote command."),
                ("Route", plan.route.key, plan.route.route_role),
                ("Execution", "dry-run preview", "Use row broadcast when you are ready to execute."),
            ],
            "\n".join(
                [
                    "MultiExec broadcast preview",
                    f"Command: {plan.command}",
                    *preview_lines,
                ]
            ),
            actions=[("Run doctor", self.show_doctor), ("Macros", self.show_moba_macros_status)],
        )

    def show_moba_tunneling_status(self, *_args) -> None:
        profile = self.selected_profile_for_workflow()
        rows: list[tuple[str, str, str]]
        detail: str
        if profile is None:
            rows = [("SSH tunnels", "select profile", "Select an SSH/SFTP/SCP profile to inspect tunnel options.")]
            detail = "No profile selected.\nSelect a session from the left tree, then open Tunneling again."
            actions = [("New profile", self.create_profile)]
        else:
            tunnel_count = len(profile.tunnels)
            x11 = profile.options.get("x11", "off")
            agent = profile.options.get("agent_forward") or profile.options.get("forward_agent") or "off"
            rows = [
                ("Profile", profile.protocol.upper(), profile.name),
                ("Port forwards", str(tunnel_count), "local, remote or dynamic tunnel definitions"),
                ("X11 forwarding", str(x11), "x11=true/trusted maps to -X/-Y in SSH launch plans"),
                ("Agent forwarding", str(agent), "agent_forward=true maps to -A"),
            ]
            detail = "\n".join(
                [
                    f"Profile: {profile.name}",
                    f"Target : {profile.display_target}",
                    f"Tunnels: {tunnel_count}",
                    "Dry-run the profile to inspect the exact argv that will launch.",
                ]
            )
            actions = [("Edit profile", self.edit_selected_profile), ("Dry run", lambda: self.connect_selected(True))]
        self.show_workflow_dialog("Tunneling", "SSH forwarding and tunnel launch-plan inspection.", rows, detail, actions=actions)

    def show_moba_x_server_status(self, *_args) -> None:
        profile = self.selected_profile_for_workflow()
        x11_profiles = [item for item in self.store.load() if item.options.get("x11")]
        selected_x11 = profile.options.get("x11", "off") if profile is not None else "select profile"
        self.show_workflow_dialog(
            "X server",
            "X11-forwarded SSH sessions need a local X server such as VcXsrv, XQuartz or Xorg.",
            [
                ("Selected profile", selected_x11, profile.name if profile is not None else "No profile selected"),
                ("Profiles with X11", str(len(x11_profiles)), "Profiles where options.x11 is set"),
                ("Doctor check", "available", "Doctor reports local X server client availability."),
                ("Launch behavior", "SSH -X/-Y", "Remote Ops adds forwarding flags for opted-in profiles."),
            ],
            "\n".join(
                [
                    "X server workflow",
                    "Set profile option x11=true for -X or x11=trusted for -Y.",
                    "Start your local X server before launching the remote SSH profile.",
                ]
            ),
            actions=[("Run doctor", self.show_doctor), ("Edit profile", self.edit_selected_profile)],
        )

    def show_moba_packages_dialog(self, *_args) -> None:
        profile = self.selected_profile_for_workflow()
        if profile is None:
            rows = [("SFTP browser", "select profile", "Select an SSH/SFTP profile first.")]
            detail = "No profile selected.\nSelect a session from the tree to open files or transfer queues."
            actions = [("New profile", self.create_profile)]
        else:
            rows = [
                ("SFTP browser", profile.protocol.upper(), f"Open interactive file pane for {profile.name}."),
                ("Transfer queue", "available", "Preview batch get/put/mkdir operations before running."),
                ("Local preview", "available", "Inspect local files and directories before queueing transfers."),
            ]
            detail = "\n".join(
                [
                    f"Profile: {profile.name}",
                    f"Target : {profile.display_target}",
                    "Packages workflow maps to files, queues and local preview tools.",
                ]
            )
            actions = [("Open files", self.open_files_selected), ("Transfer queue", self.open_transfer_queue_selected)]
        self.show_workflow_dialog("Packages", "File, SFTP and transfer queue workflows.", rows, detail, actions=actions)

    def show_moba_help_dialog(self, *_args) -> None:
        self.show_workflow_dialog(
            "Help",
            "Shortcuts, diagnostics and workflow entry points.",
            [
                ("New terminal", "Ctrl+T", "Open a local shell tab."),
                ("Close tab", "Ctrl+W", "Close the current session tab."),
                ("Recover sessions", "Ctrl+Shift+T", "Reopen recent terminal plans."),
                ("Find log text", "Ctrl+F", "Focus the log search field in non-Moba layouts."),
                ("Doctor", "available", "Report protocol client availability."),
            ],
            "\n".join(
                [
                    "Help workflow",
                    "The Moba-style UI keeps common workflows in the ribbon and context menus.",
                    "Run doctor for local client availability and protocol readiness.",
                ]
            ),
            actions=[("Run doctor", self.show_doctor)],
        )

    def show_moba_macros_status(self, *_args) -> None:
        self.set_moba_rail_active("macros")
        self.show_workflow_dialog(
            "Macros",
            "Reusable snippets and scripted workflows for repeated operator actions.",
            [
                ("Snippets", "CLI-backed", "Store and run reusable command snippets."),
                ("MultiExec", "ribbon", "Preview broadcast command plans for SSH profiles."),
                ("Recover", "Ctrl+Shift+T", "Restore recent terminal plans."),
                ("Future dialogs", "tracked", "GUI macro editor can build on snippet storage."),
            ],
            "Macros are represented by reusable snippets and terminal plans today.\nThe rail keeps this workflow visible in the Moba-style shell.",
            actions=[("New terminal", self.open_local_terminal_tab), ("Run doctor", self.show_doctor)],
        )

    def show_workflow_dialog(
        self,
        title: str,
        subtitle: str,
        rows: list[tuple[str, str, str]],
        detail: str,
        *,
        actions: Sequence[tuple[str, Callable[..., object]]] | None = None,
    ) -> None:
        dialog = self.create_workflow_dialog(
            title,
            subtitle,
            rows,
            detail,
            actions=actions,
        )
        dialog.exec()
        self.statusBar().showMessage(f"Workflow: {title}")

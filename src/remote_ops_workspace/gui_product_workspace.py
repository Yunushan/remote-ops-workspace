"""Build the product workspace panels and shared terminal drawer controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from . import gui_preset_properties
from .gui_designs import (
    gui_design_mremoteng_inheritance_route,
    gui_design_preset_focus_interaction_route,
    gui_design_preset_selection_route,
    gui_design_product_identity_route,
    gui_design_reference_state,
    gui_design_securecrt_sftp_tab_route,
    gui_design_termius_snippet_route,
    gui_design_workflow_cards,
)
from .gui_dialogs import _literal_label
from .gui_values import _safe_tooltip_html, _widget_style

if TYPE_CHECKING:
    from PyQt6.QtCore import QObject
    from PyQt6.QtWidgets import QStatusBar

    from .gui_designs import (
        GuiPresetFocusInteractionRoute,
        GuiProductIdentityRoute,
        GuiTermiusSnippetRoute,
        GuiWorkspaceSurface,
    )
    from .gui_terminal import TerminalPane


class ProductWorkspaceContent:
    """Compose shared workspace content from the active preset's panels."""

    if TYPE_CHECKING:
        def current_design_id(self) -> str: ...
        def statusBar(self) -> QStatusBar: ...  # noqa: N802
        def apply_focus_interaction_route_for_design(
            self, route: GuiPresetFocusInteractionRoute, preset_id: str,
        ) -> None: ...
        @staticmethod
        def apply_termius_snippet_run_route_properties(
            widget: QObject, route: GuiTermiusSnippetRoute, *,
            triggered: bool = False, command: str | None = None, status: str | None = None,
        ) -> None: ...
        def handle_termius_snippet_run(self, _checked: bool = False) -> None: ...
        def build_mremoteng_document_controls_evidence(self) -> QFrame: ...
        def build_mremoteng_property_grid_evidence(self) -> QFrame: ...
        def build_mremoteng_runtime_document_surface(self, pane: TerminalPane | None = None) -> QFrame: ...
        def build_remmina_native_viewer_surface(self, terminal_pane: TerminalPane | None = None) -> QFrame: ...
        def build_remmina_sftp_transfer_evidence(self) -> QFrame: ...
        def build_remmina_viewer_controls_evidence(self) -> QFrame: ...
        def build_securecrt_command_window_evidence(self) -> QFrame: ...
        def build_securecrt_runtime_terminal_surface(self) -> QFrame: ...
        def build_securecrt_session_status_strip_evidence(self) -> QFrame: ...
        def build_securecrt_sftp_browser_evidence(self) -> QFrame: ...
        def build_termius_files_browser_evidence(self) -> QFrame: ...
        def build_termius_header_chips_evidence(self) -> QFrame: ...
        def build_termius_host_identity_strip_evidence(self) -> QFrame: ...
        def build_termius_native_sftp_surface(self, terminal_pane: TerminalPane | None = None) -> QFrame: ...

    def build_product_workflow_evidence(self) -> QFrame:
        design_id = self.current_design_id()
        cards = gui_design_workflow_cards(design_id)
        snippet_route = gui_design_termius_snippet_route() if design_id == "termius" else None
        inheritance_route = gui_design_mremoteng_inheritance_route() if design_id == "mremoteng" else None
        securecrt_sftp_route = gui_design_securecrt_sftp_tab_route() if design_id == "securecrt" else None
        panel = QFrame()
        panel.setObjectName("productWorkflowEvidence")
        panel.setProperty("designPreset", design_id)
        if snippet_route is not None:
            panel.setProperty("termiusSnippetRouteKey", snippet_route.key)
            panel.setProperty("termiusSnippetRouteRole", snippet_route.route_role)
            panel.setProperty("termiusSnippetRouteWorkflowKey", snippet_route.workflow_card_key)
            panel.setProperty("termiusSnippetRouteWorkflowCardObject", snippet_route.workflow_card_object)
            panel.setProperty("termiusSnippetRouteTitleObject", snippet_route.workflow_title_object)
            panel.setProperty("termiusSnippetRoutePrimaryObject", snippet_route.workflow_primary_object)
            panel.setProperty("termiusSnippetRouteSecondaryObject", snippet_route.workflow_secondary_object)
            panel.setProperty("termiusSnippetRouteIdentityObject", snippet_route.host_identity_object)
            panel.setProperty("termiusSnippetRouteIdentityFieldKey", snippet_route.identity_field_key)
            panel.setProperty("termiusSnippetRouteIdentityCellObject", snippet_route.identity_cell_object)
            panel.setProperty("termiusSnippetRouteActiveTab", snippet_route.active_tab_label)
            panel.setProperty("termiusSnippetRouteSelectedProfile", snippet_route.selected_profile_name)
            panel.setProperty("termiusSnippetRouteTitle", snippet_route.workflow_title)
            panel.setProperty("termiusSnippetRouteCommand", snippet_route.snippet_command)
            panel.setProperty("termiusSnippetRouteState", snippet_route.snippet_state)
            panel.setProperty("termiusSnippetRouteDetailLine", snippet_route.detail_line)
            panel.setProperty("termiusSnippetRouteRenderSource", snippet_route.render_source)
            self.termius_snippet_workflow_panel = panel
            self.apply_termius_snippet_run_route_properties(panel, snippet_route)
        if inheritance_route is not None:
            panel.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
            panel.setProperty("mRemoteNgInheritanceRouteRole", inheritance_route.route_role)
            panel.setProperty("mRemoteNgInheritanceRouteWorkflowKey", inheritance_route.workflow_card_key)
            panel.setProperty(
                "mRemoteNgInheritanceRouteWorkflowCardObject",
                inheritance_route.workflow_card_object,
            )
            panel.setProperty("mRemoteNgInheritanceRouteTitleObject", inheritance_route.workflow_title_object)
            panel.setProperty("mRemoteNgInheritanceRoutePrimaryObject", inheritance_route.workflow_primary_object)
            panel.setProperty(
                "mRemoteNgInheritanceRouteSecondaryObject",
                inheritance_route.workflow_secondary_object,
            )
            panel.setProperty("mRemoteNgInheritanceRoutePropertyGridObject", inheritance_route.property_grid_object)
            panel.setProperty("mRemoteNgInheritanceRoutePropertyRowKey", inheritance_route.property_row_key)
            panel.setProperty("mRemoteNgInheritanceRoutePropertyCellObject", inheritance_route.property_cell_object)
            panel.setProperty("mRemoteNgInheritanceRouteActiveTab", inheritance_route.active_tab_label)
            panel.setProperty("mRemoteNgInheritanceRouteSelectedProfile", inheritance_route.selected_profile_name)
            panel.setProperty("mRemoteNgInheritanceRouteSelectedTreeLabel", inheritance_route.selected_tree_label)
            panel.setProperty("mRemoteNgInheritanceRouteTitle", inheritance_route.workflow_title)
            panel.setProperty(
                "mRemoteNgInheritanceRouteInheritedPropertyLabel",
                inheritance_route.inherited_property_label,
            )
            panel.setProperty("mRemoteNgInheritanceRouteInheritedValue", inheritance_route.inherited_value)
            panel.setProperty("mRemoteNgInheritanceRouteInheritedSource", inheritance_route.inherited_source)
            panel.setProperty("mRemoteNgInheritanceRouteState", inheritance_route.inheritance_state)
            panel.setProperty("mRemoteNgInheritanceRouteRenderSource", inheritance_route.render_source)
        if securecrt_sftp_route is not None:
            panel.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
            panel.setProperty("secureCrtSftpTabRouteRole", securecrt_sftp_route.route_role)
            panel.setProperty("secureCrtSftpTabRouteWorkflowKey", securecrt_sftp_route.workflow_card_key)
            panel.setProperty(
                "secureCrtSftpTabRouteWorkflowCardObject",
                securecrt_sftp_route.workflow_card_object,
            )
            panel.setProperty("secureCrtSftpTabRouteTitleObject", securecrt_sftp_route.workflow_title_object)
            panel.setProperty("secureCrtSftpTabRoutePrimaryObject", securecrt_sftp_route.workflow_primary_object)
            panel.setProperty(
                "secureCrtSftpTabRouteSecondaryObject",
                securecrt_sftp_route.workflow_secondary_object,
            )
            panel.setProperty(
                "secureCrtSftpTabRouteSessionManagerObject",
                securecrt_sftp_route.session_manager_object,
            )
            panel.setProperty("secureCrtSftpTabRouteSelectedTreeObject", securecrt_sftp_route.selected_tree_object)
            panel.setProperty("secureCrtSftpTabRouteSelectedProfile", securecrt_sftp_route.selected_profile_name)
            panel.setProperty("secureCrtSftpTabRouteSelectedTreeLabel", securecrt_sftp_route.selected_tree_label)
            panel.setProperty("secureCrtSftpTabRouteActiveTab", securecrt_sftp_route.active_tab_label)
            panel.setProperty("secureCrtSftpTabRouteTabLabel", securecrt_sftp_route.sftp_tab_label)
            panel.setProperty("secureCrtSftpTabRouteStatusStripObject", securecrt_sftp_route.status_strip_object)
            panel.setProperty("secureCrtSftpTabRouteStatusFieldKey", securecrt_sftp_route.status_field_key)
            panel.setProperty("secureCrtSftpTabRouteStatusFieldObject", securecrt_sftp_route.status_field_object)
            panel.setProperty("secureCrtSftpTabRouteStatus", securecrt_sftp_route.status_value)
            panel.setProperty("secureCrtSftpTabRouteTransferState", securecrt_sftp_route.transfer_state)
            panel.setProperty("secureCrtSftpTabRouteRenderSource", securecrt_sftp_route.render_source)
        layout = QHBoxLayout(panel)
        compact_securecrt = design_id == "securecrt"
        layout.setContentsMargins(4 if compact_securecrt else 8, 3 if compact_securecrt else 8, 4 if compact_securecrt else 8, 3 if compact_securecrt else 8)
        layout.setSpacing(4 if compact_securecrt else 8)
        if compact_securecrt:
            panel.setMaximumHeight(38)
        for card in cards[:3]:
            card_frame = QFrame()
            card_frame.setObjectName("productWorkflowCard")
            card_frame.setProperty("workflowKey", card.key)
            card_frame.setMinimumWidth(190)
            if compact_securecrt:
                card_frame.setMaximumHeight(30)
            if snippet_route is not None and card.key == snippet_route.workflow_card_key:
                card_frame.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                card_frame.setProperty("termiusSnippetRouteKey", snippet_route.key)
                card_frame.setProperty("termiusSnippetRouteRole", snippet_route.route_role)
                card_frame.setProperty("termiusSnippetRouteWorkflowKey", snippet_route.workflow_card_key)
                card_frame.setProperty("termiusSnippetRouteWorkflowCardObject", snippet_route.workflow_card_object)
                card_frame.setProperty("termiusSnippetRouteIdentityObject", snippet_route.host_identity_object)
                card_frame.setProperty("termiusSnippetRouteIdentityFieldKey", snippet_route.identity_field_key)
                card_frame.setProperty("termiusSnippetRouteIdentityCellObject", snippet_route.identity_cell_object)
                card_frame.setProperty("termiusSnippetRouteActiveTab", snippet_route.active_tab_label)
                card_frame.setProperty("termiusSnippetRouteSelectedProfile", snippet_route.selected_profile_name)
                card_frame.setProperty("termiusSnippetRouteTitle", snippet_route.workflow_title)
                card_frame.setProperty("termiusSnippetRouteCommand", snippet_route.snippet_command)
                card_frame.setProperty("termiusSnippetRouteState", snippet_route.snippet_state)
                card_frame.setProperty("termiusSnippetRouteDetailLine", snippet_route.detail_line)
                card_frame.setProperty("termiusSnippetRouteRenderSource", snippet_route.render_source)
                self.termius_snippet_card = card_frame
                self.apply_termius_snippet_run_route_properties(card_frame, snippet_route)
                shortcut = QShortcut(QKeySequence(snippet_route.shortcut_sequence), card_frame)
                shortcut.setObjectName(snippet_route.shortcut_object)
                shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
                self.termius_snippet_shortcut = shortcut
                self.apply_termius_snippet_run_route_properties(shortcut, snippet_route)
                shortcut.activated.connect(self.handle_termius_snippet_run)
            if inheritance_route is not None and card.key == inheritance_route.workflow_card_key:
                card_frame.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                card_frame.setProperty("mRemoteNgInheritanceRouteRole", inheritance_route.route_role)
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteWorkflowKey",
                    inheritance_route.workflow_card_key,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteWorkflowCardObject",
                    inheritance_route.workflow_card_object,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteTitleObject",
                    inheritance_route.workflow_title_object,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRoutePrimaryObject",
                    inheritance_route.workflow_primary_object,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteSecondaryObject",
                    inheritance_route.workflow_secondary_object,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRoutePropertyGridObject",
                    inheritance_route.property_grid_object,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRoutePropertyRowKey",
                    inheritance_route.property_row_key,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRoutePropertyCellObject",
                    inheritance_route.property_cell_object,
                )
                card_frame.setProperty("mRemoteNgInheritanceRouteActiveTab", inheritance_route.active_tab_label)
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteSelectedProfile",
                    inheritance_route.selected_profile_name,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteSelectedTreeLabel",
                    inheritance_route.selected_tree_label,
                )
                card_frame.setProperty("mRemoteNgInheritanceRouteTitle", inheritance_route.workflow_title)
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteInheritedPropertyLabel",
                    inheritance_route.inherited_property_label,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteInheritedValue",
                    inheritance_route.inherited_value,
                )
                card_frame.setProperty(
                    "mRemoteNgInheritanceRouteInheritedSource",
                    inheritance_route.inherited_source,
                )
                card_frame.setProperty("mRemoteNgInheritanceRouteState", inheritance_route.inheritance_state)
                card_frame.setProperty("mRemoteNgInheritanceRouteRenderSource", inheritance_route.render_source)
            if securecrt_sftp_route is not None and card.key == securecrt_sftp_route.workflow_card_key:
                card_frame.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                card_frame.setProperty("secureCrtSftpTabRouteRole", securecrt_sftp_route.route_role)
                card_frame.setProperty(
                    "secureCrtSftpTabRouteWorkflowKey",
                    securecrt_sftp_route.workflow_card_key,
                )
                card_frame.setProperty(
                    "secureCrtSftpTabRouteWorkflowCardObject",
                    securecrt_sftp_route.workflow_card_object,
                )
                card_frame.setProperty(
                    "secureCrtSftpTabRouteStatusStripObject",
                    securecrt_sftp_route.status_strip_object,
                )
                card_frame.setProperty(
                    "secureCrtSftpTabRouteStatusFieldKey",
                    securecrt_sftp_route.status_field_key,
                )
                card_frame.setProperty("secureCrtSftpTabRouteActiveTab", securecrt_sftp_route.active_tab_label)
                card_frame.setProperty("secureCrtSftpTabRouteTabLabel", securecrt_sftp_route.sftp_tab_label)
                card_frame.setProperty("secureCrtSftpTabRouteStatus", securecrt_sftp_route.status_value)
                card_frame.setProperty(
                    "secureCrtSftpTabRouteTransferState",
                    securecrt_sftp_route.transfer_state,
                )
                card_frame.setProperty(
                    "secureCrtSftpTabRouteRenderSource",
                    securecrt_sftp_route.render_source,
                )
            card_layout = QVBoxLayout(card_frame)
            card_layout.setContentsMargins(4 if compact_securecrt else 8, 2 if compact_securecrt else 7, 4 if compact_securecrt else 8, 2 if compact_securecrt else 7)
            card_layout.setSpacing(1 if compact_securecrt else 3)
            title = _literal_label(card.title)
            title.setObjectName("productWorkflowTitle")
            primary = _literal_label(card.primary)
            primary.setObjectName("productWorkflowPrimary")
            secondary = _literal_label(card.secondary)
            secondary.setObjectName("productWorkflowSecondary")
            secondary.setWordWrap(True)
            if compact_securecrt:
                # Keep the routed secondary state in the widget tree for
                # evidence checks, but leave the connected terminal as
                # the visual focus of the SecureCRT workspace.
                secondary.setVisible(False)
            if snippet_route is not None and card.key == snippet_route.workflow_card_key:
                self.termius_snippet_title = title
                self.termius_snippet_primary = primary
                self.termius_snippet_secondary = secondary
                title.setProperty("termiusSnippetRouteKey", snippet_route.key)
                title.setProperty("termiusSnippetRouteTitle", card.title)
                primary.setProperty("termiusSnippetRouteKey", snippet_route.key)
                primary.setProperty("termiusSnippetRouteCommand", card.primary)
                secondary.setProperty("termiusSnippetRouteKey", snippet_route.key)
                secondary.setProperty("termiusSnippetRouteState", card.secondary)
                self.apply_termius_snippet_run_route_properties(title, snippet_route)
                self.apply_termius_snippet_run_route_properties(primary, snippet_route)
                self.apply_termius_snippet_run_route_properties(secondary, snippet_route)
            if inheritance_route is not None and card.key == inheritance_route.workflow_card_key:
                title.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                title.setProperty("mRemoteNgInheritanceRouteTitle", card.title)
                primary.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                primary.setProperty("mRemoteNgInheritanceRouteState", card.primary)
                secondary.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                secondary.setProperty("mRemoteNgInheritanceRoutePropertyGridObject", inheritance_route.property_grid_object)
            if securecrt_sftp_route is not None and card.key == securecrt_sftp_route.workflow_card_key:
                title.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                title.setProperty("secureCrtSftpTabRouteTitle", card.title)
                primary.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                primary.setProperty("secureCrtSftpTabRouteTransferState", card.primary)
                secondary.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                secondary.setProperty("secureCrtSftpTabRouteStatus", securecrt_sftp_route.status_value)
            card_layout.addWidget(title)
            card_layout.addWidget(primary)
            card_layout.addWidget(secondary)
            if snippet_route is not None and card.key == snippet_route.workflow_card_key:
                action = QToolButton()
                action.setObjectName(snippet_route.action_object)
                action.setText(snippet_route.action_label)
                action.setToolTip(
                    _safe_tooltip_html(
                        f"{snippet_route.action_label} snippet: {snippet_route.snippet_command}"
                    )
                )
                action.clicked.connect(self.handle_termius_snippet_run)
                self.termius_snippet_action = action
                self.apply_termius_snippet_run_route_properties(action, snippet_route)
                card_layout.addWidget(action, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(card_frame)
        return panel

    def build_product_workspace_surface_evidence(self, surface: GuiWorkspaceSurface) -> QFrame:
        selection_route = gui_design_preset_selection_route(self.current_design_id())
        panel = QFrame()
        panel.setObjectName("productWorkspaceSurface")
        panel.setProperty("designPreset", self.current_design_id())
        gui_preset_properties.apply_preset_selection_route_properties(panel, selection_route)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = _literal_label(surface.title)
        title.setObjectName("productWorkspaceTitle")
        state = _literal_label(surface.primary_state)
        state.setObjectName("productWorkspaceState")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(state)
        layout.addLayout(header)

        if self.current_design_id() == "securecrt":
            # SecureCRT is terminal-led in the supplied product captures:
            # the active SSH2 document occupies the central canvas and
            # the evidence/route panels are secondary tooling.  Keep the
            # routed evidence widgets below for verification, but make
            # the first visible surface a faithful terminal document.
            layout.addWidget(self.build_securecrt_runtime_terminal_surface())

        layout.addWidget(self.build_product_reference_state_evidence())
        if self.current_design_id() == "termius":
            layout.addWidget(self.build_termius_native_sftp_surface())
            layout.addWidget(self.build_termius_header_chips_evidence())
            layout.addWidget(self.build_termius_host_identity_strip_evidence())
            layout.addWidget(self.build_termius_files_browser_evidence())
        if self.current_design_id() == "remmina":
            layout.addWidget(self.build_remmina_native_viewer_surface())
            layout.addWidget(self.build_remmina_viewer_controls_evidence())
            layout.addWidget(self.build_remmina_sftp_transfer_evidence())
        if self.current_design_id() == "mremoteng":
            layout.addWidget(self.build_mremoteng_document_controls_evidence())
            layout.addWidget(self.build_mremoteng_property_grid_evidence())
            layout.addWidget(self.build_mremoteng_runtime_document_surface())
            self.apply_focus_interaction_route_for_design(
                gui_design_preset_focus_interaction_route("mremoteng"),
                "mremoteng",
            )
        if self.current_design_id() == "securecrt":
            layout.addWidget(self.build_securecrt_session_status_strip_evidence())
            layout.addWidget(self.build_securecrt_sftp_browser_evidence())

        panes = QHBoxLayout()
        panes.setSpacing(8)
        primary = self.build_product_workspace_pane(
            "productWorkspacePrimaryPane",
            surface.primary_title,
            surface.command_line,
            surface.detail_lines,
        )
        secondary = self.build_product_workspace_pane(
            "productWorkspaceSecondaryPane",
            surface.secondary_title,
            surface.secondary_state,
            surface.activity_lines,
        )
        panes.addWidget(primary, 3)
        panes.addWidget(secondary, 2)
        layout.addLayout(panes)
        if self.current_design_id() == "securecrt":
            layout.addWidget(self.build_securecrt_command_window_evidence())
        return panel

    def toggle_product_terminal_drawer(
        self,
        drawer: QWidget,
        button: QToolButton,
    ) -> None:
        """Toggle the opt-in terminal drawer on viewer-first product surfaces."""
        visible = not drawer.isVisible()
        drawer.setVisible(visible)
        state = "open" if visible else "closed"
        drawer.setProperty("productTerminalDrawerState", state)
        button.setText("Hide terminal" if visible else "Terminal")
        button.setProperty("productTerminalDrawerState", state)
        button.setAccessibleName("Hide terminal" if visible else "Show terminal")
        style = _widget_style(button)
        style.unpolish(button)
        style.polish(button)
        self.statusBar().showMessage(
            "Terminal drawer opened" if visible else "Terminal drawer closed",
            1800,
        )

    def build_product_reference_state_evidence(self) -> QFrame:
        reference = gui_design_reference_state(self.current_design_id())
        route = gui_design_product_identity_route(self.current_design_id())
        selection_route = gui_design_preset_selection_route(self.current_design_id())
        panel = QFrame()
        panel.setObjectName("productReferenceState")
        panel.setProperty("designPreset", self.current_design_id())
        self.apply_product_identity_route_properties(panel, route)
        gui_preset_properties.apply_preset_selection_route_properties(panel, selection_route)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(8)
        for key, value in reference.items():
            label = _literal_label(f"{key}: {value}")
            label.setObjectName("productReferenceStateItem")
            label.setProperty("referenceKey", key)
            self.apply_product_identity_route_properties(label, route)
            gui_preset_properties.apply_preset_selection_route_properties(label, selection_route)
            label.setToolTip(_safe_tooltip_html(f"{reference.active_tab_label} {key}"))
            layout.addWidget(label)
        layout.addStretch(1)
        return panel

    def apply_product_identity_route_properties(
        self, widget: QWidget, route: GuiProductIdentityRoute,
    ) -> None:
        properties = {
            "productIdentityRouteKey": route.key,
            "productIdentityRouteRole": route.route_role,
            "productIdentityPreset": route.preset_id,
            "productIdentitySelectedTreeLabel": route.selected_tree_label,
            "productIdentityReferenceStateObject": route.reference_state_object,
            "productIdentityReferenceItemObject": route.reference_item_object,
            "productIdentityTreeObject": route.tree_object,
            "productIdentityTabsObject": route.tabs_object,
            "productIdentityStatusSegmentObject": route.status_segment_object,
            "productIdentityWorkspaceSurfaceObject": route.workspace_surface_object,
            "productIdentityProfile": route.selected_profile_name,
            "productIdentityTarget": route.target_label,
            "productIdentityProtocol": route.protocol_label,
            "productIdentityActiveTab": route.active_tab_label,
            "productIdentitySidebar": route.sidebar_label,
            "productIdentityWorkspaceState": route.workspace_state,
            "productIdentityStatusSegments": list(route.status_segments),
            "productIdentityRenderSource": route.render_source,
        }
        for key, value in properties.items():
            widget.setProperty(key, value)

    def build_product_workspace_pane(
        self,
        object_name: str,
        title: str,
        lead: str,
        lines: tuple[str, ...],
    ) -> QFrame:
        pane = QFrame()
        pane.setObjectName(object_name)
        pane_layout = QVBoxLayout(pane)
        pane_layout.setContentsMargins(8, 7, 8, 7)
        pane_layout.setSpacing(4)
        pane_title = _literal_label(title)
        pane_title.setObjectName("productWorkspacePaneTitle")
        pane_layout.addWidget(pane_title)
        lead_label = _literal_label(lead)
        lead_label.setObjectName("productWorkspaceLead")
        lead_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pane_layout.addWidget(lead_label)
        for line in lines:
            line_label = _literal_label(line)
            line_label.setObjectName("productWorkspaceLine")
            line_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            pane_layout.addWidget(line_label)
        return pane

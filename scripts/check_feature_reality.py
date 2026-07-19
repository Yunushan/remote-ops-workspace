from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.cli import build_parser  # noqa: E402
from remote_ops_workspace.features import load_feature_manifest  # noqa: E402
from remote_ops_workspace.keys import build_keygen_plan  # noqa: E402
from remote_ops_workspace.launcher import build_launch_plan  # noqa: E402
from remote_ops_workspace.models import Profile, Tunnel  # noqa: E402

SAMPLE_HOST = "row-feature-check.example"

IMPLEMENTED_STATUS_PREFIX = "implemented"

FEATURE_REALITY_RULES: dict[str, dict[str, Any]] = {
    "protocol.ssh": {
        "protocols": ["ssh"],
        "module_attrs": ["remote_ops_workspace.launcher:build_launch_plan"],
    },
    "protocol.sftp": {
        "protocols": ["sftp"],
        "cli": ["files open", "files ls", "files get", "files put", "files queue"],
        "module_attrs": ["remote_ops_workspace.file_transfer:build_sftp_interactive_plan"],
    },
    "moba.ssh-browser": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_moba_connected_session_state"],
        "source_tokens": {
            "src/remote_ops_workspace/gui.py": ["MobaConnectedSessionPanel", "mobaSftpBrowser", "mobaSftpFileTable"]
        },
    },
    "moba.follow-terminal-folder": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_follow_terminal_folder_plan"],
        "source_tokens": {
            "src/remote_ops_workspace/gui.py": ["mobaFollowTerminalFolder", "follow_folder_plan"]
        },
    },
    "moba.remote-monitoring": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_remote_monitoring_plan"],
        "source_tokens": {
            "src/remote_ops_workspace/gui.py": ["mobaRemoteMonitoring", "mobaMonitoringMetric"]
        },
    },
    "moba.telemetry-status-bar": {
        "module_attrs": ["remote_ops_workspace.moba_connected:RemoteMonitoringSnapshot"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["mobaTelemetryBar", "mobaTelemetryItem"]},
    },
    "moba.ssh-connection-banner": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_ssh_connection_banner"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["mobaSshBanner", "mobaSshBannerCapability"]},
    },
    "moba.open-sftp-same-parameters": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_same_parameters_sftp_plan"],
        "source_tokens": {
            "src/remote_ops_workspace/moba_connected.py": [
                "open-sftp-same-parameters",
                "build_same_parameters_sftp_plan",
            ],
        },
    },
    "moba.ssh-smartcard-auth": {
        "module_attrs": [
            "remote_ops_workspace.launcher:_ssh_connection_option_args",
            "remote_ops_workspace.moba_connected:build_ssh_connection_banner",
        ],
        "plans": [
            {
                "profile": Profile(
                    name="smartcard-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    options={
                        "smartcard_auth": "true",
                        "pkcs11_provider": "/usr/lib/opensc-pkcs11.so",
                        "certificate_file": "/tmp/id_ed25519-cert.pub",
                        "identity_agent": "/tmp/ssh-agent.sock",
                    },
                ),
                "contains": [
                    "-I",
                    "/usr/lib/opensc-pkcs11.so",
                    "CertificateFile=/tmp/id_ed25519-cert.pub",
                    "IdentityAgent=/tmp/ssh-agent.sock",
                ],
            }
        ],
        "source_tokens": {
            "src/remote_ops_workspace/moba_connected.py": ["smartcard-auth", "Smart card auth"],
        },
    },
    "moba.smartcard-management-26-4": {
        "cli": [
            "smartcard inventory-plan",
            "smartcard select-review",
            "smartcard mobagent-plan",
            "smartcard ssh-browser-plan",
            "smartcard evidence-bundle",
            "smartcard evidence-verify",
        ],
        "module_attrs": [
            "remote_ops_workspace.moba_smartcards:build_smartcard_inventory_plan",
            "remote_ops_workspace.moba_smartcards:build_smartcard_management_gui_surface",
            "remote_ops_workspace.moba_smartcards:review_smartcard_certificate_selection",
            "remote_ops_workspace.moba_smartcards:build_mobagent_smartcard_plan",
            "remote_ops_workspace.moba_smartcards:build_smartcard_ssh_browser_plan",
            "remote_ops_workspace.moba_smartcards:build_smartcard_release_evidence_bundle_plan",
            "remote_ops_workspace.moba_smartcards:write_smartcard_release_evidence_bundle",
            "remote_ops_workspace.moba_smartcards:validate_smartcard_release_evidence",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardCertificate",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardInventoryPlan",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardGuiManagementSurface",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardGuiCertificateRow",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardSelectionReview",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardMobAgentPlan",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardSshBrowserPlan",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardReleaseEvidenceBundlePlan",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardReleaseEvidenceBundleResult",
            "remote_ops_workspace.moba_smartcards:MobaSmartCardReleaseEvidenceValidation",
            "remote_ops_workspace.moba_smartcards:MOBA_SMARTCARD_GUI_MANAGEMENT_SCHEMA",
            "remote_ops_workspace.moba_smartcards:MOBA_SMARTCARD_RELEASE_EVIDENCE_BUNDLE_SCHEMA",
            "remote_ops_workspace.moba_smartcards:MOBA_SMARTCARD_RELEASE_EVIDENCE_SCHEMA",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_smartcard_inventory_plan",
                "cmd_smartcard_select_review",
                "cmd_smartcard_mobagent_plan",
                "cmd_smartcard_ssh_browser_plan",
                "cmd_smartcard_evidence_bundle",
                "evidence-bundle",
                "cmd_smartcard_evidence_verify",
            ],
            "src/remote_ops_workspace/moba_smartcards.py": [
                "row.moba-smartcard.gui-management-surface.v1",
                "row.moba-smartcard.release-evidence-bundle.v1",
                "row.moba-smartcard.release-evidence.v1",
                "Microsoft CryptoAPI",
                "certificate-table",
                "export-openssh-public-key",
                "add_smartcard_to_mobagent",
                "openssh_public_key",
                "same_parameters_sftp",
                "multiplex_mode",
                "Production parity requires the supplied evidence files",
            ],
            "src/remote_ops_workspace/gui.py": [
                "show_moba_smartcards_status",
                "build_smartcard_management_gui_surface",
                "mobaSmartcardGuiManagementSchema",
                "mobaSmartcardGuiControls",
            ],
            "scripts/check_moba_smartcard_evidence.py": [
                "validate_smartcard_release_evidence",
                "--assets-dir",
            ],
        },
    },
    "moba.multi-execution": {
        "cli": ["broadcast"],
        "module_attrs": [
            "remote_ops_workspace.broadcast:run_broadcast",
            "remote_ops_workspace.moba_multiexec:build_moba_multiexec_plan",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/gui.py": ["show_moba_multiexec_status", "build_moba_multiexec_plan"],
            "src/remote_ops_workspace/gui_designs.py": ["multiexec", "Preview broadcast command plans"],
        },
    },
    "moba.professional-customizer": {
        "cli": ["customizer build"],
        "module_attrs": [
            "remote_ops_workspace.moba_customizer:build_moba_professional_customizer_plan",
            "remote_ops_workspace.moba_customizer:write_moba_professional_customizer_bundle",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": ["--brand-name", "--lock-setting", "cmd_customizer_build"],
            "src/remote_ops_workspace/moba_customizer.py": [
                "MobaProfessionalCustomizerPlan",
                "SHA256SUMS.txt",
                "locked_settings",
            ],
        },
    },
    "moba.professional-deployment-depth": {
        "cli": [
            "customizer deployment-plan",
            "customizer evidence-bundle",
            "customizer evidence-verify",
            "customizer update-verify",
        ],
        "module_attrs": [
            "remote_ops_workspace.moba_customizer:build_professional_deployment_plan",
            "remote_ops_workspace.moba_customizer:build_professional_deployment_evidence_bundle_plan",
            "remote_ops_workspace.moba_customizer:build_installer_branding_plan",
            "remote_ops_workspace.moba_customizer:build_enterprise_policy_lock_plan",
            "remote_ops_workspace.moba_customizer:build_enterprise_update_channel_plan",
            "remote_ops_workspace.moba_customizer:write_professional_deployment_evidence_bundle",
            "remote_ops_workspace.moba_customizer:validate_professional_deployment_evidence",
            "remote_ops_workspace.moba_customizer:validate_professional_update_manifest",
            "remote_ops_workspace.moba_customizer:canonical_update_manifest_payload",
            "remote_ops_workspace.moba_customizer:MobaProfessionalDeploymentPlan",
            "remote_ops_workspace.moba_customizer:MobaProfessionalDeploymentEvidenceBundlePlan",
            "remote_ops_workspace.moba_customizer:MobaProfessionalDeploymentEvidenceBundleResult",
            "remote_ops_workspace.moba_customizer:MobaProfessionalDeploymentEvidenceValidation",
            "remote_ops_workspace.moba_customizer:MobaProfessionalUpdateManifestValidation",
            "remote_ops_workspace.moba_customizer:MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA",
            "remote_ops_workspace.moba_customizer:MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA",
            "remote_ops_workspace.moba_customizer:MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_BUNDLE_SCHEMA",
            "remote_ops_workspace.enterprise_policy:load_enterprise_policy",
            "remote_ops_workspace.enterprise_policy:review_profile_write",
            "remote_ops_workspace.enterprise_policy:review_profile_launch",
            "remote_ops_workspace.enterprise_policy:review_profile_collection_change",
            "remote_ops_workspace.enterprise_policy:assert_profile_launch_allowed",
            "remote_ops_workspace.enterprise_policy:EnterprisePolicy",
            "remote_ops_workspace.enterprise_policy:EnterprisePolicyReview",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_customizer_deployment_plan",
                "cmd_customizer_evidence_bundle",
                "cmd_customizer_evidence_verify",
                "cmd_customizer_update_verify",
                "evidence-bundle",
                "--bundle-manifest-sha256",
                "--update-public-key",
                "assert_profile_launch_allowed",
            ],
            "src/remote_ops_workspace/storage.py": [
                "assert_profile_write_allowed",
                "assert_settings_write_allowed",
                "policy_path",
            ],
            "src/remote_ops_workspace/gui.py": [
                "assert_profile_launch_allowed",
                "surface=\"profile-editor\"",
                "surface=\"quick-connect\"",
            ],
            "src/remote_ops_workspace/web_server.py": [
                "enterprise-policy.json",
                "load_enterprise_policy",
            ],
            "apps/web/app.js": [
                "loadEnterprisePolicy",
                "reviewEnterpriseWebProfile",
                "enterprise-policy.json",
            ],
            "src/remote_ops_workspace/launcher.py": [
                "assert_profile_launch_allowed",
            ],
            "src/remote_ops_workspace/moba_customizer.py": [
                "row.moba-professional.deployment-evidence-bundle.v1",
                "row.moba-professional.deployment-evidence.v1",
                "write_professional_deployment_evidence_bundle",
                "windows_exe_rebranded",
                "windows_msi_rebranded",
                "signature_verified",
                "row.moba-professional.update-manifest.v1",
                "canonical_update_manifest_payload",
                "REQUIRED_POLICY_SURFACES",
                "Production parity requires the supplied evidence files",
            ],
            "scripts/check_moba_professional_deployment_evidence.py": [
                "validate_professional_deployment_evidence",
                "--assets-dir",
            ],
            "scripts/check_moba_professional_update_manifest.py": [
                "validate_professional_update_manifest",
                "--public-key",
            ],
        },
    },
    "moba.mobapt-unix-packages": {
        "cli": ["mobapt status", "mobapt search", "mobapt install", "mobapt update"],
        "module_attrs": [
            "remote_ops_workspace.moba_mobapt:build_mobapt_environment_status",
            "remote_ops_workspace.moba_mobapt:build_mobapt_package_plan",
            "remote_ops_workspace.moba_mobapt:discover_mobapt_package_managers",
            "remote_ops_workspace.moba_mobapt:mobapt_unix_tool_status",
            "remote_ops_workspace.moba_mobapt:run_mobapt_package_plan",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_mobapt_status",
                "cmd_mobapt_package",
                "--execute",
            ],
            "src/remote_ops_workspace/moba_mobapt.py": [
                "MobAptPackagePlan",
                "No bundled Unix command runtime",
                "run_mobapt_package_plan",
            ],
        },
    },
    "moba.mobapt-offline-runtime-cache": {
        "cli": ["mobapt runtime-status", "mobapt bundle-runtime", "mobapt cache-verify"],
        "module_attrs": [
            "remote_ops_workspace.moba_mobapt:build_mobapt_runtime_bundle_plan",
            "remote_ops_workspace.moba_mobapt:build_mobapt_runtime_status",
            "remote_ops_workspace.moba_mobapt:discover_mobapt_embedded_runtimes",
            "remote_ops_workspace.moba_mobapt:mobapt_runtime_roots",
            "remote_ops_workspace.moba_mobapt:validate_mobapt_cache_evidence",
            "remote_ops_workspace.moba_mobapt:write_mobapt_runtime_bundle",
            "remote_ops_workspace.moba_mobapt:MobAptRuntimeBundlePlan",
            "remote_ops_workspace.moba_mobapt:MobAptRuntimeBundleResult",
            "remote_ops_workspace.moba_mobapt:MobAptCacheEvidenceValidation",
            "remote_ops_workspace.moba_mobapt:MOBAPT_BUNDLE_PLAN_SCHEMA",
            "remote_ops_workspace.moba_mobapt:MOBAPT_CACHE_EVIDENCE_SCHEMA",
            "remote_ops_workspace.moba_mobapt:MOBAPT_RUNTIME_SCHEMA",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_mobapt_runtime_status",
                "cmd_mobapt_bundle_runtime",
                "cmd_mobapt_cache_verify",
                "runtime-status",
                "bundle-runtime",
                "cache-verify",
            ],
            "src/remote_ops_workspace/moba_mobapt.py": [
                "ROW_MOBAPT_RUNTIME_DIR",
                "row.mobapt.bundle-plan.v1",
                "row.mobapt.runtime.v1",
                "row.mobapt.offline-cache-evidence.v1",
                "ROW MobApt bundled tool shim",
                "mobapt-runtime.json",
                "mobapt-cache-evidence.json",
                "terminal_probe",
                "install_tests missing package proof",
            ],
            "scripts/check_mobapt_cache_evidence.py": [
                "validate_mobapt_cache_evidence",
                "--assets-dir",
            ],
        },
    },
    "moba.embedded-server-suite": {
        "cli": ["servers status", "servers start", "servers stop"],
        "module_attrs": [
            "remote_ops_workspace.moba_servers:build_moba_server_suite_status",
            "remote_ops_workspace.moba_servers:build_moba_server_plan",
            "remote_ops_workspace.moba_servers:discover_moba_server_runtimes",
            "remote_ops_workspace.moba_servers:start_moba_server",
            "remote_ops_workspace.moba_servers:stop_moba_server",
            "remote_ops_workspace.moba_servers:load_moba_server_record",
            "remote_ops_workspace.moba_servers:build_moba_server_gui_config_surface",
            "remote_ops_workspace.moba_servers:MobaEmbeddedServerGuiConfigSurface",
            "remote_ops_workspace.moba_servers:MobaEmbeddedServerGuiConfigRow",
            "remote_ops_workspace.moba_servers:SERVER_GUI_CONFIG_SCHEMA",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_servers_status",
                "cmd_servers_start",
                "cmd_servers_stop",
                "--allow-public-bind",
            ],
            "src/remote_ops_workspace/moba_servers.py": [
                "MobaEmbeddedServerPlan",
                "python-http",
                "sshd-sftp",
                "row.moba-servers.gui-config-surface.v1",
                "gui_controls",
                "Full proprietary parity",
            ],
            "src/remote_ops_workspace/gui.py": [
                "show_moba_servers_status",
                "build_moba_server_gui_config_surface",
                "mobaEmbeddedServerGuiConfigSchema",
                "mobaEmbeddedServerRuntimeRoots",
            ],
        },
    },
    "moba.embedded-server-packaged-daemon-evidence": {
        "cli": ["servers runtime-status", "servers bundle-runtime", "servers config-plan", "servers evidence-verify"],
        "module_attrs": [
            "remote_ops_workspace.moba_servers:build_moba_server_runtime_bundle_plan",
            "remote_ops_workspace.moba_servers:build_moba_server_runtime_status",
            "remote_ops_workspace.moba_servers:discover_packaged_moba_server_runtimes",
            "remote_ops_workspace.moba_servers:moba_server_runtime_roots",
            "remote_ops_workspace.moba_servers:build_moba_server_config_plan",
            "remote_ops_workspace.moba_servers:validate_moba_server_release_evidence",
            "remote_ops_workspace.moba_servers:write_moba_server_runtime_bundle",
            "remote_ops_workspace.moba_servers:MobaEmbeddedServerRuntimeBundlePlan",
            "remote_ops_workspace.moba_servers:MobaEmbeddedServerRuntimeBundleResult",
            "remote_ops_workspace.moba_servers:MobaEmbeddedServerReleaseEvidenceValidation",
            "remote_ops_workspace.moba_servers:SERVER_RUNTIME_BUNDLE_SCHEMA",
            "remote_ops_workspace.moba_servers:SERVER_RELEASE_EVIDENCE_SCHEMA",
            "remote_ops_workspace.moba_servers:SERVER_POLICY_SCHEMA",
            "remote_ops_workspace.moba_servers:build_moba_server_gui_config_surface",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_servers_runtime_status",
                "cmd_servers_bundle_runtime",
                "cmd_servers_config_plan",
                "cmd_servers_evidence_verify",
                "bundle-runtime",
                "evidence-verify",
            ],
            "src/remote_ops_workspace/moba_servers.py": [
                "ROW_SERVER_RUNTIME_DIR",
                "row.moba-servers.runtime-bundle.v1",
                "row.moba-servers.release-evidence.v1",
                "row.moba-servers.policy.v1",
                "servers-runtime.json",
                "packaged_service_count",
                "client_test.status must be passed",
                "services missing release evidence",
                "Placeholder daemon requires replacement",
            ],
            "src/remote_ops_workspace/gui.py": [
                "show_moba_servers_status",
                "mobaEmbeddedServerPackagedServiceCount",
                "mobaEmbeddedServerGuiConfigControls",
            ],
            "scripts/check_moba_server_release_evidence.py": [
                "validate_moba_server_release_evidence",
                "--assets-dir",
            ],
        },
    },
    "moba.text-editor-diff": {
        "cli": ["text preview", "text write", "text diff", "text remote-plan"],
        "module_attrs": [
            "remote_ops_workspace.moba_text:preview_text_document",
            "remote_ops_workspace.moba_text:write_text_document",
            "remote_ops_workspace.moba_text:diff_text_documents",
            "remote_ops_workspace.moba_text:build_remote_text_edit_plan",
            "remote_ops_workspace.moba_text:MobaRemoteTextEditPlan",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_text_preview",
                "cmd_text_write",
                "cmd_text_diff",
                "cmd_text_remote_plan",
            ],
            "src/remote_ops_workspace/moba_text.py": [
                "MobaTextEditor-style",
                "MobaDiff-style",
                "build_sftp_get_plan",
                "build_sftp_put_plan",
            ],
        },
    },
    "moba.text-editor-remote-gui-evidence": {
        "cli": ["text open-remote", "text save-review", "text evidence-bundle", "text evidence-verify"],
        "module_attrs": [
            "remote_ops_workspace.moba_text:build_moba_text_editor_tab_plan",
            "remote_ops_workspace.moba_text:review_moba_remote_text_save",
            "remote_ops_workspace.moba_text:build_moba_text_release_evidence_bundle_plan",
            "remote_ops_workspace.moba_text:write_moba_text_release_evidence_bundle",
            "remote_ops_workspace.moba_text:validate_moba_text_release_evidence",
            "remote_ops_workspace.moba_text:MobaTextEditorTabPlan",
            "remote_ops_workspace.moba_text:MobaRemoteTextSaveReview",
            "remote_ops_workspace.moba_text:MobaTextReleaseEvidenceBundlePlan",
            "remote_ops_workspace.moba_text:MobaTextReleaseEvidenceBundleResult",
            "remote_ops_workspace.moba_text:MobaTextReleaseEvidenceValidation",
            "remote_ops_workspace.moba_text:MOBA_TEXT_EDITOR_TAB_SCHEMA",
            "remote_ops_workspace.moba_text:MOBA_TEXT_RELEASE_EVIDENCE_BUNDLE_SCHEMA",
            "remote_ops_workspace.moba_text:MOBA_TEXT_RELEASE_EVIDENCE_SCHEMA",
            "remote_ops_workspace.moba_connected:MobaConnectedTextEditorState",
            "remote_ops_workspace.moba_connected:build_moba_connected_text_editor_state",
            "remote_ops_workspace.moba_connected:moba_connected_text_editor_route",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_text_open_remote",
                "cmd_text_save_review",
                "cmd_text_evidence_bundle",
                "evidence-bundle",
                "cmd_text_evidence_verify",
            ],
            "src/remote_ops_workspace/moba_text.py": [
                "row.moba-text.editor-tab.v1",
                "row.moba-text.remote-edit-evidence-bundle.v1",
                "row.moba-text.remote-edit-evidence.v1",
                "opened_from_sftp_browser",
                "conflict_checked",
                "real_connected_session",
                "connected-session",
                "Production parity requires the supplied evidence files",
            ],
            "src/remote_ops_workspace/moba_connected.py": [
                "connected-sftp-browser-text-editor",
                "mobaTextEditor",
                "itemDoubleClicked",
            ],
            "src/remote_ops_workspace/gui.py": [
                "QPlainTextEdit",
                "MobaTextEditorHighlighter",
                "mobaTextEditor",
                "handle_moba_text_editor_open_from_item",
                "mobaTextEditorSaveAction",
            ],
            "scripts/check_moba_text_remote_edit_evidence.py": [
                "validate_moba_text_release_evidence",
                "--assets-dir",
            ],
        },
    },
    "moba.ssh-browser-26-4-state": {
        "cli": [
            "ssh-browser status",
            "ssh-browser location",
            "ssh-browser columns",
            "ssh-browser open-plan",
            "ssh-browser overwrite",
        ],
        "module_attrs": [
            "remote_ops_workspace.moba_ssh_browser:load_moba_ssh_browser_preferences",
            "remote_ops_workspace.moba_ssh_browser:update_moba_ssh_browser_location",
            "remote_ops_workspace.moba_ssh_browser:update_moba_ssh_browser_columns",
            "remote_ops_workspace.moba_ssh_browser:build_moba_ssh_browser_open_plan",
            "remote_ops_workspace.moba_ssh_browser:review_moba_ssh_browser_overwrite",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_ssh_browser_status",
                "cmd_ssh_browser_open_plan",
                "cmd_ssh_browser_overwrite",
            ],
            "src/remote_ops_workspace/moba_ssh_browser.py": [
                "side-by-side",
                "column_widths",
                "overwrite confirmation",
                "build_same_parameters_sftp_plan",
            ],
        },
    },
    "moba.typed-macro-recorder": {
        "cli": ["macro record", "macro list", "macro show", "macro remove", "macro replay"],
        "module_attrs": [
            "remote_ops_workspace.moba_macros:MobaMacroStore",
            "remote_ops_workspace.moba_macros:record_typed_macro",
            "remote_ops_workspace.moba_macros:build_macro_replay_plans",
            "remote_ops_workspace.moba_macros:run_macro_replay",
            "remote_ops_workspace.moba_macros:MobaMacroReplayPlan",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_macro_record",
                "cmd_macro_replay",
                "--stdin",
                "--dry-run",
            ],
            "src/remote_ops_workspace/moba_macros.py": [
                "MobaXterm-style typed macro replay",
                "MobaMacroEvent",
                "input_text",
            ],
        },
    },
    "moba.macro-live-gui-evidence": {
        "cli": ["macro capture-plan", "macro live-plan", "macro evidence-bundle", "macro evidence-verify"],
        "module_attrs": [
            "remote_ops_workspace.moba_macros:build_macro_gui_capture_plan",
            "remote_ops_workspace.moba_macros:build_macro_live_replay_plans",
            "remote_ops_workspace.moba_macros:review_macro_live_replay",
            "remote_ops_workspace.moba_macros:build_macro_live_evidence_bundle_plan",
            "remote_ops_workspace.moba_macros:write_macro_live_evidence_bundle",
            "remote_ops_workspace.moba_macros:validate_macro_live_replay_evidence",
            "remote_ops_workspace.moba_macros:MobaMacroGuiCapturePlan",
            "remote_ops_workspace.moba_macros:MobaMacroLiveReplayPlan",
            "remote_ops_workspace.moba_macros:MobaMacroLiveReplayReview",
            "remote_ops_workspace.moba_macros:MobaMacroLiveEvidenceBundlePlan",
            "remote_ops_workspace.moba_macros:MobaMacroLiveEvidenceBundleResult",
            "remote_ops_workspace.moba_macros:MobaMacroLiveEvidenceValidation",
            "remote_ops_workspace.moba_macros:MobaMacroTerminalCaptureState",
            "remote_ops_workspace.moba_macros:MobaMacroTerminalReplayInjection",
            "remote_ops_workspace.moba_macros:MOBA_MACRO_GUI_CAPTURE_SCHEMA",
            "remote_ops_workspace.moba_macros:MOBA_MACRO_LIVE_EVIDENCE_BUNDLE_SCHEMA",
            "remote_ops_workspace.moba_macros:MOBA_MACRO_LIVE_REPLAY_SCHEMA",
            "remote_ops_workspace.moba_macros:MOBA_MACRO_LIVE_EVIDENCE_SCHEMA",
            "remote_ops_workspace.moba_macros:MOBA_MACRO_TERMINAL_CAPTURE_SCHEMA",
            "remote_ops_workspace.moba_macros:MOBA_MACRO_TERMINAL_REPLAY_SCHEMA",
            "remote_ops_workspace.moba_macros:start_terminal_macro_capture",
            "remote_ops_workspace.moba_macros:capture_terminal_macro_input",
            "remote_ops_workspace.moba_macros:finish_terminal_macro_capture",
            "remote_ops_workspace.moba_macros:cancel_terminal_macro_capture",
            "remote_ops_workspace.moba_macros:build_terminal_macro_replay_injection",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/cli.py": [
                "cmd_macro_capture_plan",
                "cmd_macro_live_plan",
                "cmd_macro_evidence_bundle",
                "evidence-bundle",
                "cmd_macro_evidence_verify",
            ],
            "src/remote_ops_workspace/moba_macros.py": [
                "row.moba-macro.gui-capture-plan.v1",
                "row.moba-macro.live-replay-evidence-bundle.v1",
                "row.moba-macro.live-replay-plan.v1",
                "row.moba-macro.live-replay-evidence.v1",
                "row.moba-macro.terminal-capture-state.v1",
                "row.moba-macro.terminal-replay-injection.v1",
                "pyqt-terminal-pane",
                "real_connected_session",
                "per_keystroke_timing_replay",
                "cancel_prompt_verified",
                "Production parity requires the supplied evidence files",
            ],
            "src/remote_ops_workspace/gui.py": [
                "macro_record_button",
                "mobaMacroCaptureActive",
                "capture_terminal_macro_input",
                "build_terminal_macro_replay_injection",
                "QTimer.singleShot",
                "mobaMacroReplayInjectedPayload",
            ],
            "scripts/check_moba_macro_live_evidence.py": [
                "validate_macro_live_replay_evidence",
                "--assets-dir",
            ],
        },
    },
    "moba.managed-x-server-runtime": {
        "cli": ["x11 start", "x11 status", "x11 package-status"],
        "module_attrs": [
            "remote_ops_workspace.x11:build_moba_x_server_plan",
            "remote_ops_workspace.x11:build_moba_x_server_status",
            "remote_ops_workspace.x11:build_moba_x_server_package_status",
            "remote_ops_workspace.x11:discover_packaged_x_server_runtimes",
            "remote_ops_workspace.x11:x_server_extension_inventory",
            "remote_ops_workspace.x11:is_x_display_in_use",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/x11.py": [
                "ManagedXServerPlan",
                "XServerRuntimeCandidate",
                "display_in_use",
                "GLX / OpenGL",
                "XDMCP",
                "ROW_XSERVER_RUNTIME_DIR",
            ],
            "src/remote_ops_workspace/cli.py": ["x11_status", "cmd_x11_status", "cmd_x11_package_status"],
        },
    },
    "moba.xserver-lifecycle-supervision": {
        "cli": ["x11 start", "x11 status", "x11 stop"],
        "module_attrs": [
            "remote_ops_workspace.x11:start_moba_x_server",
            "remote_ops_workspace.x11:stop_moba_x_server",
            "remote_ops_workspace.x11:load_moba_x_server_record",
            "remote_ops_workspace.x11:moba_x_server_state_path",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/x11.py": [
                "XServerLifecycleRecord",
                "xserver-state.json",
                "pid_probe",
                "taskkill",
                "SIGTERM",
            ],
            "src/remote_ops_workspace/cli.py": ["x11_stop", "cmd_x11_stop", "managed lifecycle"],
        },
    },
    "moba.xserver-smoke-evidence": {
        "cli": ["x11 smoke"],
        "module_attrs": [
            "remote_ops_workspace.x11:run_moba_x_server_smoke",
            "remote_ops_workspace.x11:write_moba_x_server_smoke_evidence",
            "remote_ops_workspace.x11:XServerSmokeEvidence",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/x11.py": [
                "xdpyinfo",
                "xset",
                "xprop",
                "evidence_sha256",
                "missing-probe-command",
            ],
            "src/remote_ops_workspace/cli.py": ["x11_smoke", "cmd_x11_smoke", "--probe-command"],
        },
    },
    "moba.xserver-packaged-runtime-evidence": {
        "cli": ["x11 package-status", "x11 bundle-runtime", "x11 evidence-verify"],
        "module_attrs": [
            "remote_ops_workspace.x11:build_moba_x_server_runtime_bundle_plan",
            "remote_ops_workspace.x11:discover_packaged_x_server_runtimes",
            "remote_ops_workspace.x11:x_server_packaged_runtime_roots",
            "remote_ops_workspace.x11:write_moba_x_server_runtime_bundle",
            "remote_ops_workspace.x11:validate_moba_x_server_release_evidence",
            "remote_ops_workspace.x11:XServerRuntimeBundlePlan",
            "remote_ops_workspace.x11:XServerRuntimeBundleResult",
            "remote_ops_workspace.x11:XServerReleaseEvidenceValidation",
            "remote_ops_workspace.x11:XSERVER_RUNTIME_BUNDLE_SCHEMA",
            "remote_ops_workspace.x11:XSERVER_RELEASE_EVIDENCE_SCHEMA",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/x11.py": [
                "row.moba-xserver.runtime-bundle.v1",
                "row.moba-xserver.release-evidence.v1",
                "forwarded_gui_app",
                "screenshot_sha256",
                "window_observed",
                "ROW_XSERVER_RUNTIME_DIR",
                "Placeholder runtime requires replacement",
            ],
            "src/remote_ops_workspace/cli.py": [
                "cmd_x11_package_status",
                "cmd_x11_bundle_runtime",
                "cmd_x11_evidence_verify",
                "bundle-runtime",
                "evidence-verify",
            ],
            "scripts/check_moba_xserver_release_evidence.py": [
                "validate_moba_x_server_release_evidence",
                "--assets-dir",
            ],
        },
    },
    "protocol.scp": {"protocols": ["scp"]},
    "protocol.rdp": {"protocols": ["rdp"]},
    "protocol.vnc": {"protocols": ["vnc"]},
    "protocol.telnet": {"protocols": ["telnet"]},
    "protocol.rlogin": {"protocols": ["rlogin"]},
    "protocol.rsh": {"protocols": ["rsh"]},
    "protocol.ftp": {"protocols": ["ftp"]},
    "protocol.mosh": {"protocols": ["mosh"]},
    "protocol.spice": {"protocols": ["spice"]},
    "protocol.x2go": {"protocols": ["x2go"]},
    "protocol.xdmcp": {"protocols": ["xdmcp"]},
    "protocol.ica": {"protocols": ["ica"]},
    "protocol.http": {"protocols": ["http", "https"]},
    "protocol.raw": {"protocols": ["raw"]},
    "protocol.serial": {"protocols": ["serial"]},
    "terminal.tabs": {
        "module_attrs": ["remote_ops_workspace.terminal:TerminalPanePlan"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["class TerminalPane"]},
    },
    "terminal.local-shell": {
        "protocols": ["local-shell"],
        "module_attrs": ["remote_ops_workspace.terminal:default_shell_plan"],
    },
    "terminal.splits": {
        "module_attrs": ["remote_ops_workspace.terminal:split_shell_plans"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["def add_split"]},
    },
    "terminal.layouts": {
        "cli": ["layout save", "layout run"],
        "module_attrs": ["remote_ops_workspace.layouts:build_layout_terminal_plans"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["open_selected_layout"]},
    },
    "terminal.broadcast": {
        "cli": ["broadcast"],
        "module_attrs": ["remote_ops_workspace.broadcast:run_broadcast"],
    },
    "terminal.shortcuts": {
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["QShortcut("]},
    },
    "terminal.search": {
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["def find_log_text"]},
    },
    "terminal.syntax-highlighting": {
        "module_attrs": [
            "remote_ops_workspace.terminal_highlighting:highlight_terminal_text",
            "remote_ops_workspace.terminal_highlighting:terminal_highlight_fragments",
        ],
        "source_tokens": {
            "src/remote_ops_workspace/gui.py": [
                "terminalSyntaxHighlightingEnabled",
                "terminalAnsiSgrColorEnabled",
                "terminalLinkActivation",
                "highlight_terminal_text",
            ],
            "src/remote_ops_workspace/terminal_emulation.py": [
                "def styled_fragments",
                "def ansi_256_color",
            ],
            "src/remote_ops_workspace/terminal_highlighting.py": [
                "DEFAULT_TERMINAL_SYNTAX_RULES",
                '"url"',
                "parse_terminal_syntax_rules",
            ],
        },
    },
    "terminal.macros": {
        "cli": ["snippet add", "snippet run"],
        "module_attrs": ["remote_ops_workspace.snippets:SnippetStore"],
    },
    "session.profiles": {
        "cli": ["profile add", "profile list", "profile show"],
        "module_attrs": ["remote_ops_workspace.storage:ProfileStore"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["class ProfileDialog"]},
    },
    "session.inheritance": {
        "cli": ["profile defaults"],
        "module_attrs": ["remote_ops_workspace.storage:ProfileStore.set_group_defaults"],
    },
    "session.quick-connect": {
        "cli": ["connect"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["def connect_selected"]},
    },
    "session.import-export": {
        "cli": ["export", "import"],
        "module_attrs": [
            "remote_ops_workspace.profile_importers:import_profiles",
            "remote_ops_workspace.sync:BackupService",
        ],
    },
    "security.vault": {
        "cli": ["vault init", "vault set", "vault get", "vault delete", "vault status"],
        "module_attrs": ["remote_ops_workspace.vault:LocalVault"],
    },
    "security.keys": {
        "cli": ["keygen"],
        "module_attrs": ["remote_ops_workspace.keys:build_keygen_plan"],
        "key_types": ["ed25519", "rsa"],
    },
    "security.fido": {
        "cli": ["keygen"],
        "module_attrs": ["remote_ops_workspace.keys:SECURITY_KEY_TYPES"],
        "key_types": ["ed25519-sk", "ecdsa-sk"],
    },
    "security.audit": {
        "module_attrs": ["remote_ops_workspace.audit:append_event"],
    },
    "network.tunnels": {
        "module_attrs": ["remote_ops_workspace.models:Tunnel"],
        "plans": [
            {
                "profile": Profile(
                    name="tunnel-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    tunnels=[
                        Tunnel(
                            mode="local",
                            local_port=15432,
                            remote_host="127.0.0.1",
                            remote_port=5432,
                        )
                    ],
                ),
                "contains": ["-L", "127.0.0.1:15432:127.0.0.1:5432"],
            }
        ],
    },
    "network.proxy": {
        "module_attrs": ["remote_ops_workspace.launcher:_ssh_proxy_args"],
        "plans": [
            {
                "profile": Profile(
                    name="proxy-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    options={"proxy_jump": "jump.example"},
                ),
                "contains": ["-J", "jump.example"],
            }
        ],
    },
    "network.tools": {
        "cli": ["nettool ping", "nettool trace", "nettool dns", "nettool whois", "nettool port"],
        "module_attrs": ["remote_ops_workspace.network_tools:build_network_tool_plan"],
    },
    "x11.forwarding": {
        "plans": [
            {
                "profile": Profile(
                    name="x11-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    options={"x11": "true"},
                ),
                "contains": ["-X"],
            },
            {
                "profile": Profile(
                    name="trusted-x11-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    options={"x11": "trusted"},
                ),
                "contains": ["-Y"],
            },
        ],
    },
    "x11.server": {
        "cli": ["x11 start"],
        "module_attrs": [
            "remote_ops_workspace.x11:build_x_server_plan",
            "remote_ops_workspace.x11:build_moba_x_server_plan",
        ],
    },
    "sync.local": {
        "cli": ["export", "import"],
        "module_attrs": ["remote_ops_workspace.sync:BackupService"],
    },
    "sync.cloud": {
        "cli": ["sync push", "sync pull"],
        "module_attrs": ["remote_ops_workspace.sync:DirectorySyncProvider"],
    },
    "web.pwa": {
        "cli": ["serve-web"],
        "module_attrs": ["remote_ops_workspace.web_server:serve_web"],
        "files": ["apps/web/index.html", "apps/web/app.js", "apps/web/manifest.json", "apps/web/sw.js"],
    },
    "android.termux": {
        "files": ["installers/install-termux.sh", "docs/ANDROID.md"],
    },
    "ios.web-pwa": {
        "files": ["apps/web/index.html", "apps/web/manifest.json", "apps/web/sw.js", "docs/IOS.md"],
    },
    "portable.mode": {
        "cli": ["init", "welcome"],
        "module_attrs": ["remote_ops_workspace.paths:data_dir"],
        "source_tokens": {"src/remote_ops_workspace/paths.py": ["ROW_HOME"]},
    },
    "plugins.entrypoints": {
        "cli": ["plugins list", "plugins validate", "plugins scaffold", "doctor"],
        "module_attrs": [
            "remote_ops_workspace.plugins:load_plugin_registry",
            "remote_ops_workspace.plugin_dev:validate_installed_plugins",
            "remote_ops_workspace.plugin_dev:scaffold_plugin",
        ],
    },
}


def main() -> int:
    errors = check_feature_reality()
    if errors:
        for error in errors:
            print(f"feature reality: {error}", file=sys.stderr)
        return 1
    print("feature reality alignment passed")
    return 0


def check_feature_reality() -> list[str]:
    errors: list[str] = []
    manifest = load_feature_manifest()
    features = manifest.get("features", [])
    feature_ids = {str(item.get("id", "")) for item in features}

    unknown_rule_ids = sorted(set(FEATURE_REALITY_RULES) - feature_ids)
    for feature_id in unknown_rule_ids:
        errors.append(f"reality rule references unknown feature id: {feature_id}")

    for item in features:
        feature_id = str(item.get("id", ""))
        status = str(item.get("status", ""))
        if status.startswith(IMPLEMENTED_STATUS_PREFIX) and feature_id not in FEATURE_REALITY_RULES:
            errors.append(f"{feature_id} has status {status} but no executable reality rule")

    command_paths = collect_cli_command_paths(build_parser())
    for feature_id in sorted(feature_ids & set(FEATURE_REALITY_RULES)):
        rule = FEATURE_REALITY_RULES[feature_id]
        errors.extend(check_cli_paths(feature_id, rule.get("cli", []), command_paths))
        errors.extend(check_protocol_plans(feature_id, rule.get("protocols", [])))
        errors.extend(check_named_plans(feature_id, rule.get("plans", [])))
        errors.extend(check_module_attrs(feature_id, rule.get("module_attrs", [])))
        errors.extend(check_files(feature_id, rule.get("files", [])))
        errors.extend(check_source_tokens(feature_id, rule.get("source_tokens", {})))
        errors.extend(check_key_types(feature_id, rule.get("key_types", [])))
    return errors


def collect_cli_command_paths(parser: argparse.ArgumentParser) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()

    def walk(current: argparse.ArgumentParser, prefix: tuple[str, ...]) -> None:
        subparser_actions = [
            action for action in current._actions if isinstance(action, argparse._SubParsersAction)
        ]
        if not subparser_actions:
            if prefix:
                paths.add(prefix)
            return
        for action in subparser_actions:
            for name, child in action.choices.items():
                walk(child, (*prefix, name))

    walk(parser, ())
    return paths


def check_cli_paths(
    feature_id: str,
    required_paths: list[str],
    command_paths: set[tuple[str, ...]],
) -> list[str]:
    errors: list[str] = []
    for required in required_paths:
        path = tuple(required.split())
        if path not in command_paths:
            errors.append(f"{feature_id} requires CLI command path: {required}")
    return errors


def check_protocol_plans(feature_id: str, protocols: list[str]) -> list[str]:
    errors: list[str] = []
    for protocol in protocols:
        try:
            plan = build_launch_plan(sample_profile(protocol))
        except Exception as exc:
            errors.append(f"{feature_id} cannot build {protocol} launch plan: {exc}")
            continue
        if not plan.command:
            errors.append(f"{feature_id} {protocol} launch plan has an empty command")
    return errors


def check_named_plans(feature_id: str, plan_specs: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for spec in plan_specs:
        profile = spec["profile"]
        try:
            plan = build_launch_plan(profile)
        except Exception as exc:
            errors.append(f"{feature_id} cannot build named launch plan {profile.name}: {exc}")
            continue
        for token in spec.get("contains", []):
            if token not in plan.command:
                errors.append(f"{feature_id} plan {profile.name} missing argv token: {token}")
    return errors


def check_module_attrs(feature_id: str, refs: list[str]) -> list[str]:
    errors: list[str] = []
    for ref in refs:
        module_name, separator, attr_path = ref.partition(":")
        if not separator:
            errors.append(f"{feature_id} module attribute ref must use module:attr: {ref}")
            continue
        try:
            obj: object = importlib.import_module(module_name)
            for attr in attr_path.split("."):
                obj = getattr(obj, attr)
        except Exception as exc:
            errors.append(f"{feature_id} missing module attribute {ref}: {exc}")
    return errors


def check_files(feature_id: str, required_files: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in required_files:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{feature_id} requires shipped file: {relative}")
    return errors


def check_source_tokens(feature_id: str, token_map: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    for relative, tokens in token_map.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{feature_id} source evidence file missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                errors.append(f"{feature_id} source evidence {relative} missing token: {token}")
    return errors


def check_key_types(feature_id: str, key_types: list[str]) -> list[str]:
    errors: list[str] = []
    for key_type in key_types:
        try:
            plan = build_keygen_plan(Path("feature-check-key"), key_type=key_type)
        except Exception as exc:
            errors.append(f"{feature_id} cannot build keygen plan for {key_type}: {exc}")
            continue
        if key_type not in plan.command:
            errors.append(f"{feature_id} keygen plan missing key type: {key_type}")
    return errors


def sample_profile(protocol: str) -> Profile:
    if protocol in {"http", "https"}:
        return Profile(name=f"{protocol}-proof", protocol=protocol, url=f"{protocol}://{SAMPLE_HOST}")
    if protocol == "raw":
        return Profile(name="raw-proof", protocol=protocol, host=SAMPLE_HOST, port=443)
    if protocol == "serial":
        return Profile(name="serial-proof", protocol=protocol, path="COM1", options={"baud": "115200"})
    if protocol == "local-shell":
        return Profile(name="local-shell-proof", protocol=protocol)
    if protocol == "ica":
        return Profile(name="ica-proof", protocol=protocol, path="sample.ica")
    if protocol in {"ssh1", "sshv1"}:
        return Profile(
            name=f"{protocol}-proof",
            protocol=protocol,
            host=SAMPLE_HOST,
            options={"allow_insecure_sshv1": "true"},
        )
    return Profile(name=f"{protocol}-proof", protocol=protocol, host=SAMPLE_HOST, username="operator")


if __name__ == "__main__":
    raise SystemExit(main())

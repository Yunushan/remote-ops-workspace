from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from . import command_safety as safe
from .file_safety import write_json_atomic
from .launcher import build_launch_plan
from .models import Profile

MOBA_SMARTCARD_INVENTORY_SCHEMA = "row.moba-smartcard.inventory-plan.v1"
MOBA_SMARTCARD_SELECTION_SCHEMA = "row.moba-smartcard.selection-review.v1"
MOBA_SMARTCARD_MOBAGENT_SCHEMA = "row.moba-smartcard.mobagent-plan.v1"
MOBA_SMARTCARD_SSH_BROWSER_SCHEMA = "row.moba-smartcard.ssh-browser-plan.v1"
MOBA_SMARTCARD_RELEASE_EVIDENCE_BUNDLE_SCHEMA = "row.moba-smartcard.release-evidence-bundle.v1"
MOBA_SMARTCARD_RELEASE_EVIDENCE_SCHEMA = "row.moba-smartcard.release-evidence.v1"
MOBA_SMARTCARD_GUI_MANAGEMENT_SCHEMA = "row.moba-smartcard.gui-management-surface.v1"

CAPI_PROVIDER_ALIASES = {
    "capi": "microsoft-capi",
    "cryptoapi": "microsoft-capi",
    "microsoft-capi": "microsoft-capi",
    "microsoft-cryptoapi": "microsoft-capi",
    "windows-capi": "microsoft-capi",
    "windows-cryptoapi": "microsoft-capi",
}


@dataclass(slots=True)
class MobaSmartCardCertificate:
    certificate_id: str
    label: str
    provider: str
    subject: str = ""
    issuer: str = ""
    public_key: str = ""
    fingerprint_sha256: str = ""
    source: str = "manual"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MobaSmartCardCertificate:
        return cls(
            certificate_id=safe.option_value(str(data.get("id") or data.get("certificate_id")), "certificate id"),
            label=safe.clean_text(str(data.get("label") or data.get("subject") or ""), "certificate label"),
            provider=normalise_smartcard_provider(str(data.get("provider") or "microsoft-capi")),
            subject=safe.clean_text(str(data.get("subject") or ""), "certificate subject", allow_empty=True),
            issuer=safe.clean_text(str(data.get("issuer") or ""), "certificate issuer", allow_empty=True),
            public_key=safe.clean_text(str(data.get("public_key") or ""), "certificate public key", allow_empty=True),
            fingerprint_sha256=_optional_sha256(
                str(data.get("fingerprint_sha256") or ""),
                "certificate fingerprint_sha256",
            ),
            source=safe.option_value(str(data.get("source") or "manual"), "certificate source"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.certificate_id,
            "label": self.label,
            "provider": self.provider,
            "subject": self.subject,
            "issuer": self.issuer,
            "public_key": self.public_key,
            "fingerprint_sha256": self.fingerprint_sha256,
            "source": self.source,
        }


@dataclass(slots=True)
class MobaSmartCardInventoryPlan:
    schema: str
    provider: str
    platform: str
    commands: list[list[str]]
    management_actions: list[str]
    retrieves_openssh_public_key: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "provider": self.provider,
            "platform": self.platform,
            "commands": self.commands,
            "management_actions": self.management_actions,
            "retrieves_openssh_public_key": self.retrieves_openssh_public_key,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaSmartCardSelectionReview:
    schema: str
    profile_name: str
    certificate_id: str
    available_certificate_ids: list[str]
    allowed: bool
    profile_options: dict[str, str]
    ssh_browser_multiplex_required: bool
    mobagent_add_required: bool
    confirmation_required: bool
    prompt: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "profile": self.profile_name,
            "certificate_id": self.certificate_id,
            "available_certificate_ids": self.available_certificate_ids,
            "allowed": self.allowed,
            "profile_options": self.profile_options,
            "ssh_browser_multiplex_required": self.ssh_browser_multiplex_required,
            "mobagent_add_required": self.mobagent_add_required,
            "confirmation_required": self.confirmation_required,
            "prompt": self.prompt,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaSmartCardMobAgentPlan:
    schema: str
    action: str
    certificate_id: str
    provider: str
    agent_socket: str
    global_setting_key: str
    command: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "action": self.action,
            "certificate_id": self.certificate_id,
            "provider": self.provider,
            "agent_socket": self.agent_socket,
            "global_setting_key": self.global_setting_key,
            "command": self.command,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaSmartCardSshBrowserPlan:
    schema: str
    profile_name: str
    certificate_id: str
    provider: str
    terminal_command: list[str]
    sftp_command: list[str]
    ssh_browser_same_parameters: bool
    multiplex_mode_required: bool
    profile_options: dict[str, str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "profile": self.profile_name,
            "certificate_id": self.certificate_id,
            "provider": self.provider,
            "terminal_command": self.terminal_command,
            "sftp_command": self.sftp_command,
            "ssh_browser_same_parameters": self.ssh_browser_same_parameters,
            "multiplex_mode_required": self.multiplex_mode_required,
            "profile_options": self.profile_options,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaSmartCardReleaseEvidenceValidation:
    evidence_path: str
    assets_dir: str
    passed: bool
    errors: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_path": self.evidence_path,
            "assets_dir": self.assets_dir,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


@dataclass(slots=True)
class MobaSmartCardReleaseEvidenceBundlePlan:
    schema: str
    out_dir: str
    evidence_path: str
    release_target: str
    profile_name: str
    certificate: MobaSmartCardCertificate
    add_to_mobagent: bool
    management_evidence_source: str
    selection_evidence_source: str
    mobagent_evidence_source: str
    browser_evidence_source: str
    management_command: str
    selection_command: str
    mobagent_command: str
    browser_command: str
    gui_visible: bool
    add_remove_controls: bool
    openssh_public_key_visible: bool
    expert_setting_visible: bool
    certificate_selected: bool
    profile_saved: bool
    global_add_setting: bool
    agent_loaded_certificate: bool
    same_parameters_sftp: bool
    multiplex_mode: bool
    real_connected_session: bool
    sftp_browser_open: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "out_dir": self.out_dir,
            "evidence_path": self.evidence_path,
            "release_target": self.release_target,
            "profile": self.profile_name,
            "certificate": self.certificate.to_dict(),
            "add_to_mobagent": self.add_to_mobagent,
            "management_evidence_source": self.management_evidence_source,
            "selection_evidence_source": self.selection_evidence_source,
            "mobagent_evidence_source": self.mobagent_evidence_source,
            "browser_evidence_source": self.browser_evidence_source,
            "management_command": self.management_command,
            "selection_command": self.selection_command,
            "mobagent_command": self.mobagent_command,
            "browser_command": self.browser_command,
            "gui_visible": self.gui_visible,
            "add_remove_controls": self.add_remove_controls,
            "openssh_public_key_visible": self.openssh_public_key_visible,
            "expert_setting_visible": self.expert_setting_visible,
            "certificate_selected": self.certificate_selected,
            "profile_saved": self.profile_saved,
            "global_add_setting": self.global_add_setting,
            "agent_loaded_certificate": self.agent_loaded_certificate,
            "same_parameters_sftp": self.same_parameters_sftp,
            "multiplex_mode": self.multiplex_mode,
            "real_connected_session": self.real_connected_session,
            "sftp_browser_open": self.sftp_browser_open,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaSmartCardReleaseEvidenceBundleResult:
    plan: MobaSmartCardReleaseEvidenceBundlePlan
    evidence_path: str
    files: tuple[str, ...]
    validation: MobaSmartCardReleaseEvidenceValidation
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "evidence_path": self.evidence_path,
            "files": list(self.files),
            "validation": self.validation.to_dict(),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaSmartCardGuiCertificateRow:
    certificate_id: str
    label: str
    provider: str
    subject: str
    issuer: str
    fingerprint_sha256: str
    public_key_available: bool
    source: str
    actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.certificate_id,
            "label": self.label,
            "provider": self.provider,
            "subject": self.subject,
            "issuer": self.issuer,
            "fingerprint_sha256": self.fingerprint_sha256,
            "public_key_available": self.public_key_available,
            "source": self.source,
            "actions": self.actions,
        }


@dataclass(slots=True)
class MobaSmartCardGuiManagementSurface:
    schema: str
    provider: str
    platform: str
    inventory_plan: MobaSmartCardInventoryPlan
    certificate_rows: tuple[MobaSmartCardGuiCertificateRow, ...]
    selected_certificate_id: str
    selected_profile: str
    selection_review: MobaSmartCardSelectionReview | None
    mobagent_plan: MobaSmartCardMobAgentPlan | None
    ssh_browser_plan: MobaSmartCardSshBrowserPlan | None
    gui_controls: tuple[str, ...]
    commands: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "provider": self.provider,
            "platform": self.platform,
            "inventory_plan": self.inventory_plan.to_dict(),
            "certificate_rows": [row.to_dict() for row in self.certificate_rows],
            "selected_certificate_id": self.selected_certificate_id,
            "selected_profile": self.selected_profile,
            "selection_review": self.selection_review.to_dict() if self.selection_review else None,
            "mobagent_plan": self.mobagent_plan.to_dict() if self.mobagent_plan else None,
            "ssh_browser_plan": self.ssh_browser_plan.to_dict() if self.ssh_browser_plan else None,
            "gui_controls": list(self.gui_controls),
            "commands": self.commands,
            "notes": self.notes,
        }


def build_smartcard_inventory_plan(provider: str = "microsoft-capi") -> MobaSmartCardInventoryPlan:
    provider_key = normalise_smartcard_provider(provider)
    if provider_key == "microsoft-capi":
        commands = [
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-ChildItem Cert:\\CurrentUser\\My | Select-Object Subject,Issuer,Thumbprint",
            ]
        ]
        notes = [
            "MobaXterm 26.4-style smart-card management interface for Microsoft CryptoAPI certificates.",
            "The inventory plan is declarative; release evidence must prove the GUI listed a real certificate.",
        ]
    else:
        commands = [["ssh-keygen", "-D", provider_key]]
        notes = [
            "OpenSC/PKCS#11 smart-card inventory uses ssh-keygen -D provider discovery.",
            "Release evidence must include the OpenSSH public key exported from the card.",
        ]
    return MobaSmartCardInventoryPlan(
        schema=MOBA_SMARTCARD_INVENTORY_SCHEMA,
        provider=provider_key,
        platform=platform.system() or "unknown",
        commands=commands,
        management_actions=["list", "add-certificate", "remove-certificate", "export-openssh-public-key"],
        retrieves_openssh_public_key=True,
        notes=notes,
    )


def build_smartcard_management_gui_surface(
    *,
    provider: str = "microsoft-capi",
    certificates: Iterable[MobaSmartCardCertificate] = (),
    selected_certificate_id: str = "",
    profile: Profile | None = None,
    add_to_mobagent: bool = False,
    force: bool = False,
) -> MobaSmartCardGuiManagementSurface:
    provider_key = normalise_smartcard_provider(provider)
    inventory = build_smartcard_inventory_plan(provider_key)
    certificate_list = list(certificates)
    selected_id = safe.option_value(
        selected_certificate_id or (certificate_list[0].certificate_id if certificate_list else "pending-selection"),
        "selected smart-card certificate id",
    )
    rows = tuple(_smartcard_gui_row(certificate) for certificate in certificate_list)
    selection = None
    ssh_browser = None
    if profile is not None and selected_id != "pending-selection":
        selection = review_smartcard_certificate_selection(
            profile,
            selected_id,
            certificate_list,
            add_to_mobagent=add_to_mobagent,
            force=force,
        )
        ssh_browser = build_smartcard_ssh_browser_plan(
            profile,
            selected_id,
            provider=provider_key,
            add_to_mobagent=add_to_mobagent,
        )
    mobagent = None
    if selected_id != "pending-selection":
        mobagent = build_mobagent_smartcard_plan(
            selected_id,
            provider=provider_key,
            action="add" if add_to_mobagent else "list",
        )
    commands = [
        f"row smartcard inventory-plan --provider {provider_key}",
    ]
    if profile is not None and selected_id != "pending-selection":
        commands.append(f"row smartcard select-review {profile.name} --certificate-id {selected_id}")
        commands.append(f"row smartcard ssh-browser-plan {profile.name} --certificate-id {selected_id}")
    if selected_id != "pending-selection":
        commands.append(f"row smartcard mobagent-plan --certificate-id {selected_id}")
    notes = [
        "MobaXterm 26.4-style smart-card management GUI surface.",
        "Certificate inventory, add/remove controls and OpenSSH public-key export are represented from the same release-evidence contract.",
        "Real parity still requires evidence from an actual smart card and connected SSH/SFTP session.",
    ]
    return MobaSmartCardGuiManagementSurface(
        schema=MOBA_SMARTCARD_GUI_MANAGEMENT_SCHEMA,
        provider=provider_key,
        platform=inventory.platform,
        inventory_plan=inventory,
        certificate_rows=rows,
        selected_certificate_id=selected_id,
        selected_profile=profile.name if profile is not None else "",
        selection_review=selection,
        mobagent_plan=mobagent,
        ssh_browser_plan=ssh_browser,
        gui_controls=(
            "provider-selector",
            "certificate-table",
            "add-certificate",
            "remove-certificate",
            "export-openssh-public-key",
            "select-for-ssh-session",
            "add-to-mobagent",
            "open-sftp-same-parameters",
        ),
        commands=commands,
        notes=notes,
    )


def review_smartcard_certificate_selection(
    profile: Profile,
    certificate_id: str,
    certificates: Iterable[MobaSmartCardCertificate],
    *,
    add_to_mobagent: bool = False,
    force: bool = False,
) -> MobaSmartCardSelectionReview:
    if profile.protocol.lower() != "ssh":
        raise ValueError(f"smart-card certificate selection requires an ssh profile: {profile.name}")
    selected_id = safe.option_value(certificate_id, "certificate id")
    available = list(certificates)
    available_ids = [item.certificate_id for item in available]
    selected = next((item for item in available if item.certificate_id == selected_id), None)
    allowed = selected is not None or force
    provider = selected.provider if selected is not None else normalise_smartcard_provider(
        profile.options.get("smartcard_provider") or "microsoft-capi"
    )
    profile_options = _smartcard_profile_options(selected_id, provider, add_to_mobagent)
    if selected is not None:
        profile_options["smartcard_certificate_label"] = selected.label
        if selected.public_key:
            profile_options["smartcard_public_key"] = selected.public_key
        if selected.fingerprint_sha256:
            profile_options["smartcard_fingerprint_sha256"] = selected.fingerprint_sha256
    prompt = ""
    notes = [
        "MobaXterm 26.4-style SSH expert setting selects a smart-card certificate for the profile.",
        "Smart-card SSH sessions require SSH-browser multiplex mode so the SFTP browser reuses the authenticated session parameters.",
    ]
    if selected is None:
        prompt = "Certificate id was not found in the current smart-card inventory; refresh inventory or pass --force."
        notes.append("Certificate selection conflict detected.")
    else:
        prompt = "Confirm the selected smart-card certificate before saving SSH profile expert settings."
    return MobaSmartCardSelectionReview(
        schema=MOBA_SMARTCARD_SELECTION_SCHEMA,
        profile_name=profile.name,
        certificate_id=selected_id,
        available_certificate_ids=available_ids,
        allowed=allowed,
        profile_options=profile_options,
        ssh_browser_multiplex_required=True,
        mobagent_add_required=add_to_mobagent,
        confirmation_required=True,
        prompt=prompt,
        notes=notes,
    )


def build_mobagent_smartcard_plan(
    certificate_id: str,
    *,
    provider: str = "microsoft-capi",
    action: str = "add",
    agent_socket: str = "",
) -> MobaSmartCardMobAgentPlan:
    action_key = safe.option_value(action, "MobAgent smart-card action").lower()
    if action_key not in {"add", "remove", "list"}:
        raise ValueError("MobAgent smart-card action must be add, remove or list")
    certificate_key = safe.option_value(certificate_id, "certificate id")
    provider_key = normalise_smartcard_provider(provider)
    socket = safe.path_arg(agent_socket, "agent socket") if agent_socket else ""
    command = ["mobagent", "smartcard", action_key, certificate_key]
    if provider_key:
        command.extend(["--provider", provider_key])
    if socket:
        command.extend(["--agent-socket", socket])
    return MobaSmartCardMobAgentPlan(
        schema=MOBA_SMARTCARD_MOBAGENT_SCHEMA,
        action=action_key,
        certificate_id=certificate_key,
        provider=provider_key,
        agent_socket=socket,
        global_setting_key="add_smartcard_to_mobagent",
        command=safe.argv_list(command, "MobAgent smart-card command"),
        notes=[
            "MobaXterm 26.4-style global setting adds the selected smart card to MobAgent.",
            "The command is an adapter contract; release evidence must prove the agent saw the certificate.",
        ],
    )


def build_smartcard_ssh_browser_plan(
    profile: Profile,
    certificate_id: str,
    *,
    provider: str = "microsoft-capi",
    add_to_mobagent: bool = False,
) -> MobaSmartCardSshBrowserPlan:
    if profile.protocol.lower() != "ssh":
        raise ValueError(f"smart-card SSH-browser plan requires an ssh profile: {profile.name}")
    certificate_key = safe.option_value(certificate_id, "certificate id")
    provider_key = normalise_smartcard_provider(provider)
    options = {
        **profile.options,
        **_smartcard_profile_options(certificate_key, provider_key, add_to_mobagent),
        "ssh_browser_multiplex": "true",
        "ssh_browser_same_parameters": "true",
    }
    ssh_profile = _replace_profile(profile, protocol="ssh", options=options)
    sftp_profile = _replace_profile(profile, protocol="sftp", options=options)
    terminal = build_launch_plan(ssh_profile)
    sftp = build_launch_plan(sftp_profile)
    return MobaSmartCardSshBrowserPlan(
        schema=MOBA_SMARTCARD_SSH_BROWSER_SCHEMA,
        profile_name=profile.name,
        certificate_id=certificate_key,
        provider=provider_key,
        terminal_command=terminal.command,
        sftp_command=sftp.command,
        ssh_browser_same_parameters=True,
        multiplex_mode_required=True,
        profile_options=options,
        notes=[
            *terminal.notes,
            "MobaXterm 26.4-style SSH-browser uses the same smart-card SSH parameters.",
            "Multiplex mode is required when the SSH session uses a smart card.",
        ],
    )


def build_smartcard_release_evidence_bundle_plan(
    profile: Profile,
    certificate: MobaSmartCardCertificate,
    *,
    out_dir: Path,
    management_evidence: Path,
    selection_evidence: Path,
    mobagent_evidence: Path,
    browser_evidence: Path,
    release_target: str = "local-bundle",
    add_to_mobagent: bool = True,
    management_command: str = "",
    selection_command: str = "",
    mobagent_command: str = "",
    browser_command: str = "",
    gui_visible: bool = False,
    add_remove_controls: bool = False,
    openssh_public_key_visible: bool = False,
    expert_setting_visible: bool = False,
    certificate_selected: bool = False,
    profile_saved: bool = False,
    global_add_setting: bool = False,
    agent_loaded_certificate: bool = False,
    same_parameters_sftp: bool = False,
    multiplex_mode: bool = False,
    real_connected_session: bool = False,
    sftp_browser_open: bool = False,
) -> MobaSmartCardReleaseEvidenceBundlePlan:
    cert = _normalise_certificate(certificate)
    surface = build_smartcard_management_gui_surface(
        provider=cert.provider,
        certificates=[cert],
        selected_certificate_id=cert.certificate_id,
        profile=profile,
        add_to_mobagent=add_to_mobagent,
    )
    selection = surface.selection_review or review_smartcard_certificate_selection(
        profile,
        cert.certificate_id,
        [cert],
        add_to_mobagent=add_to_mobagent,
    )
    mobagent = surface.mobagent_plan or build_mobagent_smartcard_plan(
        cert.certificate_id,
        provider=cert.provider,
        action="add" if add_to_mobagent else "list",
    )
    browser = surface.ssh_browser_plan or build_smartcard_ssh_browser_plan(
        profile,
        cert.certificate_id,
        provider=cert.provider,
        add_to_mobagent=add_to_mobagent,
    )
    root = Path(out_dir).expanduser()
    evidence_path = root / "moba-smartcard-release.json"
    notes = [
        "Bundle plan writes MobaXterm 26.4-style smart-card release evidence from supplied proof files.",
        "Production parity requires the supplied evidence files to come from a real smart card, MobAgent handoff and connected SSH/SFTP browser session.",
    ]
    if not cert.fingerprint_sha256 or not cert.public_key:
        notes.append("Certificate fingerprint and OpenSSH public key are incomplete; the verifier will fail until real certificate metadata is supplied.")
    if not selection.allowed:
        notes.append("Smart-card certificate selection is not allowed until the selected certificate appears in inventory.")
    if not all(
        (
            gui_visible,
            add_remove_controls,
            openssh_public_key_visible,
            expert_setting_visible,
            certificate_selected,
            profile_saved,
            global_add_setting,
            agent_loaded_certificate,
            same_parameters_sftp,
            multiplex_mode,
            real_connected_session,
            sftp_browser_open,
        )
    ):
        notes.append("Evidence flags are incomplete; the verifier will fail until real smart-card session evidence is asserted.")
    return MobaSmartCardReleaseEvidenceBundlePlan(
        schema=MOBA_SMARTCARD_RELEASE_EVIDENCE_BUNDLE_SCHEMA,
        out_dir=str(root),
        evidence_path=str(evidence_path),
        release_target=safe.clean_text(release_target, "release target"),
        profile_name=profile.name,
        certificate=cert,
        add_to_mobagent=bool(add_to_mobagent),
        management_evidence_source=str(Path(management_evidence).expanduser()),
        selection_evidence_source=str(Path(selection_evidence).expanduser()),
        mobagent_evidence_source=str(Path(mobagent_evidence).expanduser()),
        browser_evidence_source=str(Path(browser_evidence).expanduser()),
        management_command=safe.clean_text(
            management_command or f"row smartcard inventory-plan --provider {surface.provider}",
            "management command",
        ),
        selection_command=safe.clean_text(
            selection_command or f"row smartcard select-review {profile.name} --certificate-id {selection.certificate_id}",
            "selection command",
        ),
        mobagent_command=safe.clean_text(mobagent_command or " ".join(mobagent.command), "mobagent command"),
        browser_command=safe.clean_text(
            browser_command or f"row smartcard ssh-browser-plan {profile.name} --certificate-id {browser.certificate_id}",
            "browser command",
        ),
        gui_visible=bool(gui_visible),
        add_remove_controls=bool(add_remove_controls),
        openssh_public_key_visible=bool(openssh_public_key_visible),
        expert_setting_visible=bool(expert_setting_visible),
        certificate_selected=bool(certificate_selected),
        profile_saved=bool(profile_saved),
        global_add_setting=bool(global_add_setting),
        agent_loaded_certificate=bool(agent_loaded_certificate),
        same_parameters_sftp=bool(same_parameters_sftp),
        multiplex_mode=bool(multiplex_mode),
        real_connected_session=bool(real_connected_session),
        sftp_browser_open=bool(sftp_browser_open),
        notes=notes,
    )


def write_smartcard_release_evidence_bundle(
    plan: MobaSmartCardReleaseEvidenceBundlePlan,
) -> MobaSmartCardReleaseEvidenceBundleResult:
    if plan.schema != MOBA_SMARTCARD_RELEASE_EVIDENCE_BUNDLE_SCHEMA:
        raise ValueError(f"smart-card release evidence bundle schema must be {MOBA_SMARTCARD_RELEASE_EVIDENCE_BUNDLE_SCHEMA}")
    root = Path(plan.out_dir)
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    copied = {
        "management_interface": _copy_evidence_asset(
            Path(plan.management_evidence_source),
            evidence_dir,
            "management-interface",
            root,
        ),
        "ssh_session_selection": _copy_evidence_asset(
            Path(plan.selection_evidence_source),
            evidence_dir,
            "ssh-session-selection",
            root,
        ),
        "mobagent": _copy_evidence_asset(Path(plan.mobagent_evidence_source), evidence_dir, "mobagent", root),
        "ssh_browser": _copy_evidence_asset(Path(plan.browser_evidence_source), evidence_dir, "ssh-browser", root),
    }
    payload = {
        "schema": MOBA_SMARTCARD_RELEASE_EVIDENCE_SCHEMA,
        "release_target": plan.release_target,
        "certificate": {
            "id": plan.certificate.certificate_id,
            "provider": plan.certificate.provider,
            "fingerprint_sha256": plan.certificate.fingerprint_sha256,
            "openssh_public_key": plan.certificate.public_key,
        },
        "management_interface": {
            "status": "passed",
            "command": plan.management_command,
            "evidence_file": copied["management_interface"],
            "evidence_sha256": _sha256_path(root / copied["management_interface"]),
            "gui_visible": plan.gui_visible,
            "add_remove_controls": plan.add_remove_controls,
            "openssh_public_key_visible": plan.openssh_public_key_visible,
        },
        "ssh_session_selection": {
            "status": "passed",
            "command": plan.selection_command,
            "evidence_file": copied["ssh_session_selection"],
            "evidence_sha256": _sha256_path(root / copied["ssh_session_selection"]),
            "expert_setting_visible": plan.expert_setting_visible,
            "certificate_selected": plan.certificate_selected,
            "profile_saved": plan.profile_saved,
        },
        "mobagent": {
            "status": "passed",
            "command": plan.mobagent_command,
            "evidence_file": copied["mobagent"],
            "evidence_sha256": _sha256_path(root / copied["mobagent"]),
            "global_add_setting": plan.global_add_setting,
            "agent_loaded_certificate": plan.agent_loaded_certificate,
        },
        "ssh_browser": {
            "status": "passed",
            "command": plan.browser_command,
            "evidence_file": copied["ssh_browser"],
            "evidence_sha256": _sha256_path(root / copied["ssh_browser"]),
            "same_parameters_sftp": plan.same_parameters_sftp,
            "multiplex_mode": plan.multiplex_mode,
            "real_connected_session": plan.real_connected_session,
            "sftp_browser_open": plan.sftp_browser_open,
        },
    }
    target_evidence_path = Path(plan.evidence_path)
    write_json_atomic(target_evidence_path, payload, private=False)
    validation = validate_smartcard_release_evidence(target_evidence_path, assets_dir=root)
    files = tuple(
        dict.fromkeys(
            (
                copied["management_interface"],
                copied["ssh_session_selection"],
                copied["mobagent"],
                copied["ssh_browser"],
                _relative_to_root(target_evidence_path, root),
            )
        )
    )
    return MobaSmartCardReleaseEvidenceBundleResult(
        plan=plan,
        evidence_path=str(target_evidence_path),
        files=files,
        validation=validation,
        notes=list(plan.notes),
    )


def validate_smartcard_release_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobaSmartCardReleaseEvidenceValidation:
    target_evidence_path = Path(evidence_path)
    root = Path(assets_dir) if assets_dir is not None else target_evidence_path.parent
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "schema": "",
        "release_target": "",
        "certificate_id": "",
        "provider": "",
    }
    try:
        data = json.loads(target_evidence_path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"evidence file cannot be read: {exc}")
        data = {}
    except json.JSONDecodeError as exc:
        errors.append(f"evidence file is not valid JSON: {exc}")
        data = {}
    if not isinstance(data, dict):
        errors.append("evidence root must be a JSON object")
        data = {}

    schema = str(data.get("schema") or data.get("schema_version") or "")
    summary["schema"] = schema
    if schema != MOBA_SMARTCARD_RELEASE_EVIDENCE_SCHEMA:
        errors.append(f"schema must be {MOBA_SMARTCARD_RELEASE_EVIDENCE_SCHEMA}")
    summary["release_target"] = _required_text(data, "release_target", errors)

    certificate = _required_mapping(data, "certificate", errors)
    summary["certificate_id"] = _required_text(certificate, "id", errors, prefix="certificate.")
    summary["provider"] = _required_text(certificate, "provider", errors, prefix="certificate.")
    _required_sha256(
        _required_text(certificate, "fingerprint_sha256", errors, prefix="certificate."),
        "certificate.fingerprint_sha256",
        errors,
    )
    _required_text(certificate, "openssh_public_key", errors, prefix="certificate.")

    management = _required_mapping(data, "management_interface", errors)
    _validate_action_evidence(management, root, errors, "management_interface")
    for key in ("gui_visible", "add_remove_controls", "openssh_public_key_visible"):
        if management.get(key) is not True:
            errors.append(f"management_interface.{key} must be true")

    selection = _required_mapping(data, "ssh_session_selection", errors)
    _validate_action_evidence(selection, root, errors, "ssh_session_selection")
    for key in ("expert_setting_visible", "certificate_selected", "profile_saved"):
        if selection.get(key) is not True:
            errors.append(f"ssh_session_selection.{key} must be true")

    mobagent = _required_mapping(data, "mobagent", errors)
    _validate_action_evidence(mobagent, root, errors, "mobagent")
    if mobagent.get("global_add_setting") is not True:
        errors.append("mobagent.global_add_setting must be true")
    if mobagent.get("agent_loaded_certificate") is not True:
        errors.append("mobagent.agent_loaded_certificate must be true")

    browser = _required_mapping(data, "ssh_browser", errors)
    _validate_action_evidence(browser, root, errors, "ssh_browser")
    for key in ("same_parameters_sftp", "multiplex_mode", "real_connected_session", "sftp_browser_open"):
        if browser.get(key) is not True:
            errors.append(f"ssh_browser.{key} must be true")

    return MobaSmartCardReleaseEvidenceValidation(
        evidence_path=str(target_evidence_path),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def normalise_smartcard_provider(provider: str) -> str:
    text = safe.option_value(provider, "smart-card provider")
    lowered = text.lower()
    return CAPI_PROVIDER_ALIASES.get(lowered, text)


def _smartcard_profile_options(certificate_id: str, provider: str, add_to_mobagent: bool) -> dict[str, str]:
    options = {
        "smartcard_auth": "true",
        "smartcard_provider": provider,
        "smartcard_certificate_id": certificate_id,
    }
    if add_to_mobagent:
        options["add_smartcard_to_mobagent"] = "true"
        options["mobagent_smartcard"] = "true"
    return options


def _smartcard_gui_row(certificate: MobaSmartCardCertificate) -> MobaSmartCardGuiCertificateRow:
    return MobaSmartCardGuiCertificateRow(
        certificate_id=certificate.certificate_id,
        label=certificate.label,
        provider=certificate.provider,
        subject=certificate.subject,
        issuer=certificate.issuer,
        fingerprint_sha256=certificate.fingerprint_sha256,
        public_key_available=bool(certificate.public_key),
        source=certificate.source,
        actions=[
            "select-for-ssh-session",
            "add-to-mobagent",
            "remove-certificate",
            "export-openssh-public-key",
        ],
    )


def _replace_profile(profile: Profile, **changes: Any) -> Profile:
    data = profile.to_dict()
    data.update(changes)
    return Profile.from_dict(data)


def _normalise_certificate(certificate: MobaSmartCardCertificate) -> MobaSmartCardCertificate:
    return MobaSmartCardCertificate(
        certificate_id=safe.option_value(certificate.certificate_id, "certificate id"),
        label=safe.clean_text(certificate.label or certificate.certificate_id, "certificate label"),
        provider=normalise_smartcard_provider(certificate.provider),
        subject=safe.clean_text(certificate.subject, "certificate subject", allow_empty=True),
        issuer=safe.clean_text(certificate.issuer, "certificate issuer", allow_empty=True),
        public_key=safe.clean_text(certificate.public_key, "certificate public key", allow_empty=True),
        fingerprint_sha256=_optional_sha256(certificate.fingerprint_sha256, "certificate fingerprint_sha256"),
        source=safe.option_value(certificate.source or "manual", "certificate source"),
    )


def _copy_evidence_asset(source: Path, evidence_dir: Path, label: str, root: Path) -> str:
    resolved_source = source.expanduser()
    if not resolved_source.is_file():
        raise ValueError(f"{label} evidence file is missing: {resolved_source}")
    suffix = resolved_source.suffix if resolved_source.suffix else ".txt"
    target = evidence_dir / f"{label}{suffix}"
    if resolved_source.resolve() != target.resolve():
        shutil.copy2(resolved_source, target)
    return _relative_to_root(target, root)


def _relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _optional_sha256(value: str | None, label: str) -> str:
    if not value:
        return ""
    return _required_sha256(value, label)


def _required_sha256(value: str, label: str, errors: list[str] | None = None) -> str:
    try:
        text = safe.clean_text(str(value), label)
    except ValueError as exc:
        if errors is not None:
            errors.append(f"{label} is invalid: {exc}")
            return str(value)
        raise
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return text
    message = f"{label} must be a lowercase 64-character SHA-256 digest"
    if errors is not None:
        errors.append(message)
        return text
    raise ValueError(message)


def _required_mapping(data: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = data.get(key)
    if isinstance(value, dict):
        return value
    errors.append(f"{key} must be a JSON object")
    return {}


def _required_text(
    data: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str = "",
) -> str:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        try:
            return safe.clean_text(value, f"{prefix}{key}")
        except ValueError as exc:
            errors.append(f"{prefix}{key} is invalid: {exc}")
            return value
    errors.append(f"{prefix}{key} must be a non-empty string")
    return ""


def _validate_action_evidence(action: dict[str, Any], assets_dir: Path, errors: list[str], label: str) -> None:
    if action.get("status") != "passed":
        errors.append(f"{label}.status must be passed")
    command = _required_text(action, "command", errors, prefix=f"{label}.")
    if not command:
        errors.append(f"{label}.command must record the executed action")
    evidence_file = _required_text(action, "evidence_file", errors, prefix=f"{label}.")
    digest = _required_sha256(
        _required_text(action, "evidence_sha256", errors, prefix=f"{label}."),
        f"{label}.evidence_sha256",
        errors,
    )
    if evidence_file and digest:
        _validate_asset_hash(assets_dir, evidence_file, digest, errors, label)


def _validate_asset_hash(
    assets_dir: Path,
    evidence_file: str,
    expected_sha256: str,
    errors: list[str],
    label: str,
) -> None:
    try:
        asset = _resolve_evidence_asset(assets_dir, evidence_file)
    except ValueError as exc:
        errors.append(f"{label}.evidence_file is invalid: {exc}")
        return
    if not asset.exists():
        errors.append(f"{label}.evidence_file does not exist: {asset}")
        return
    if not asset.is_file():
        errors.append(f"{label}.evidence_file is not a file: {asset}")
        return
    actual = _sha256_path(asset)
    if actual != expected_sha256:
        errors.append(f"{label}.evidence_sha256 does not match {asset.name}")


def _resolve_evidence_asset(assets_dir: Path, evidence_file: str) -> Path:
    relative = Path(safe.path_arg(evidence_file, "evidence file"))
    if relative.is_absolute():
        raise ValueError("must be relative to assets_dir")
    root = assets_dir.resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise ValueError("must stay inside assets_dir")
    return target


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

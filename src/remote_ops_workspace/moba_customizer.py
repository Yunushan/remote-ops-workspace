from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
from base64 import b64decode
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import __version__
from . import command_safety as safe
from .file_safety import (
    chmod_best_effort,
    ensure_private_dir,
    write_bytes_atomic,
    write_json_atomic,
    write_text_atomic,
)
from .models import Profile
from .profile_validation import prepare_profile

ALLOWED_LOGO_SUFFIXES = {".bmp", ".ico", ".jpeg", ".jpg", ".png", ".svg"}
DEFAULT_WELCOME_MESSAGE = (
    "Welcome to Remote Ops Workspace. Select a saved session, use quick connect, "
    "or open the bundled profiles for your team."
)
DEFAULT_CUSTOMIZER_SETTINGS: dict[str, Any] = {
    "version": 1,
    "theme": "system",
    "portable_mode": True,
    "confirm_before_launch": True,
    "redact_audit_log": True,
    "gui_preset": "mobaxterm",
}
DEFAULT_CUSTOMIZER_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "allow_user_profiles": True,
    "allow_custom_commands": False,
    "allow_unsafe_proxy_command": False,
    "locked_settings": [],
}
MOBA_PROFESSIONAL_INSTALLER_BRANDING_SCHEMA = "row.moba-professional.installer-branding-plan.v1"
MOBA_PROFESSIONAL_POLICY_LOCK_SCHEMA = "row.moba-professional.policy-lock-plan.v1"
MOBA_PROFESSIONAL_UPDATE_CHANNEL_SCHEMA = "row.moba-professional.update-channel-plan.v1"
MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA = "row.moba-professional.update-manifest.v1"
MOBA_PROFESSIONAL_DEPLOYMENT_SCHEMA = "row.moba-professional.deployment-plan.v1"
MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA = "row.moba-professional.deployment-evidence.v1"
MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_BUNDLE_SCHEMA = "row.moba-professional.deployment-evidence-bundle.v1"
PROFESSIONAL_INSTALLER_TARGETS = ["windows-exe", "windows-msi"]
REQUIRED_POLICY_SURFACES = ["cli", "gui", "web", "profile-editor", "quick-connect", "launcher"]


@dataclass(slots=True)
class MobaProfessionalCustomizerPlan:
    output_dir: Path
    brand_name: str
    organization: str = ""
    welcome_message: str = DEFAULT_WELCOME_MESSAGE
    logo_path: Path | None = None
    settings: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_CUSTOMIZER_SETTINGS))
    policy: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_CUSTOMIZER_POLICY))
    profiles: list[Profile] = field(default_factory=list)
    force: bool = False


@dataclass(slots=True)
class MobaProfessionalCustomizerBundle:
    root: Path
    files: list[Path]
    manifest: dict[str, Any]
    sha256s: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "files": [str(path) for path in self.files],
            "manifest": self.manifest,
            "sha256s": self.sha256s,
        }


@dataclass(slots=True)
class MobaProfessionalInstallerBrandingPlan:
    schema: str
    brand_name: str
    organization: str
    version: str
    installer_targets: list[str]
    artifact_names: dict[str, str]
    product_name: str
    publisher: str
    logo_path: str
    required_metadata: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "brand_name": self.brand_name,
            "organization": self.organization,
            "version": self.version,
            "installer_targets": self.installer_targets,
            "artifact_names": self.artifact_names,
            "product_name": self.product_name,
            "publisher": self.publisher,
            "logo_path": self.logo_path,
            "required_metadata": self.required_metadata,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEnterprisePolicyLockPlan:
    schema: str
    locked_settings: list[dict[str, str]]
    enforcement_surfaces: list[str]
    blocked_user_controls: list[str]
    policy: dict[str, Any]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "locked_settings": self.locked_settings,
            "enforcement_surfaces": self.enforcement_surfaces,
            "blocked_user_controls": self.blocked_user_controls,
            "policy": self.policy,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEnterpriseUpdateChannelPlan:
    schema: str
    channel: str
    update_url: str
    interval_hours: int
    require_signature: bool
    public_key: str
    rollout_ring: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "channel": self.channel,
            "update_url": self.update_url,
            "interval_hours": self.interval_hours,
            "require_signature": self.require_signature,
            "public_key": self.public_key,
            "rollout_ring": self.rollout_ring,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaProfessionalDeploymentPlan:
    schema: str
    installer_branding: MobaProfessionalInstallerBrandingPlan
    policy_locks: MobaEnterprisePolicyLockPlan
    update_channel: MobaEnterpriseUpdateChannelPlan
    evidence_requirements: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "installer_branding": self.installer_branding.to_dict(),
            "policy_locks": self.policy_locks.to_dict(),
            "update_channel": self.update_channel.to_dict(),
            "evidence_requirements": self.evidence_requirements,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaProfessionalDeploymentEvidenceValidation:
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
class MobaProfessionalDeploymentEvidenceBundlePlan:
    schema: str
    out_dir: str
    evidence_path: str
    release_target: str
    brand_name: str
    organization: str
    version: str
    bundle_manifest_evidence_source: str
    installer_evidence_source: str
    policy_evidence_source: str
    update_evidence_source: str
    update_manifest_source: str
    update_manifest_assets_dir: str
    public_key: str
    channel: str
    bundle_command: str
    installer_command: str
    policy_command: str
    update_command: str
    bundle_manifest_sha256: str
    locked_settings: list[dict[str, str]]
    surfaces: dict[str, bool]
    sha256s_present: bool
    windows_exe_rebranded: bool
    windows_msi_rebranded: bool
    product_name_matches_brand: bool
    logo_applied: bool
    https_update_url: bool
    signature_verified: bool
    organization_channel: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "out_dir": self.out_dir,
            "evidence_path": self.evidence_path,
            "release_target": self.release_target,
            "brand_name": self.brand_name,
            "organization": self.organization,
            "version": self.version,
            "bundle_manifest_evidence_source": self.bundle_manifest_evidence_source,
            "installer_evidence_source": self.installer_evidence_source,
            "policy_evidence_source": self.policy_evidence_source,
            "update_evidence_source": self.update_evidence_source,
            "update_manifest_source": self.update_manifest_source,
            "update_manifest_assets_dir": self.update_manifest_assets_dir,
            "public_key": self.public_key,
            "channel": self.channel,
            "bundle_command": self.bundle_command,
            "installer_command": self.installer_command,
            "policy_command": self.policy_command,
            "update_command": self.update_command,
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "locked_settings": self.locked_settings,
            "surfaces": self.surfaces,
            "sha256s_present": self.sha256s_present,
            "windows_exe_rebranded": self.windows_exe_rebranded,
            "windows_msi_rebranded": self.windows_msi_rebranded,
            "product_name_matches_brand": self.product_name_matches_brand,
            "logo_applied": self.logo_applied,
            "https_update_url": self.https_update_url,
            "signature_verified": self.signature_verified,
            "organization_channel": self.organization_channel,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaProfessionalDeploymentEvidenceBundleResult:
    plan: MobaProfessionalDeploymentEvidenceBundlePlan
    evidence_path: str
    files: tuple[str, ...]
    validation: MobaProfessionalDeploymentEvidenceValidation
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
class MobaProfessionalUpdateManifestValidation:
    manifest_path: str
    assets_dir: str
    passed: bool
    errors: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_path": self.manifest_path,
            "assets_dir": self.assets_dir,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


def build_moba_professional_customizer_plan(
    output_dir: Path,
    *,
    brand_name: str,
    organization: str = "",
    welcome_message: str | None = None,
    logo_path: Path | None = None,
    settings_path: Path | None = None,
    profiles_path: Path | None = None,
    policy_path: Path | None = None,
    lock_settings: list[str] | None = None,
    force: bool = False,
) -> MobaProfessionalCustomizerPlan:
    brand = safe.clean_text(brand_name, "brand name").strip()
    if not brand:
        raise ValueError("brand name is required")
    organization = safe.clean_text(organization, "organization", allow_empty=True).strip()
    welcome = _clean_multiline_text(welcome_message or DEFAULT_WELCOME_MESSAGE, "welcome message")
    logo = _validate_logo_path(logo_path)
    settings = _load_json_object(settings_path, "settings") if settings_path else dict(DEFAULT_CUSTOMIZER_SETTINGS)
    policy = _policy_with_locked_settings(
        _load_json_object(policy_path, "policy") if policy_path else dict(DEFAULT_CUSTOMIZER_POLICY),
        lock_settings or [],
    )
    profiles = _load_profiles(profiles_path) if profiles_path else []
    return MobaProfessionalCustomizerPlan(
        output_dir=output_dir,
        brand_name=brand,
        organization=organization,
        welcome_message=welcome,
        logo_path=logo,
        settings=settings,
        policy=policy,
        profiles=profiles,
        force=force,
    )


def build_professional_deployment_plan(
    *,
    brand_name: str,
    update_url: str,
    update_public_key: str,
    organization: str = "",
    version: str = __version__,
    logo_path: Path | None = None,
    policy_path: Path | None = None,
    lock_settings: list[str] | None = None,
    update_channel: str = "stable",
    update_interval_hours: int = 24,
    rollout_ring: str = "enterprise",
    enforcement_surfaces: list[str] | None = None,
) -> MobaProfessionalDeploymentPlan:
    installer = build_installer_branding_plan(
        brand_name=brand_name,
        organization=organization,
        version=version,
        logo_path=logo_path,
    )
    policy = build_enterprise_policy_lock_plan(
        policy_path=policy_path,
        lock_settings=lock_settings or [],
        enforcement_surfaces=enforcement_surfaces or REQUIRED_POLICY_SURFACES,
    )
    channel = build_enterprise_update_channel_plan(
        update_url=update_url,
        public_key=update_public_key,
        channel=update_channel,
        interval_hours=update_interval_hours,
        rollout_ring=rollout_ring,
    )
    return MobaProfessionalDeploymentPlan(
        schema=MOBA_PROFESSIONAL_DEPLOYMENT_SCHEMA,
        installer_branding=installer,
        policy_locks=policy,
        update_channel=channel,
        evidence_requirements=[
            "Windows EXE installer branding proof",
            "Windows MSI installer branding proof",
            "locked setting enforcement for CLI, GUI, Web, profile editor, quick connect and launcher",
            "signed HTTPS organization update channel proof",
            "bundle manifest and SHA256SUMS proof",
        ],
        notes=[
            "MobaXterm Professional-style deployment depth plan for branded installers, hard policy locks and organization update channels.",
            "Release evidence must prove the generated native installers and UI surfaces consume these contracts.",
        ],
    )


def build_installer_branding_plan(
    *,
    brand_name: str,
    organization: str = "",
    version: str = __version__,
    logo_path: Path | None = None,
) -> MobaProfessionalInstallerBrandingPlan:
    brand = safe.clean_text(brand_name, "brand name").strip()
    if not brand:
        raise ValueError("brand name is required")
    org = safe.clean_text(organization, "organization", allow_empty=True).strip() or brand
    version_text = safe.option_value(version, "deployment version")
    logo = _validate_logo_path(logo_path)
    slug = _artifact_slug(brand)
    return MobaProfessionalInstallerBrandingPlan(
        schema=MOBA_PROFESSIONAL_INSTALLER_BRANDING_SCHEMA,
        brand_name=brand,
        organization=org,
        version=version_text,
        installer_targets=PROFESSIONAL_INSTALLER_TARGETS.copy(),
        artifact_names={
            "windows-exe": f"{slug}-{version_text}-setup.exe",
            "windows-msi": f"{slug}-{version_text}.msi",
        },
        product_name=f"{brand} Remote Ops Workspace",
        publisher=org,
        logo_path=str(logo) if logo is not None else "",
        required_metadata=["ProductName", "Publisher", "DisplayName", "Logo", "WelcomeMessage"],
        notes=[
            "Professional Customizer-style installer branding must be applied to both EXE and MSI artifacts.",
            "The plan is release-evidence backed; actual native installer metadata must be verified before parity is accepted.",
        ],
    )


def build_enterprise_policy_lock_plan(
    *,
    policy_path: Path | None = None,
    lock_settings: list[str] | None = None,
    enforcement_surfaces: list[str] | None = None,
) -> MobaEnterprisePolicyLockPlan:
    policy = _policy_with_locked_settings(
        _load_json_object(policy_path, "policy") if policy_path else dict(DEFAULT_CUSTOMIZER_POLICY),
        lock_settings or [],
    )
    locked = policy.get("locked_settings", [])
    if not isinstance(locked, list) or not locked:
        raise ValueError("enterprise deployment requires at least one locked setting")
    surfaces = _normalise_policy_surfaces(enforcement_surfaces or REQUIRED_POLICY_SURFACES)
    return MobaEnterprisePolicyLockPlan(
        schema=MOBA_PROFESSIONAL_POLICY_LOCK_SCHEMA,
        locked_settings=locked,
        enforcement_surfaces=surfaces,
        blocked_user_controls=[f"{surface}:edit-locked-setting" for surface in surfaces],
        policy=policy,
        notes=[
            "Hard lock enforcement must disable editing locked values in every declared UI and launch surface.",
            "Release evidence must prove CLI, GUI, Web, profile editor, quick connect and launcher enforcement.",
        ],
    )


def build_enterprise_update_channel_plan(
    *,
    update_url: str,
    public_key: str,
    channel: str = "stable",
    interval_hours: int = 24,
    rollout_ring: str = "enterprise",
) -> MobaEnterpriseUpdateChannelPlan:
    url = safe.clean_text(update_url, "update url")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("enterprise update url must be HTTPS")
    if interval_hours <= 0:
        raise ValueError("update interval must be positive")
    key = _validate_update_public_key(public_key)
    return MobaEnterpriseUpdateChannelPlan(
        schema=MOBA_PROFESSIONAL_UPDATE_CHANNEL_SCHEMA,
        channel=safe.option_value(channel, "update channel"),
        update_url=url,
        interval_hours=interval_hours,
        require_signature=True,
        public_key=key,
        rollout_ring=safe.option_value(rollout_ring, "rollout ring"),
        notes=[
            "Organization update channels must use HTTPS and signed update manifests.",
            "Release evidence must prove the configured update channel was checked and signature validation passed.",
        ],
    )


def build_professional_deployment_evidence_bundle_plan(
    deployment: MobaProfessionalDeploymentPlan,
    *,
    out_dir: Path,
    bundle_manifest_evidence: Path,
    installer_evidence: Path,
    policy_evidence: Path,
    update_evidence: Path,
    update_manifest: Path,
    bundle_manifest_sha256: str,
    update_manifest_assets_dir: Path | None = None,
    release_target: str = "local-bundle",
    bundle_command: str = "",
    installer_command: str = "",
    policy_command: str = "",
    update_command: str = "",
    surfaces: dict[str, bool] | None = None,
    sha256s_present: bool = False,
    windows_exe_rebranded: bool = False,
    windows_msi_rebranded: bool = False,
    product_name_matches_brand: bool = False,
    logo_applied: bool = False,
    https_update_url: bool = False,
    signature_verified: bool = False,
    organization_channel: bool = False,
) -> MobaProfessionalDeploymentEvidenceBundlePlan:
    root = Path(out_dir).expanduser()
    manifest = Path(update_manifest).expanduser()
    surface_state = {surface: False for surface in REQUIRED_POLICY_SURFACES}
    for surface in deployment.policy_locks.enforcement_surfaces:
        surface_state.setdefault(surface, False)
    for surface, passed in (surfaces or {}).items():
        surface_state[safe.option_value(surface, "policy evidence surface").strip().lower()] = bool(passed)
    clean_bundle_sha = _required_sha256(str(bundle_manifest_sha256), "bundle manifest sha256")
    notes = [
        "Bundle plan writes Professional deployment release evidence from supplied installer, policy and update-channel proof files.",
        "Production parity requires the supplied evidence files to come from real branded Windows installers, runtime policy-lock checks and a hosted organization update channel.",
    ]
    if not all(
        (
            sha256s_present,
            windows_exe_rebranded,
            windows_msi_rebranded,
            product_name_matches_brand,
            logo_applied,
            https_update_url,
            signature_verified,
            organization_channel,
            all(surface_state.get(surface) is True for surface in REQUIRED_POLICY_SURFACES),
        )
    ):
        notes.append("Deployment evidence flags are incomplete; the verifier will fail until real release proof is asserted.")
    brand = deployment.installer_branding.brand_name
    channel = deployment.update_channel
    return MobaProfessionalDeploymentEvidenceBundlePlan(
        schema=MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_BUNDLE_SCHEMA,
        out_dir=str(root),
        evidence_path=str(root / "moba-professional-deployment.json"),
        release_target=safe.clean_text(release_target, "release target"),
        brand_name=brand,
        organization=deployment.installer_branding.organization,
        version=deployment.installer_branding.version,
        bundle_manifest_evidence_source=str(Path(bundle_manifest_evidence).expanduser()),
        installer_evidence_source=str(Path(installer_evidence).expanduser()),
        policy_evidence_source=str(Path(policy_evidence).expanduser()),
        update_evidence_source=str(Path(update_evidence).expanduser()),
        update_manifest_source=str(manifest),
        update_manifest_assets_dir=str(Path(update_manifest_assets_dir).expanduser() if update_manifest_assets_dir else manifest.parent),
        public_key=channel.public_key,
        channel=channel.channel,
        bundle_command=safe.clean_text(bundle_command or f"row customizer build --brand-name {brand}", "bundle command"),
        installer_command=safe.clean_text(installer_command or "windows installer metadata smoke", "installer command"),
        policy_command=safe.clean_text(policy_command or "enterprise policy lock smoke", "policy command"),
        update_command=safe.clean_text(
            update_command or f"row customizer update-verify --manifest {manifest.name} --public-key {channel.public_key}",
            "update command",
        ),
        bundle_manifest_sha256=clean_bundle_sha,
        locked_settings=[dict(item) for item in deployment.policy_locks.locked_settings],
        surfaces=surface_state,
        sha256s_present=bool(sha256s_present),
        windows_exe_rebranded=bool(windows_exe_rebranded),
        windows_msi_rebranded=bool(windows_msi_rebranded),
        product_name_matches_brand=bool(product_name_matches_brand),
        logo_applied=bool(logo_applied),
        https_update_url=bool(https_update_url),
        signature_verified=bool(signature_verified),
        organization_channel=bool(organization_channel),
        notes=notes,
    )


def write_professional_deployment_evidence_bundle(
    plan: MobaProfessionalDeploymentEvidenceBundlePlan,
) -> MobaProfessionalDeploymentEvidenceBundleResult:
    if plan.schema != MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_BUNDLE_SCHEMA:
        raise ValueError(
            "professional deployment evidence bundle schema must be "
            f"{MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_BUNDLE_SCHEMA}"
        )
    root = Path(plan.out_dir)
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {
        "bundle_manifest": _copy_evidence_asset(
            Path(plan.bundle_manifest_evidence_source),
            evidence_dir,
            "bundle-manifest",
            root,
        ),
        "installer_branding": _copy_evidence_asset(
            Path(plan.installer_evidence_source),
            evidence_dir,
            "installer-branding",
            root,
        ),
        "policy_locks": _copy_evidence_asset(
            Path(plan.policy_evidence_source),
            evidence_dir,
            "policy-locks",
            root,
        ),
        "update_channel": _copy_evidence_asset(
            Path(plan.update_evidence_source),
            evidence_dir,
            "update-channel",
            root,
        ),
        "update_manifest": _copy_evidence_asset(
            Path(plan.update_manifest_source),
            evidence_dir,
            "update-manifest",
            root,
        ),
    }
    copied_artifacts = _copy_update_manifest_artifacts(
        Path(plan.update_manifest_source),
        Path(plan.update_manifest_assets_dir),
        root,
    )
    payload = {
        "schema": MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA,
        "release_target": plan.release_target,
        "brand_name": plan.brand_name,
        "version": plan.version,
        "bundle_manifest": {
            "status": "passed",
            "command": plan.bundle_command,
            "evidence_file": copied["bundle_manifest"],
            "evidence_sha256": _sha256(root / copied["bundle_manifest"]),
            "manifest_sha256": plan.bundle_manifest_sha256,
            "sha256s_present": plan.sha256s_present,
        },
        "installer_branding": {
            "status": "passed",
            "command": plan.installer_command,
            "evidence_file": copied["installer_branding"],
            "evidence_sha256": _sha256(root / copied["installer_branding"]),
            "windows_exe_rebranded": plan.windows_exe_rebranded,
            "windows_msi_rebranded": plan.windows_msi_rebranded,
            "product_name_matches_brand": plan.product_name_matches_brand,
            "logo_applied": plan.logo_applied,
        },
        "policy_locks": {
            "status": "passed",
            "command": plan.policy_command,
            "evidence_file": copied["policy_locks"],
            "evidence_sha256": _sha256(root / copied["policy_locks"]),
            "locked_settings": plan.locked_settings,
            "surfaces": plan.surfaces,
        },
        "update_channel": {
            "status": "passed",
            "command": plan.update_command,
            "evidence_file": copied["update_channel"],
            "evidence_sha256": _sha256(root / copied["update_channel"]),
            "https_update_url": plan.https_update_url,
            "signature_verified": plan.signature_verified,
            "organization_channel": plan.organization_channel,
            "manifest_file": copied["update_manifest"],
            "manifest_sha256": _sha256(root / copied["update_manifest"]),
            "public_key": plan.public_key,
            "channel": plan.channel,
            "organization": plan.organization,
        },
    }
    target = Path(plan.evidence_path)
    write_json_atomic(target, payload)
    validation = validate_professional_deployment_evidence(target, assets_dir=root)
    files = tuple(
        sorted(
            {
                *(copied.values()),
                *copied_artifacts,
                _relative_to_root(target, root),
            }
        )
    )
    return MobaProfessionalDeploymentEvidenceBundleResult(
        plan=plan,
        evidence_path=str(target),
        files=files,
        validation=validation,
        notes=plan.notes,
    )


def validate_professional_deployment_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobaProfessionalDeploymentEvidenceValidation:
    target_evidence_path = Path(evidence_path)
    root = Path(assets_dir) if assets_dir is not None else target_evidence_path.parent
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "schema": "",
        "release_target": "",
        "brand_name": "",
        "surface_count": 0,
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
    if schema != MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA:
        errors.append(f"schema must be {MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA}")
    summary["release_target"] = _required_text(data, "release_target", errors)
    summary["brand_name"] = _required_text(data, "brand_name", errors)
    _required_text(data, "version", errors)

    bundle = _required_mapping(data, "bundle_manifest", errors)
    _validate_action_evidence(bundle, root, errors, "bundle_manifest")
    _required_sha256(_required_text(bundle, "manifest_sha256", errors, prefix="bundle_manifest."), "bundle_manifest.manifest_sha256", errors)
    if bundle.get("sha256s_present") is not True:
        errors.append("bundle_manifest.sha256s_present must be true")

    installer = _required_mapping(data, "installer_branding", errors)
    _validate_action_evidence(installer, root, errors, "installer_branding")
    for key in ("windows_exe_rebranded", "windows_msi_rebranded", "product_name_matches_brand", "logo_applied"):
        if installer.get(key) is not True:
            errors.append(f"installer_branding.{key} must be true")

    policy = _required_mapping(data, "policy_locks", errors)
    _validate_action_evidence(policy, root, errors, "policy_locks")
    locked_settings = policy.get("locked_settings")
    if not isinstance(locked_settings, list) or not locked_settings:
        errors.append("policy_locks.locked_settings must be a non-empty list")
    surfaces = policy.get("surfaces")
    if not isinstance(surfaces, dict):
        errors.append("policy_locks.surfaces must be an object")
        surfaces = {}
    summary["surface_count"] = len(surfaces)
    for surface in REQUIRED_POLICY_SURFACES:
        if surfaces.get(surface) is not True:
            errors.append(f"policy_locks.surfaces.{surface} must be true")

    channel = _required_mapping(data, "update_channel", errors)
    _validate_action_evidence(channel, root, errors, "update_channel")
    for key in ("https_update_url", "signature_verified", "organization_channel"):
        if channel.get(key) is not True:
            errors.append(f"update_channel.{key} must be true")
    manifest_file = _required_text(channel, "manifest_file", errors, prefix="update_channel.")
    manifest_digest = _required_sha256(
        _required_text(channel, "manifest_sha256", errors, prefix="update_channel."),
        "update_channel.manifest_sha256",
        errors,
    )
    public_key = _required_text(channel, "public_key", errors, prefix="update_channel.")
    channel_name = _required_text(channel, "channel", errors, prefix="update_channel.")
    organization = str(channel.get("organization") or "")
    if manifest_file and manifest_digest:
        _validate_asset_hash(root, manifest_file, manifest_digest, errors, "update_channel.manifest_file")
    if manifest_file and public_key and channel_name:
        try:
            manifest_path = _resolve_evidence_asset(root, manifest_file)
        except ValueError as exc:
            errors.append(f"update_channel.manifest_file is invalid: {exc}")
        else:
            manifest_result = validate_professional_update_manifest(
                manifest_path,
                public_key=public_key,
                expected_channel=channel_name,
                expected_organization=organization,
                assets_dir=root,
            )
            summary["update_manifest"] = manifest_result.summary
            if not manifest_result.passed:
                errors.extend(f"update_channel.manifest: {error}" for error in manifest_result.errors)

    return MobaProfessionalDeploymentEvidenceValidation(
        evidence_path=str(target_evidence_path),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def validate_professional_update_manifest(
    manifest_path: Path,
    *,
    public_key: str,
    expected_channel: str = "",
    expected_organization: str = "",
    assets_dir: Path | None = None,
) -> MobaProfessionalUpdateManifestValidation:
    target_manifest_path = Path(manifest_path)
    root = Path(assets_dir) if assets_dir is not None else target_manifest_path.parent
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "schema": "",
        "channel": "",
        "organization": "",
        "version": "",
        "artifact_count": 0,
        "signature_algorithm": "",
    }
    try:
        data = json.loads(target_manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"update manifest cannot be read: {exc}")
        data = {}
    except json.JSONDecodeError as exc:
        errors.append(f"update manifest is not valid JSON: {exc}")
        data = {}
    if not isinstance(data, dict):
        errors.append("update manifest root must be a JSON object")
        data = {}

    schema = str(data.get("schema") or data.get("schema_version") or "")
    summary["schema"] = schema
    if schema != MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA:
        errors.append(f"schema must be {MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA}")
    channel = _required_text(data, "channel", errors)
    organization = _required_text(data, "organization", errors)
    version = _required_text(data, "version", errors)
    summary["channel"] = channel
    summary["organization"] = organization
    summary["version"] = version
    if expected_channel and channel != expected_channel:
        errors.append(f"channel must match expected channel {expected_channel}")
    if expected_organization and organization != expected_organization:
        errors.append(f"organization must match expected organization {expected_organization}")

    update_url = str(data.get("update_url") or "")
    if update_url:
        _require_https_url(update_url, "update_url", errors)

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
        artifacts = []
    summary["artifact_count"] = len(artifacts)
    seen_artifacts: set[tuple[str, str]] = set()
    for index, raw_artifact in enumerate(artifacts, start=1):
        label = f"artifacts[{index}]"
        if not isinstance(raw_artifact, dict):
            errors.append(f"{label} must be a JSON object")
            continue
        target = _required_text(raw_artifact, "target", errors, prefix=f"{label}.")
        name = _required_text(raw_artifact, "name", errors, prefix=f"{label}.")
        url = _required_text(raw_artifact, "url", errors, prefix=f"{label}.")
        digest = _required_sha256(
            _required_text(raw_artifact, "sha256", errors, prefix=f"{label}."),
            f"{label}.sha256",
            errors,
        )
        if url:
            _require_https_url(url, f"{label}.url", errors)
        size = raw_artifact.get("size_bytes")
        if not isinstance(size, int) or size < 0:
            errors.append(f"{label}.size_bytes must be a non-negative integer")
        key = (target, name)
        if key in seen_artifacts:
            errors.append(f"{label} duplicates target/name pair {target}/{name}")
        seen_artifacts.add(key)
        artifact_file = str(raw_artifact.get("file") or "")
        if artifact_file and digest:
            _validate_asset_hash(root, artifact_file, digest, errors, f"{label}.file")

    signature = _required_mapping(data, "signature", errors)
    algorithm = _required_text(signature, "algorithm", errors, prefix="signature.")
    signature_value = _required_text(signature, "value", errors, prefix="signature.")
    payload_digest = _required_sha256(
        _required_text(signature, "payload_sha256", errors, prefix="signature."),
        "signature.payload_sha256",
        errors,
    )
    summary["signature_algorithm"] = algorithm
    payload = canonical_update_manifest_payload(data)
    actual_payload_digest = hashlib.sha256(payload).hexdigest()
    if payload_digest and actual_payload_digest != payload_digest:
        errors.append("signature.payload_sha256 does not match canonical manifest payload")
    if algorithm and signature_value and public_key and not _verify_update_manifest_signature(
        algorithm,
        public_key=public_key,
        signature_value=signature_value,
        payload=payload,
        errors=errors,
    ):
        errors.append("signature verification failed")

    return MobaProfessionalUpdateManifestValidation(
        manifest_path=str(target_manifest_path),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def canonical_update_manifest_payload(data: dict[str, Any]) -> bytes:
    payload = dict(data)
    payload.pop("signature", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def write_moba_professional_customizer_bundle(
    plan: MobaProfessionalCustomizerPlan,
) -> MobaProfessionalCustomizerBundle:
    root = plan.output_dir
    if root.exists() and not root.is_dir():
        raise ValueError(f"customizer output must be a directory: {root}")
    if root.exists() and any(root.iterdir()) and not plan.force:
        raise FileExistsError(f"customizer output is not empty: {root}; use --force to overwrite bundle files")

    ensure_private_dir(root)
    written: list[Path] = []

    logo_relative = ""
    if plan.logo_path is not None:
        logo_relative = f"branding/logo{plan.logo_path.suffix.lower()}"
        logo_target = root / logo_relative
        write_bytes_atomic(logo_target, plan.logo_path.read_bytes())
        written.append(logo_target)

    branding = {
        "schema_version": 1,
        "brand_name": plan.brand_name,
        "organization": plan.organization,
        "logo": logo_relative,
        "welcome_message_file": "welcome.txt",
        "source": "row customizer build",
    }
    settings = dict(plan.settings)
    settings["branding"] = {
        "brand_name": plan.brand_name,
        "organization": plan.organization,
        "logo": logo_relative,
    }
    profiles = {
        "version": 1,
        "profiles": [profile.to_dict() for profile in plan.profiles],
        "group_defaults": {},
    }

    written.extend(
        _write_payloads(
            root,
            {
                "branding/branding.json": branding,
                "config/settings.json": settings,
                "config/policy.json": plan.policy,
                "config/profiles.json": profiles,
            },
        )
    )
    written.append(_write_text(root / "welcome.txt", plan.welcome_message.rstrip() + "\n"))
    written.append(_write_text(root / "install/README.txt", _install_readme(plan)))
    written.append(_write_text(root / "install/apply-enterprise-bundle.ps1", _powershell_apply_script()))
    posix_script = _write_text(root / "install/apply-enterprise-bundle.sh", _posix_apply_script())
    chmod_best_effort(
        posix_script,
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH,
    )
    written.append(posix_script)

    manifest_files = _file_records(root, written)
    manifest = {
        "schema_version": 1,
        "generated_by": "remote-ops-workspace moba professional customizer",
        "project_version": __version__,
        "brand_name": plan.brand_name,
        "organization": plan.organization,
        "profile_count": len(plan.profiles),
        "locked_setting_count": len(plan.policy.get("locked_settings", [])),
        "files": manifest_files,
    }
    manifest_path = root / "manifest.json"
    write_json_atomic(manifest_path, manifest)
    written.append(manifest_path)

    sha256s = _sha256s(root, written)
    sums_path = root / "SHA256SUMS.txt"
    lines = [f"{digest}  {relative}" for relative, digest in sorted(sha256s.items())]
    write_text_atomic(sums_path, "\n".join(lines) + "\n")
    written.append(sums_path)

    return MobaProfessionalCustomizerBundle(
        root=root,
        files=sorted(written, key=lambda path: _relative(path, root)),
        manifest=manifest,
        sha256s=sha256s,
    )


def _write_payloads(root: Path, payloads: dict[str, dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    for relative, payload in payloads.items():
        path = root / relative
        write_json_atomic(path, payload)
        paths.append(path)
    return paths


def _write_text(path: Path, text: str) -> Path:
    write_text_atomic(path, text)
    return path


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} JSON must be an object: {path}")
    return data


def _load_profiles(path: Path) -> list[Profile]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        raw_profiles = data.get("profiles", [])
    elif isinstance(data, list):
        raw_profiles = data
    else:
        raise ValueError(f"profiles JSON must be an object or list: {path}")
    if not isinstance(raw_profiles, list):
        raise ValueError(f"profiles JSON requires a profiles list: {path}")
    profiles: list[Profile] = []
    for index, item in enumerate(raw_profiles, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"profile entry {index} must be an object")
        profiles.append(prepare_profile(Profile.from_dict(item)))
    return profiles


def _policy_with_locked_settings(policy: dict[str, Any], lock_settings: list[str]) -> dict[str, Any]:
    merged = dict(DEFAULT_CUSTOMIZER_POLICY)
    merged.update(policy)
    existing = merged.get("locked_settings", [])
    if not isinstance(existing, list):
        raise ValueError("policy locked_settings must be a list")
    locked: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in existing:
        if not isinstance(item, dict) or "key" not in item or "value" not in item:
            raise ValueError("policy locked_settings entries must contain key and value")
        key = safe.option_value(str(item["key"]), "locked setting key")
        value = safe.clean_text(str(item["value"]), "locked setting value", allow_empty=True)
        if key in seen:
            raise ValueError(f"duplicate locked setting: {key}")
        locked.append({"key": key, "value": value})
        seen.add(key)
    for item in lock_settings:
        if "=" not in item:
            raise ValueError(f"locked setting must be key=value: {item}")
        key, value = item.split("=", 1)
        key = safe.option_value(key.strip(), "locked setting key")
        value = safe.clean_text(value, "locked setting value", allow_empty=True)
        if key in seen:
            raise ValueError(f"duplicate locked setting: {key}")
        locked.append({"key": key, "value": value})
        seen.add(key)
    merged["locked_settings"] = locked
    merged["schema_version"] = int(merged.get("schema_version", 1))
    return merged


def _validate_logo_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if not path.exists() or not path.is_file():
        raise ValueError(f"logo file does not exist: {path}")
    if path.suffix.lower() not in ALLOWED_LOGO_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_LOGO_SUFFIXES))
        raise ValueError(f"logo file must use one of: {allowed}")
    return path


def _clean_multiline_text(value: str, label: str) -> str:
    text = str(value)
    if not text:
        raise ValueError(f"{label} is required")
    for char in text:
        codepoint = ord(char)
        if codepoint < 32 and char not in "\n\r\t":
            raise ValueError(f"{label} contains control characters")
        if codepoint == 127:
            raise ValueError(f"{label} contains control characters")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _artifact_slug(brand_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", brand_name.lower()).strip("-")
    return slug or "remote-ops-workspace"


def _normalise_policy_surfaces(surfaces: list[str]) -> list[str]:
    normalised: list[str] = []
    seen: set[str] = set()
    for item in surfaces:
        surface = safe.option_value(item, "policy enforcement surface").strip().lower()
        if not surface:
            raise ValueError("policy enforcement surface is required")
        if surface not in seen:
            normalised.append(surface)
            seen.add(surface)
    if not normalised:
        raise ValueError("at least one policy enforcement surface is required")
    return normalised


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


def _copy_evidence_asset(source: Path, evidence_dir: Path, label: str, root: Path) -> str:
    resolved_source = source.expanduser()
    if not resolved_source.is_file():
        raise ValueError(f"{label} evidence file is missing: {resolved_source}")
    suffix = resolved_source.suffix if resolved_source.suffix else ".txt"
    target = evidence_dir / f"{label}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if resolved_source.resolve() != target.resolve():
        shutil.copy2(resolved_source, target)
    return _relative_to_root(target, root)


def _copy_update_manifest_artifacts(manifest_path: Path, source_assets_dir: Path, root: Path) -> list[str]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"update manifest cannot be read for artifact copy: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"update manifest is not valid JSON for artifact copy: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("update manifest root must be a JSON object for artifact copy")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    copied: list[str] = []
    for index, raw_artifact in enumerate(artifacts, start=1):
        if not isinstance(raw_artifact, dict):
            continue
        artifact_file = str(raw_artifact.get("file") or "")
        if not artifact_file:
            continue
        try:
            source = _resolve_evidence_asset(source_assets_dir, artifact_file)
            target = _resolve_evidence_asset(root, artifact_file)
        except ValueError as exc:
            raise ValueError(f"update manifest artifacts[{index}].file is invalid: {exc}") from exc
        if not source.is_file():
            raise ValueError(f"update manifest artifact file is missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        copied.append(_relative_to_root(target, root))
    return copied


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
    actual = _sha256(asset)
    if actual != expected_sha256:
        errors.append(f"{label}.evidence_sha256 does not match {asset.name}")


def _require_https_url(value: str, label: str, errors: list[str]) -> None:
    try:
        url = safe.clean_text(value, label)
    except ValueError as exc:
        errors.append(f"{label} is invalid: {exc}")
        return
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append(f"{label} must be an HTTPS URL")


def _verify_update_manifest_signature(
    algorithm: str,
    *,
    public_key: str,
    signature_value: str,
    payload: bytes,
    errors: list[str],
) -> bool:
    normalised = algorithm.strip().lower()
    if normalised == "ed25519":
        return _verify_ed25519_signature(public_key, signature_value, payload, errors)
    errors.append("signature.algorithm must be ed25519")
    return False


def _validate_update_public_key(public_key: str) -> str:
    key = safe.clean_text(public_key, "update public key").strip()
    if not key.startswith("ed25519:"):
        raise ValueError("update public key must use ed25519:<base64-raw-public-key>")
    try:
        key_bytes = b64decode(key.split(":", 1)[1], validate=True)
    except Exception as exc:  # noqa: BLE001 - malformed deployment input.
        raise ValueError(f"update public key is not valid base64: {exc}") from exc
    if len(key_bytes) != 32:
        raise ValueError("ed25519 update public key must contain 32 raw bytes")
    return key


def _verify_ed25519_signature(
    public_key: str,
    signature_value: str,
    payload: bytes,
    errors: list[str],
) -> bool:
    try:
        public_key = _validate_update_public_key(public_key)
    except ValueError as exc:
        errors.append(str(exc))
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:  # noqa: BLE001 - optional dependency should fail closed.
        errors.append(f"cryptography is required for ed25519 update signatures: {exc}")
        return False
    try:
        key_bytes = b64decode(public_key.split(":", 1)[1], validate=True)
        signature_bytes = b64decode(signature_value, validate=True)
        Ed25519PublicKey.from_public_bytes(key_bytes).verify(signature_bytes, payload)
    except InvalidSignature:
        return False
    except Exception as exc:  # noqa: BLE001 - malformed signature/key are validation errors.
        errors.append(f"ed25519 signature material is invalid: {exc}")
        return False
    return True


def _resolve_evidence_asset(assets_dir: Path, evidence_file: str) -> Path:
    relative = Path(safe.path_arg(evidence_file, "evidence file"))
    if relative.is_absolute():
        raise ValueError("must be relative to assets_dir")
    root = assets_dir.resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise ValueError("must stay inside assets_dir")
    return target


def _relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _file_records(root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": _relative(path, root),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(paths, key=lambda item: _relative(item, root))
    ]


def _sha256s(root: Path, paths: list[Path]) -> dict[str, str]:
    return {_relative(path, root): _sha256(path) for path in paths}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _install_readme(plan: MobaProfessionalCustomizerPlan) -> str:
    return (
        f"{plan.brand_name} Remote Ops Workspace enterprise customization bundle\n\n"
        "Contents:\n"
        "- branding/branding.json and optional branding/logo.*\n"
        "- config/settings.json for default application settings\n"
        "- config/policy.json for locked enterprise policy values\n"
        "- config/profiles.json for seeded connection profiles\n"
        "- welcome.txt for the first-run welcome message\n"
        "- SHA256SUMS.txt and manifest.json for release evidence\n\n"
        "Run apply-enterprise-bundle.ps1 on Windows or apply-enterprise-bundle.sh on POSIX hosts.\n"
        "Set ROW_HOME first to apply into a portable workspace directory.\n"
    )


def _powershell_apply_script() -> str:
    return """$ErrorActionPreference = "Stop"
$BundleRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Target = if ($env:ROW_HOME) { $env:ROW_HOME } else { Join-Path $env:APPDATA "RemoteOpsWorkspace" }
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item -Force (Join-Path $BundleRoot "config/settings.json") (Join-Path $Target "settings.json")
Copy-Item -Force (Join-Path $BundleRoot "config/profiles.json") (Join-Path $Target "profiles.json")
Copy-Item -Force (Join-Path $BundleRoot "config/policy.json") (Join-Path $Target "policy.json")
Copy-Item -Force (Join-Path $BundleRoot "welcome.txt") (Join-Path $Target "welcome.txt")
Write-Host "Applied Remote Ops Workspace enterprise bundle to $Target"
"""


def _posix_apply_script() -> str:
    return """#!/usr/bin/env sh
set -eu
bundle_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
target="${ROW_HOME:-${HOME}/.config/remote-ops-workspace}"
mkdir -p "$target"
cp "$bundle_root/config/settings.json" "$target/settings.json"
cp "$bundle_root/config/profiles.json" "$target/profiles.json"
cp "$bundle_root/config/policy.json" "$target/policy.json"
cp "$bundle_root/welcome.txt" "$target/welcome.txt"
printf 'Applied Remote Ops Workspace enterprise bundle to %s\n' "$target"
"""

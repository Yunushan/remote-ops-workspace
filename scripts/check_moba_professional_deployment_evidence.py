from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import struct
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for location in (ROOT, SRC):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace import update_channel  # noqa: E402
from remote_ops_workspace.moba_customizer import (  # noqa: E402
    MobaProfessionalDeploymentEvidenceValidation,
    build_installer_branding_plan,
    validate_professional_deployment_evidence,
)
from scripts.check_mobaxterm_parity_evidence import (  # noqa: E402
    PROFESSIONAL_POLICY_SURFACES,
    capture_release_identity,
)
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    secure_regular_file,
    sha256_file,
    valid_sha256,
)

INSTALLER_CAPTURE_SCHEMA = "row.moba-professional.windows-installers.v1"
POLICY_CAPTURE_SCHEMA = "row.moba-professional.policy-surfaces.v1"
STOCK_INSTALLER_IDS = {
    "00000000-0000-0000-0000-000000000000",
    "5C887096-F4E5-4AB8-8D6F-65052D08D284",
    "8F8A21B4-6E48-4B1A-9F5D-B9373E1807D0",
}


def read_small(path: Path, label: str) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError(f"{label} exceeds 1 MiB")
    return data


def decode_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def read_object(path: Path, label: str) -> dict[str, Any]:
    return decode_object(read_small(path, label), label)


def attachment(root: Path, ref: Any, label: str) -> Path:
    if not isinstance(ref, dict):
        raise ValueError(f"{label} requires a SHA-256 attachment")
    return bound_evidence_file(root, ref.get("evidence_file"), ref.get("evidence_sha256"), label)


def verify_native_formats(exe: Path, msi: Path, *, icon_offset: Any, icon: bytes) -> None:
    with exe.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ValueError("reviewed Windows EXE must be a PE executable")
        stream.seek(struct.unpack_from("<I", header, 60)[0])
        pe = stream.read(24)
        if len(pe) != 24 or pe[:4] != b"PE\0\0" or pe[4:6] not in (b"\x4c\x01", b"\x64\x86", b"\x64\xaa"):
            raise ValueError("reviewed Windows EXE must have a supported PE header")
        count = struct.unpack_from("<H", pe, 6)[0]
        optional_size = struct.unpack_from("<H", pe, 20)[0]
        if not 1 <= count <= 96 or type(icon_offset) is not int or icon_offset < 0:
            raise ValueError("reviewed Windows EXE must identify its captured icon resource offset")
        stream.seek(optional_size, 1)
        sections = stream.read(count * 40)
        if len(sections) != count * 40:
            raise ValueError("reviewed Windows EXE has a truncated section table")
        resource = next(
            (offset for offset in range(0, len(sections), 40) if sections[offset:offset + 8] == b".rsrc\0\0\0"),
            None,
        )
        if resource is None:
            raise ValueError("reviewed Windows EXE must have a PE resource section")
        raw_size, raw_start = struct.unpack_from("<II", sections, resource + 16)
        if not raw_start <= icon_offset <= raw_start + raw_size - len(icon):
            raise ValueError("captured icon must lie inside the exact EXE resource section")
        stream.seek(icon_offset)
        if stream.read(len(icon)) != icon:
            raise ValueError("captured icon bytes differ from the exact reviewed EXE resource")
    with msi.open("rb") as stream:
        if stream.read(8) != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            raise ValueError("reviewed Windows MSI must have a compound file header")


def verify_installer_payloads(
    root: Path, rows: Any, artifact_names: dict[str, str], update: dict[str, Any], target: str,
    *, icon_offset: Any, icon: bytes,
) -> dict[str, str]:
    if not isinstance(rows, list) or len(rows) != 2 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Windows installer build manifest must identify both installer artifacts")
    artifacts = {row.get("name"): row for row in rows if isinstance(row.get("name"), str)}
    if artifacts.keys() != set(artifact_names.values()):
        raise ValueError("Windows installer names must match the customizer branding plan")
    entries = update.get("artifacts")
    if not isinstance(entries, list):
        raise ValueError("signed organization update manifest requires installer artifacts")
    paths: dict[str, Path] = {}
    digests: dict[str, str] = {}
    for kind, name in artifact_names.items():
        rows_for_package = [row for row in entries if isinstance(row, dict) and row.get("name") == name]
        if len(rows_for_package) != 1:
            raise ValueError(f"signed organization update manifest must identify {name} exactly once")
        entry = rows_for_package[0]
        digest = artifacts[name].get("sha256")
        size = artifacts[name].get("size_bytes")
        if (
            not valid_sha256(digest) or type(size) is not int or size <= 0
            or entry.get("sha256") != digest or entry.get("size_bytes") != size
            or entry.get("target") not in (target, kind)
        ):
            raise ValueError(f"signed organization update manifest must match the reviewed installer {name}")
        path = bound_evidence_file(root, entry.get("file"), digest, f"reviewed installer {name}")
        if path.stat().st_size != size:
            raise ValueError(f"reviewed installer size differs for {name}")
        paths[kind], digests[name] = path, digest
    verify_native_formats(paths["windows-exe"], paths["windows-msi"], icon_offset=icon_offset, icon=icon)
    return digests


def verify_exe_icon(ico: bytes, resource: bytes) -> None:
    if len(ico) < 6 or ico[:4] != b"\0\0\1\0":
        raise ValueError("reviewed branding logo must be an ICO file")
    images = struct.unpack_from("<H", ico, 4)[0]
    table_end = 6 + images * 16
    if not images or table_end > len(ico):
        raise ValueError("reviewed ICO image table is invalid")
    for entry in range(6, table_end, 16):
        size, start = struct.unpack_from("<II", ico, entry + 8)
        if size and start >= table_end and start + size <= len(ico) and resource == ico[start:start + size]:
            return
    raise ValueError("extracted EXE icon resource must match the branding logo")


def verify_windows_capture(
    root: Path, bundle: dict[str, Any], capture: dict[str, Any], update: dict[str, Any],
) -> dict[str, Any]:
    if capture.get("schema") != INSTALLER_CAPTURE_SCHEMA:
        raise ValueError(f"Windows installer capture schema must be {INSTALLER_CAPTURE_SCHEMA}")
    brand, version, target = (bundle.get(key) for key in ("brand_name", "version", "release_target"))
    organization = update.get("organization")
    update_url = update.get("update_url")
    if (
        not isinstance(brand, str) or not isinstance(version, str)
        or target not in ("windows-x86", "windows-x64", "windows-arm64")
        or not isinstance(organization, str) or not organization.strip()
        or update.get("version") != version
    ):
        raise ValueError("installer capture requires the exact branded Windows target, version and organization")
    if not isinstance(update_url, str) or not update_url.startswith("https://"):
        raise ValueError("signed organization update manifest must identify its HTTPS update URL")
    plan = build_installer_branding_plan(brand_name=brand, version=version, organization=organization)
    manifest_path = attachment(root, bundle.get("bundle_manifest"), "customizer manifest")
    manifest = read_object(manifest_path, "customizer manifest")
    if (
        bundle["bundle_manifest"].get("manifest_sha256") != bundle["bundle_manifest"].get("evidence_sha256")
        or manifest.get("schema_version") != 1 or manifest.get("brand_name") != brand
        or manifest.get("organization") != organization or manifest.get("project_version") != version
    ):
        raise ValueError("customizer manifest must bind the exact project version, brand and organization")

    logo = read_small(attachment(root, capture.get("logo"), "customizer logo"), "customizer logo")
    welcome = read_small(attachment(root, capture.get("welcome"), "customizer welcome"), "customizer welcome")
    logo_sha = hashlib.sha256(logo).hexdigest()
    welcome_sha = hashlib.sha256(welcome).hexdigest()
    files = manifest.get("files")
    if not isinstance(files, list) or any(not isinstance(row, dict) for row in files):
        raise ValueError("customizer manifest must inventory the original logo and welcome files")
    for name, content, digest in (("branding/logo.ico", logo, logo_sha), ("welcome.txt", welcome, welcome_sha)):
        rows = [row for row in files if row.get("path") == name]
        if len(rows) != 1 or rows[0].get("sha256") != digest or rows[0].get("size_bytes") != len(content):
            raise ValueError(f"customizer manifest differs from the captured {name}")

    build = read_object(attachment(root, capture.get("build_manifest"), "Windows build manifest"), "Windows build manifest")
    deployment = str(UUID(str(build.get("deployment_id")))).upper()
    if (
        deployment in STOCK_INSTALLER_IDS or build.get("product_name") != plan.product_name
        or build.get("publisher") != plan.publisher or build.get("version") != version
        or f"windows-{build.get('architecture')}" != target
        or build.get("icon_sha256") != logo_sha or build.get("welcome_sha256") != welcome_sha
    ):
        raise ValueError("Windows build manifest must match the deployment, Windows target and original branding")

    exe_icon = read_small(attachment(root, capture.get("exe_icon"), "extracted EXE icon"), "extracted EXE icon")
    verify_exe_icon(logo, exe_icon)
    digests = verify_installer_payloads(
        root, build.get("artifacts"), plan.artifact_names, update, target,
        icon_offset=capture.get("exe_icon_offset"), icon=exe_icon,
    )
    if capture.get("installer_sha256") != digests:
        raise ValueError("native inspection must bind both exact installer digests")

    exe = read_object(attachment(root, capture.get("exe_version"), "EXE version resource"), "EXE version resource")
    if (
        exe.get("ProductName") != plan.product_name
        or exe.get("CompanyName") != plan.publisher or exe.get("ProductVersion") != version
    ):
        raise ValueError("EXE version resource must show the branded product name, publisher and version")

    msi_data = read_small(attachment(root, capture.get("msi_database"), "decompiled MSI"), "decompiled MSI")
    msi = ElementTree.fromstring(msi_data).find("{*}Package")
    if msi is None or (
        msi.get("Name") != plan.product_name or msi.get("Manufacturer") != plan.publisher
        or msi.get("Version") != version or str(msi.get("UpgradeCode", "")).strip("{}").upper() != deployment
        or msi.find("{*}Property[@Id='ARPPRODUCTICON'][@Value='RemoteOpsWorkspaceIcon']") is None
        or msi.find("{*}Icon[@Id='RemoteOpsWorkspaceIcon']") is None
        or msi.find(f".//{{*}}Directory[@Id='INSTALLFOLDER'][@Name='Remote Ops Workspace {deployment}']") is None
        or msi.find(".//{*}File[@Id='WelcomeFile'][@Name='welcome.txt']") is None
    ):
        raise ValueError("decompiled MSI database must show the exact branding, upgrade code, install directory and welcome file")
    if (
        read_small(attachment(root, capture.get("msi_icon"), "extracted MSI icon"), "extracted MSI icon") != logo
        or read_small(attachment(root, capture.get("msi_welcome"), "extracted MSI welcome"), "extracted MSI welcome") != welcome
    ):
        raise ValueError("MSI exported icon and welcome bytes must match the original branding")
    return {"verified_windows_installers": digests, "deployment_id": deployment}


def policy_observation(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"machine policy capture requires a structured {label} observation")
    return value


def require_policy_denial(
    message: Any, surface: str, action: str, allowed: str, denied: str,
) -> None:
    reason = (
        f"enterprise policy blocked {surface} {action}: "
        f"{surface} cannot use locked enterprise setting protocol={denied!r}; required {allowed!r}"
    )
    if not isinstance(message, str) or reason not in message:
        raise ValueError(f"{surface} denial must show the observed protocol lock")


def verify_policy_document(manifest: dict[str, Any], policy_bytes: bytes) -> str:
    deployed = hashlib.sha256(policy_bytes).hexdigest()
    files = manifest.get("files")
    rows = [
        row for row in files if isinstance(row, dict) and row.get("path") == "config/policy.json"
    ] if isinstance(files, list) else []
    if len(rows) != 1 or rows[0].get("sha256") != deployed or rows[0].get("size_bytes") != len(policy_bytes):
        raise ValueError("installed machine policy must match config/policy.json in the customizer manifest")
    return deployed


def verify_policy_surfaces(root: Path, bundle: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    if capture.get("schema") != POLICY_CAPTURE_SCHEMA:
        raise ValueError(f"machine policy capture schema must be {POLICY_CAPTURE_SCHEMA}")
    document = attachment(root, capture.get("policy_document"), "deployed policy document")
    policy_bytes = read_small(document, "deployed policy document")
    policy = decode_object(policy_bytes, "deployed policy document")
    manifest = read_object(attachment(root, bundle.get("bundle_manifest"), "customizer manifest"), "customizer manifest")
    deployed = verify_policy_document(manifest, policy_bytes)
    if capture.get("installed_policy_sha256") != deployed or capture.get("machine_policy_sha256") != deployed:
        raise ValueError("installed machine policy must match config/policy.json in the customizer manifest")
    if any(capture.get(key) is not True for key in (
        "machine_policy_write_refused", "machine_policy_unchanged", "portable_policy_writable",
        "gui_and_web_started_before_machine_install",
    )):
        raise ValueError("machine policy capture must show protected policy and a writable portable fallback in an open workspace")

    attempts = policy_observation(capture.get("attempts"), "protocol attempts")
    allowed, denied = attempts.get("allowed_protocol"), attempts.get("denied_protocol")
    if not isinstance(allowed, str) or not allowed or not isinstance(denied, str) or not denied or allowed == denied:
        raise ValueError("machine policy capture requires distinct allowed and denied protocols")
    locks = policy.get("locked_settings")
    lock = {"key": "protocol", "value": allowed}
    declared = policy_observation(bundle.get("policy_locks"), "declared policy locks")
    if not isinstance(locks, list) or lock not in locks or declared.get("locked_settings") != locks:
        raise ValueError("observed locked protocol must match the declared deployed policy")

    before = policy_observation(capture.get("public_policy_before"), "pre-install Web policy")
    after = policy_observation(capture.get("public_policy"), "installed Web policy")
    before_body = policy_observation(before.get("body"), "pre-install Web policy body")
    after_body = policy_observation(after.get("body"), "installed Web policy body")
    if (
        before.get("status") != 200 or before_body.get("locked_settings") != []
        or after.get("status") != 200 or after_body.get("active") is not True
        or after_body.get("locked_settings") != [lock]
    ):
        raise ValueError("running Web endpoint must expose the protocol lock after machine policy installation")
    for process in ("web", "gui"):
        ids = policy_observation(capture.get(f"{process}_process"), f"{process} process")
        if (
            type(ids.get("before")) is not int or type(ids.get("after")) is not int
            or ids["before"] <= 0 or ids.get("after") != ids["before"]
        ):
            raise ValueError(f"machine policy capture must retain the same {process} process across installation")

    for surface in ("web", "cli", "profile-editor"):
        row = policy_observation(capture.get(surface), surface)
        original = row.get("store_before")
        saved = row.get("store_after_allowance")
        if (
            not valid_sha256(original) or row.get("store_after_denial") != original
            or not valid_sha256(saved) or saved == original or row.get("saved_protocol") != allowed
        ):
            raise ValueError(f"{surface} store must remain unchanged on denial and persist the allowed protocol")
        if surface == "web":
            refusal = policy_observation(row.get("denied"), "Web refusal")
            success = policy_observation(row.get("allowed"), "Web success")
            if refusal.get("status") != 400 or success.get("status") != 201:
                raise ValueError("Web write capture must record HTTP 400 and 201")
            confirmed = policy_observation(success.get("body"), "Web successful profile")
            if confirmed.get("protocol") != allowed:
                raise ValueError("Web response must return the allowed profile")
            denial = policy_observation(refusal.get("body"), "Web error body").get("error")
        elif surface == "cli":
            refusal = policy_observation(row.get("denied"), "CLI refusal")
            success = policy_observation(row.get("allowed"), "CLI success")
            if (
                type(refusal.get("exit")) is not int or type(success.get("exit")) is not int
                or refusal["exit"] == 0 or success["exit"] != 0
            ):
                raise ValueError("CLI capture must show failing and successful exit statuses")
            denial = refusal.get("stderr")
        else:
            notices = row.get("denied")
            denial = notices[0] if isinstance(notices, list) and len(notices) == 1 else None
        require_policy_denial(denial, surface, "add", allowed, denied)

    for surface in ("gui", "quick-connect"):
        row = policy_observation(capture.get(surface), surface)
        original_tabs, denied_tabs, allowed_tabs = (
            row.get(key) for key in ("tabs_before", "tabs_after_denial", "tabs_after_allowance")
        )
        if (
            type(original_tabs) is not int or type(denied_tabs) is not int or type(allowed_tabs) is not int
            or original_tabs < 0 or original_tabs != denied_tabs or allowed_tabs != original_tabs + 1
        ):
            raise ValueError(f"{surface} must open one tab only for the allowed operation")
        notices = row.get("denied")
        if not isinstance(notices, list) or len(notices) != 1:
            raise ValueError(f"{surface} must display a policy refusal")
        require_policy_denial(policy_observation(notices[0], surface).get("text"), surface, "launch", allowed, denied)

    launcher = policy_observation(capture.get("launcher"), "launcher")
    require_policy_denial(launcher.get("denied"), "launcher", "launch", allowed, denied)
    plan = launcher.get("allowed_argv")
    if (
        launcher.get("allowed_protocol") != allowed or not isinstance(plan, list) or not plan
        or any(not isinstance(value, str) or not value for value in plan)
    ):
        raise ValueError("launcher must return a plan for the allowed profile")
    return {"verified_policy_surfaces": list(PROFESSIONAL_POLICY_SURFACES), "verified_machine_policy_sha256": deployed}


def approved_update_origins(origins: list[str], *, published: bool) -> set[str]:
    if not origins:
        raise ValueError("supply at least one independently approved professional update HTTPS origin")
    approved: set[str] = set()
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            canonical = update_channel._origin(origin)
        except ValueError as exc:
            raise ValueError("approved professional update origin must be a canonical HTTPS origin") from exc
        if origin != canonical or parsed.path or parsed.query:
            raise ValueError("approved professional update origin must be a canonical HTTPS origin")
        host = parsed.hostname or ""
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if published and (
            host == "localhost" or host.endswith(".localhost")
            or (literal is not None and (literal.is_loopback or literal.is_unspecified))
        ):
            raise ValueError("published professional update channel requires a hosted HTTPS origin")
        approved.add(origin)
    return approved


def reviewed_delivery_object(root: Path, name: Any, digest: Any, label: str) -> tuple[dict[str, Any], int]:
    path, error = secure_regular_file(root, name, label)
    if path is None:
        raise ValueError(error)
    raw = read_small(path, label)
    if not valid_sha256(digest) or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"{label} SHA-256 differs from the evidence")
    return decode_object(raw, label), len(raw)


def approved_delivery_target(
    label: str, url: Any, digest: Any, size: Any, origins: set[str],
) -> tuple[str, str, str, int]:
    if not isinstance(url, str) or update_channel._origin(url) not in origins:
        raise ValueError(f"{label} URL must use an approved professional update origin")
    if not isinstance(digest, str) or not valid_sha256(digest):
        raise ValueError(f"{label} has an invalid delivery digest")
    if type(size) is not int or not 1 <= size <= update_channel.MAX_ARTIFACT_BYTES:
        raise ValueError(f"{label} has an invalid delivery byte limit")
    return label, url, digest, size


def verify_hosted_professional_update(
    evidence_path: Path, *, assets_dir: Path, evidence_sha256: str,
    verified_installers: dict[str, str], origins: list[str], published: bool,
) -> None:
    """Compare actual HTTPS response bytes after the underlying release evidence passed."""
    approved = approved_update_origins(origins, published=published)
    relative = evidence_path.absolute().relative_to(assets_dir.absolute()).as_posix()
    evidence, _ = reviewed_delivery_object(
        assets_dir, relative, evidence_sha256, "reviewed deployment evidence",
    )
    channel = policy_observation(evidence.get("update_channel"), "signed update channel")
    manifest_digest = channel.get("manifest_sha256")
    update, manifest_size = reviewed_delivery_object(
        assets_dir, channel.get("manifest_file"), manifest_digest, "reviewed update manifest",
    )
    if (
        len(verified_installers) != 2
        or {Path(name).suffix for name in verified_installers} != {".exe", ".msi"}
        or any(not valid_sha256(digest) for digest in verified_installers.values())
    ):
        raise ValueError("hosted delivery requires the verified EXE and MSI")

    entries = update.get("artifacts")
    if not isinstance(entries, list):
        raise ValueError("reviewed update manifest must include installer entries")
    # Approve the whole request set before contacting any endpoint.
    targets = [approved_delivery_target(
        "signed manifest", update.get("update_url"), manifest_digest, manifest_size, approved,
    )]
    for name, digest in sorted(verified_installers.items()):
        matching = [row for row in entries if isinstance(row, dict) and row.get("name") == name]
        if len(matching) != 1 or matching[0].get("sha256") != digest:
            raise ValueError(f"reviewed installer {name} must be bound by the signed update manifest")
        row = matching[0]
        targets.append(approved_delivery_target(name, row.get("url"), digest, row.get("size_bytes"), approved))
    settings = {"allowed_origins": approved, "limits": {"redirects": 3, "http_timeout_seconds": 20}}
    deadline = time.monotonic() + 300
    for label, url, digest, size in targets:
        actual = hashlib.sha256()
        try:
            for chunk in update_channel._chunks(url, settings, deadline, size, expected=size):
                actual.update(chunk)
        except (OSError, ValueError) as exc:
            raise ValueError(f"{label} HTTPS delivery failed: {exc}") from exc
        if actual.hexdigest() != digest:
            raise ValueError(f"{label} HTTPS delivery SHA-256 differs from the reviewed bytes")


def validate_professional_release_evidence(
    evidence_path: Path, *, assets_dir: Path | None = None,
) -> MobaProfessionalDeploymentEvidenceValidation:
    root = assets_dir if assets_dir is not None else evidence_path.parent
    try:
        relative = evidence_path.absolute().relative_to(root.absolute()).as_posix()
        evidence, error = secure_regular_file(root, relative, "professional release evidence")
        if evidence is None:
            raise ValueError(error)
        bundle = read_object(evidence, "professional release evidence")
        identity = capture_release_identity(bundle, "professional release evidence")
        for stage in ("bundle_manifest", "update_channel"):
            attachment(root, bundle.get(stage), stage)
        capture = read_object(attachment(root, bundle.get("installer_branding"), "Windows installer capture"), "Windows installer capture")
        if capture_release_identity(capture, "Windows installer capture") != identity or (
            identity["release_tag"] != f"v{bundle.get('version')}"
        ):
            raise ValueError("Windows installer capture must bind the exact release source, tag and public artifact")
        policy_capture = read_object(attachment(root, bundle.get("policy_locks"), "machine policy capture"), "machine policy capture")
        if capture_release_identity(policy_capture, "machine policy capture") != identity:
            raise ValueError("machine policy capture must bind the exact release source, tag and public artifact")
        channel = bundle["update_channel"]
        update = read_object(
            bound_evidence_file(root, channel.get("manifest_file"), channel.get("manifest_sha256"), "signed update manifest"),
            "signed update manifest",
        )
        entries = update.get("artifacts")
        if isinstance(entries, list):
            for row in entries:
                if isinstance(row, dict) and row.get("file"):
                    path, error = secure_regular_file(root, row.get("file"), "signed update manifest payload")
                    if path is None:
                        raise ValueError(error)
        result = validate_professional_deployment_evidence(evidence, assets_dir=root)
        if result.passed:
            result.summary.update(identity, **verify_windows_capture(root, bundle, capture, update))
            result.summary.update(verify_policy_surfaces(root, bundle, policy_capture))
        return result
    except (OSError, ValueError, ElementTree.ParseError) as exc:
        return MobaProfessionalDeploymentEvidenceValidation(str(evidence_path), str(root), False, [str(exc)], [], {})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify MobaXterm Professional-style deployment evidence.",
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-origin", action="append", default=[], help="approved HTTPS origin for a live delivery check")
    args = parser.parse_args()

    result = validate_professional_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if result.passed and args.update_origin:
        root = args.assets_dir or args.evidence.parent
        try:
            verify_hosted_professional_update(
                args.evidence, assets_dir=root, evidence_sha256=sha256_file(args.evidence),
                verified_installers=result.summary["verified_windows_installers"],
                origins=args.update_origin, published=False,
            )
            result.summary["verified_update_delivery"] = True
        except (OSError, ValueError) as exc:
            result = MobaProfessionalDeploymentEvidenceValidation(
                str(args.evidence), str(root), False, [str(exc)], [], {},
            )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba professional deployment evidence passed")
    else:
        for error in result.errors:
            print(f"moba professional deployment evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

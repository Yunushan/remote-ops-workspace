"""Assemble the native Professional deployment captures into a parity review."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.moba_customizer import (  # noqa: E402
    MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA,
    REQUIRED_POLICY_SURFACES,
    validate_professional_deployment_evidence,
)
from scripts.check_moba_professional_deployment_evidence import (  # noqa: E402
    approved_update_origins,
    attachment,
    policy_observation,
    read_object,
    validate_professional_release_evidence,
    verify_hosted_professional_update,
    verify_policy_surfaces,
    verify_windows_capture,
)
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    secure_regular_file,
    sha256_file,
)
from scripts.release_candidate_inventory import safe_name  # noqa: E402

EVIDENCE = "evidence.json"
INSTALLER_ATTACHMENTS = ("build_manifest", "logo", "welcome", "exe_version", "exe_icon",
                         "msi_database", "msi_icon", "msi_welcome")


def input_path(root: Path, name: str, label: str) -> Path:
    source, error = secure_regular_file(root, name, label)
    if source is None:
        raise ValueError(error)
    return source


class ReviewFiles:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.names: dict[str, str] = {}

    def copy(self, source: Path, name: Any, digest: Any, label: str) -> dict[str, str]:
        original = bound_evidence_file(source, name, digest, label)
        relative = PurePosixPath(name)
        if relative.as_posix() != name or not all(safe_name(part) and not part.startswith(".") for part in relative.parts):
            raise ValueError(f"{label} must use a portable relative path")
        if relative.parts[0].casefold() == EVIDENCE:
            raise ValueError(f"{label} conflicts with a review path: {name}")
        prefix = PurePosixPath()
        for part in relative.parts:
            prefix /= part
            spelling = prefix.as_posix()
            if self.names.setdefault(spelling.casefold(), spelling) != spelling:
                raise ValueError(f"{label} conflicts with a review path: {name}")
        target = self.root / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
        if sha256_file(target) != digest:
            raise ValueError(f"{label} changed during assembly or conflicts with another attachment")
        return {"evidence_file": name, "evidence_sha256": digest}

    def reference(self, source: Path, value: Any, label: str) -> dict[str, str]:
        ref = policy_observation(value, label)
        return self.copy(source, ref.get("evidence_file"), ref.get("evidence_sha256"), label)


def stage(reference: dict[str, str], command: str, **fields: Any) -> dict[str, Any]:
    return {**reference, "status": "passed", "command": command, **fields}


def assemble(
    installer_root: Path, policy_root: Path, wheel: Path, public_key: str, output: Path, *,
    origins: list[str], local: bool = False,
) -> Path:
    if output.exists() or output.is_symlink():
        raise ValueError("output must be a new directory")
    if not local or origins:
        approved_update_origins(origins, published=not local)
    installer_review = read_object(input_path(installer_root, "installer-review.json", "installer review"), "installer review")
    policy_review = read_object(input_path(policy_root, "policy-review.json", "policy review"), "policy review")
    wheel_source = input_path(wheel.parent, wheel.name, "release wheel")
    asset = {"name": wheel.name, "sha256": sha256_file(wheel_source)}
    version = installer_review.get("version")
    if wheel.name != f"remote_ops_workspace-{version}-py3-none-any.whl" or policy_review.get("release_asset") != asset:
        raise ValueError("policy review must bind the supplied release wheel and installer version")
    identity: dict[str, Any] = {"release_asset": asset}
    if local:
        if "source" in installer_review or "source" in policy_review:
            raise ValueError("tagged captures require release review assembly")
    else:
        windows = capture_release_identity(installer_review, "installer review")
        linux = capture_release_identity(policy_review, "policy review")
        if windows != linux or windows["release_tag"] != f"v{version}" or windows["tested_release_asset"] != asset:
            raise ValueError("installer and policy reviews must bind the same release wheel, tag and workflow attempt")
        identity["source"] = installer_review["source"]

    with TemporaryDirectory(prefix=".professional-review-", dir=output.parent) as temporary:
        root = Path(temporary) / "review"
        files = ReviewFiles(root)
        manifest_ref = files.reference(installer_root, installer_review.get("bundle_manifest"), "installer customizer manifest")
        policy_manifest = attachment(policy_root, policy_review.get("bundle_manifest"), "policy customizer manifest")
        if manifest_ref["evidence_sha256"] != sha256_file(policy_manifest):
            raise ValueError("installer and policy reviews must use the same original customizer manifest")
        installer_ref = files.reference(installer_root, installer_review.get("installer_branding"), "installer capture")
        policy_ref = files.reference(policy_root, policy_review.get("policy_locks"), "policy capture")
        update_ref = files.reference(installer_root, installer_review.get("update_manifest"), "signed update manifest")
        installer = read_object(root / installer_ref["evidence_file"], "installer capture")
        policy = read_object(root / policy_ref["evidence_file"], "policy capture")
        update = read_object(root / update_ref["evidence_file"], "signed update manifest")
        if policy.get("release_asset") != asset:
            raise ValueError("policy capture must bind the supplied release wheel")
        if local and ("source" in installer or "source" in policy):
            raise ValueError("tagged captures require release review assembly")

        for name in INSTALLER_ATTACHMENTS:
            files.reference(installer_root, installer.get(name), name)
        files.reference(policy_root, policy.get("policy_document"), "deployed policy document")
        artifacts = update.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != 2:
            raise ValueError("the signed update manifest must identify exactly the two Windows installers")
        for entry in artifacts:
            row = policy_observation(entry, "signed update artifact")
            files.copy(installer_root, row.get("file"), row.get("sha256"), "signed update artifact")

        envelope = {
            **identity, "schema": MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA,
            "release_target": installer_review.get("release_target"),
            "brand_name": installer_review.get("brand_name"), "version": version,
            "bundle_manifest": stage(manifest_ref, "verify original customizer manifest",
                                     manifest_sha256=manifest_ref["evidence_sha256"], sha256s_present=True),
            "installer_branding": stage(installer_ref, "capture_moba_professional_installers.py",
                                        windows_exe_rebranded=True, windows_msi_rebranded=True,
                                        product_name_matches_brand=True, logo_applied=True),
            "policy_locks": stage(policy_ref, "capture_moba_professional_policy.py",
                                  locked_settings=policy_review["policy_locks"].get("locked_settings"),
                                  surfaces=dict.fromkeys(REQUIRED_POLICY_SURFACES, True)),
            "update_channel": stage(update_ref, "row customizer update-verify",
                                    manifest_file=update_ref["evidence_file"], manifest_sha256=update_ref["evidence_sha256"],
                                    channel=update.get("channel"), organization=update.get("organization"), public_key=public_key,
                                    https_update_url=True, signature_verified=True, organization_channel=True),
        }
        evidence = root / EVIDENCE
        evidence.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if local:
            result = validate_professional_deployment_evidence(evidence)
        else:
            result = validate_professional_release_evidence(evidence)
        if not result.passed:
            raise ValueError("Professional deployment review failed validation\n" + "\n".join(result.errors))
        if local:
            installers = verify_windows_capture(root, envelope, installer, update)["verified_windows_installers"]
            verify_policy_surfaces(root, envelope, policy)
        else:
            installers = result.summary["verified_windows_installers"]
        if origins:
            verify_hosted_professional_update(evidence, assets_dir=root, evidence_sha256=sha256_file(evidence),
                                              verified_installers=installers, origins=origins, published=not local)
        if sha256_file(wheel_source) != asset["sha256"]:
            raise ValueError("release wheel changed during evidence assembly")
        root.rename(output)
    return output / EVIDENCE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer-review", type=Path, required=True, help="directory from the Windows capture")
    parser.add_argument("--policy-review", type=Path, required=True, help="directory from the policy capture")
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--update-key", required=True, help="independently trusted organization public key")
    parser.add_argument("--update-origin", action="append", default=[], help="approved HTTPS origin")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--local", action="store_true", help="assemble a local rehearsal without release provenance")
    args = parser.parse_args()
    try:
        evidence = assemble(args.installer_review, args.policy_review, args.wheel, args.update_key, args.out,
                            origins=args.update_origin, local=args.local)
    except (OSError, ValueError, ElementTree.ParseError) as error:
        parser.exit(1, f"Professional deployment review assembly failed: {error}\n")
    print(f"Verified {'local' if args.local else 'release'} Professional deployment review: {evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

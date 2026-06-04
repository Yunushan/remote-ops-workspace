from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP_PATH = ROOT / "docs" / "ROADMAP.md"


@dataclass(frozen=True)
class Evidence:
    relative_path: str
    required_snippet: str | None = None


@dataclass(frozen=True)
class RoadmapItem:
    label: str
    completed_snippet: str
    stale_future_snippets: tuple[str, ...]
    evidence: tuple[Evidence, ...]


IMPLEMENTED_ITEMS = (
    RoadmapItem(
        label="CLI profile workflow hardening",
        completed_snippet="Hardened CLI profile workflows.",
        stale_future_snippets=("Harden CLI profile workflows.",),
        evidence=(
            Evidence("src/remote_ops_workspace/profile_validation.py", "normalize_group_defaults"),
            Evidence("src/remote_ops_workspace/storage.py", "def set_group_defaults"),
        ),
    ),
    RoadmapItem(
        label="Phase 1 source and Python releases",
        completed_snippet="Shipped Phase 1 release artifacts",
        stale_future_snippets=("Ship Phase 1 release artifacts",),
        evidence=(
            Evidence(".github/workflows/release.yml", "source-and-python"),
            Evidence("configs/release_matrix.json", '"source_and_python"'),
            Evidence("scripts/make_release.py", "target-source-install-bundle"),
        ),
    ),
    RoadmapItem(
        label="Phase 2 Windows native releases",
        completed_snippet="Shipped Phase 2 Windows native installers",
        stale_future_snippets=("Ship Phase 2 Windows native installers",),
        evidence=(
            Evidence(".github/workflows/release.yml", "windows-native"),
            Evidence("configs/release_matrix.json", ".msi"),
            Evidence("scripts/smoke_windows_native.ps1", "msiexec"),
        ),
    ),
    RoadmapItem(
        label="Phase 3 macOS native releases",
        completed_snippet="Shipped Phase 3 macOS native packages",
        stale_future_snippets=("Ship Phase 3 macOS native packages",),
        evidence=(
            Evidence(".github/workflows/release.yml", "macos-native"),
            Evidence("configs/release_matrix.json", ".dmg"),
            Evidence("scripts/smoke_macos_native.sh", "hdiutil"),
        ),
    ),
    RoadmapItem(
        label="Phase 4 Linux native releases",
        completed_snippet="Shipped Phase 4 Linux native packages",
        stale_future_snippets=("Ship Phase 4 Linux native packages",),
        evidence=(
            Evidence(".github/workflows/release.yml", "linux-native"),
            Evidence("configs/release_matrix.json", ".deb"),
            Evidence("scripts/smoke_linux_native.sh", "dpkg"),
        ),
    ),
    RoadmapItem(
        label="group-level profile defaults",
        completed_snippet="Added group-level profile defaults with inheritance into stored profiles.",
        stale_future_snippets=(
            "Add group inheritance defaults.",
            "Add group-level profile defaults",
        ),
        evidence=(
            Evidence("src/remote_ops_workspace/cli.py", 'pdefaults = psub.add_parser("defaults"'),
            Evidence("src/remote_ops_workspace/storage.py", "def set_group_defaults"),
            Evidence("tests/test_storage.py", "test_profile_store_applies_group_defaults"),
        ),
    ),
    RoadmapItem(
        label="snippets command group",
        completed_snippet="Added snippets command group.",
        stale_future_snippets=("Add snippets command group.",),
        evidence=(
            Evidence("src/remote_ops_workspace/cli.py", 'snippet = sub.add_parser("snippet"'),
            Evidence("src/remote_ops_workspace/snippets.py", "class Snippet"),
        ),
    ),
    RoadmapItem(
        label="profile importers",
        completed_snippet="Added profile importers for Remmina, mRemoteNG, Termius-style JSON and MobaXterm session exports.",
        stale_future_snippets=("Add profile importers for Remmina, mRemoteNG, Termius-style JSON and MobaXterm session exports.",),
        evidence=(
            Evidence("src/remote_ops_workspace/cli.py", 'imp = sub.add_parser("import"'),
            Evidence("src/remote_ops_workspace/profile_importers.py", "SUPPORTED_IMPORT_FORMATS"),
        ),
    ),
    RoadmapItem(
        label="SSH key helper",
        completed_snippet="Added SSH key helper and local key generation workflow.",
        stale_future_snippets=(
            "SSH key helper and local key generation workflow.",
            "Add SSH key helper and local key generation workflow.",
        ),
        evidence=(
            Evidence("src/remote_ops_workspace/cli.py", 'keygen = sub.add_parser("keygen"'),
            Evidence("src/remote_ops_workspace/keys.py", "def build_keygen_plan"),
        ),
    ),
    RoadmapItem(
        label="sync provider interface",
        completed_snippet="Added sync provider interface.",
        stale_future_snippets=(
            "Sync provider interface.",
            "Add sync provider interface.",
        ),
        evidence=(
            Evidence("src/remote_ops_workspace/cli.py", 'sync = sub.add_parser("sync"'),
            Evidence("src/remote_ops_workspace/sync.py", "class DirectorySyncProvider"),
        ),
    ),
    RoadmapItem(
        label="native installer smoke contract",
        completed_snippet="Added install, verify, upgrade and uninstall smoke-test contract for native packages.",
        stale_future_snippets=(
            "Add install, upgrade and uninstall smoke tests for native packages.",
            "Add install, verify, upgrade and uninstall smoke-test contract for native packages.",
        ),
        evidence=(
            Evidence("configs/native_installer_smoke.json", "install, verify, upgrade-or-reinstall, and uninstall"),
            Evidence("scripts/check_native_installer_smoke.py", "native installer smoke"),
            Evidence(".github/workflows/release.yml", "Run Windows native installer smoke tests"),
            Evidence(".github/workflows/release.yml", "Run macOS native installer smoke tests"),
            Evidence(".github/workflows/release.yml", "Run Linux native installer smoke tests"),
        ),
    ),
)


def main() -> int:
    errors = check_roadmap_truth()
    if errors:
        for error in errors:
            print(f"roadmap truth: {error}", file=sys.stderr)
        return 1
    print("roadmap truth checks passed")
    return 0


def check_roadmap_truth(text: str | None = None, *, root: Path = ROOT) -> list[str]:
    roadmap = text if text is not None else (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    errors: list[str] = []
    completed = completed_text(roadmap)
    future = future_text(roadmap)
    if not completed.strip():
        errors.append("docs/ROADMAP.md must include a completed section for shipped work")
    for item in IMPLEMENTED_ITEMS:
        if item.completed_snippet not in completed:
            errors.append(f"completed roadmap section missing {item.label}: {item.completed_snippet}")
        for stale in item.stale_future_snippets:
            if stale in future:
                errors.append(f"future roadmap still lists shipped {item.label}: {stale}")
        errors.extend(check_evidence(item, root=root))
    return errors


def completed_text(text: str) -> str:
    return "\n".join(body for title, body in section_blocks(text) if title.lower().startswith("completed"))


def future_text(text: str) -> str:
    return "\n".join(body for title, body in section_blocks(text) if not title.lower().startswith("completed"))


def section_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1), text[start:end]))
    return blocks


def check_evidence(item: RoadmapItem, *, root: Path) -> list[str]:
    errors: list[str] = []
    for evidence in item.evidence:
        path = root / evidence.relative_path
        if not path.exists():
            errors.append(f"{item.label} evidence file missing: {evidence.relative_path}")
            continue
        if evidence.required_snippet is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{item.label} evidence file must be UTF-8 text: {evidence.relative_path}")
            continue
        if evidence.required_snippet not in text:
            errors.append(
                f"{item.label} evidence file {evidence.relative_path} "
                f"missing snippet: {evidence.required_snippet}"
            )
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

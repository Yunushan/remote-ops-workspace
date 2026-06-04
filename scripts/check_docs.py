from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
EXTERNAL_LINK_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "data:",
)

REQUIRED_FILES = (
    "README.md",
    "README.tr.md",
    "SECURITY.md",
    "LICENSE",
    "NOTICE",
    "docs/ROADMAP.md",
    "docs/SECURITY_MODEL.md",
    "docs/VERIFYING.md",
)

README_REQUIRED_SNIPPETS = (
    "row vault status",
    "row vault set prod/router-password --secret-env ROW_ROUTER_PASSWORD",
    "row vault delete old/router-password --force",
    "row plugins list",
    "--allow-public-bind",
    "allow_insecure_sshv1=true",
    "scripts/verify.py --quick",
    "SHA256SUMS",
    "docs/SECURITY_MODEL.md",
)


def main() -> int:
    errors: list[str] = []
    errors.extend(check_required_files())
    errors.extend(check_markdown_links())
    errors.extend(check_readme_pair())
    if errors:
        for error in errors:
            print(f"docs consistency: {error}", file=sys.stderr)
        return 1
    print("documentation consistency passed")
    return 0


def check_required_files() -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).exists():
            errors.append(f"missing required file: {relative}")
    return errors


def check_markdown_links() -> list[str]:
    errors: list[str] = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            raw_target = match.group(1).strip()
            if not raw_target or should_skip_link(raw_target):
                continue
            target = raw_target.strip("<>")
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = (path.parent / unquote(target_path)).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                errors.append(f"{display(path)} links outside repository: {raw_target}")
                continue
            if not resolved.exists():
                errors.append(f"{display(path)} has missing local link: {raw_target}")
    return errors


def check_readme_pair() -> list[str]:
    errors: list[str] = []
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    turkish = (ROOT / "README.tr.md").read_text(encoding="utf-8")
    if "README.tr.md" not in english:
        errors.append("README.md must link to README.tr.md")
    if "README.md" not in turkish:
        errors.append("README.tr.md must link back to README.md")
    for snippet in README_REQUIRED_SNIPPETS:
        if snippet not in english:
            errors.append(f"README.md missing required snippet: {snippet}")
        if snippet not in turkish:
            errors.append(f"README.tr.md missing required snippet: {snippet}")
    return errors


def markdown_files() -> list[Path]:
    roots = [ROOT / "README.md", ROOT / "README.tr.md", ROOT / "SECURITY.md"]
    roots.extend(sorted((ROOT / "docs").rglob("*.md")))
    return [path for path in roots if path.exists()]


def should_skip_link(target: str) -> bool:
    lowered = target.lower()
    return target.startswith("#") or lowered.startswith(EXTERNAL_LINK_PREFIXES)


def display(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


if __name__ == "__main__":
    raise SystemExit(main())

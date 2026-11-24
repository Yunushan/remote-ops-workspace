"""Prepare a Debian amd64 MobApt cache from exact Bash and tree packages."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from remote_ops_workspace.moba_mobapt import (  # noqa: E402
    build_mobapt_runtime_bundle_plan,
    write_mobapt_runtime_bundle,
)
from scripts.check_release_license_compliance import sha256_file  # noqa: E402
from scripts.debian_release_fixture import unpack_deb_inputs  # noqa: E402
from scripts.stage_debian_mobapt_cache import EVIDENCE, REVIEW, stage_cache  # noqa: E402


def prepare_cache(bash: Path, tree: Path, release_tag: str, output: Path) -> str:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if release_tag != f"v{version}":
        raise ValueError("MobApt cache tag must match the checkout's release version")
    if output.exists() or output.is_symlink():
        raise ValueError("MobApt cache output already exists")
    with TemporaryDirectory(prefix="mobapt-prepare-", dir=output.parent) as scratch:
        root = Path(scratch)
        bash_notice = root / "bash.copyright"
        tree_notice = root / "tree.copyright"
        bash_binary = root / "bash"
        inputs = {
            "bash": unpack_deb_inputs(bash.resolve(strict=True), "bash", "amd64", {
                "usr/bin/bash": bash_binary, "usr/share/doc/bash/copyright": bash_notice,
            }),
            "tree": unpack_deb_inputs(tree.resolve(strict=True), "tree", "amd64", {
                "usr/share/doc/tree/copyright": tree_notice,
            }),
        }
        bash_binary.chmod(0o755)
        bundle = root / "bundle"
        plan = build_mobapt_runtime_bundle_plan(
            bundle, tools=["bash"], tool_sources={"bash": bash_binary},
            packages=[f"tree={inputs['tree']['version']}"], package_sources={"tree": tree.resolve()},
            release_target="linux-x86_64",
        )
        write_mobapt_runtime_bundle(plan)
        notices = bundle / "notices"
        notices.mkdir()
        for notice in (bash_notice, tree_notice):
            shutil.copyfile(notice, notices / notice.name)
        review = bundle / REVIEW
        review.write_text(json.dumps({
            "release_tag": release_tag,
            "debian_inputs": inputs,
            "assembly_sha256": sha256_file(bundle / EVIDENCE),
            "notices": {path.name: sha256_file(path) for path in sorted(notices.iterdir())},
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        digest = sha256_file(review)
        staging_root = root / "deb"
        staging_root.mkdir()
        stage_cache(bundle, staging_root, "amd64", digest, release_tag=release_tag)
        bundle.rename(output)
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bash-deb", type=Path, required=True)
    parser.add_argument("--tree-deb", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(prepare_cache(args.bash_deb, args.tree_deb, args.tag, args.out))
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        parser.exit(1, f"Debian MobApt cache preparation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

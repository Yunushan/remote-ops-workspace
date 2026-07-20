from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = Path(__file__).resolve().parent
RUNTIME_CONFIGS = (
    "feature_manifest.json",
    "platform_targets.json",
    "platform_verified_evidence.json",
    "platform_parity_promotion.json",
    "xp_native_evidence_contract.json",
)
WEB_ASSET_SOURCE = ROOT / "apps" / "web"


class build_py(_build_py):
    def run(self) -> None:
        super().run()
        destination = Path(self.build_lib) / "remote_ops_workspace" / "configs"
        destination.mkdir(parents=True, exist_ok=True)
        for name in RUNTIME_CONFIGS:
            shutil.copyfile(ROOT / "configs" / name, destination / name)
        shutil.copytree(
            WEB_ASSET_SOURCE,
            Path(self.build_lib) / "remote_ops_workspace" / "web",
            dirs_exist_ok=True,
        )


setup(cmdclass={"build_py": build_py})

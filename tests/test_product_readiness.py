import importlib.util
import json
import sys
from pathlib import Path


def load_product_readiness_checker():
    path = Path("scripts/check_product_readiness.py")
    spec = importlib.util.spec_from_file_location("check_product_readiness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check_product_readiness.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_product_readiness"] = module
    spec.loader.exec_module(module)
    return module


def test_product_readiness_checker_passes_current_tree() -> None:
    checker = load_product_readiness_checker()
    assert checker.main() == 0


def test_product_readiness_rejects_invalid_platform_evidence_registry(tmp_path: Path) -> None:
    checker = load_product_readiness_checker()
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    registry["policy"] = registry["policy"].replace(
        "review-bundle manifest release asset URL binding, ",
        "",
    )
    registry_path = tmp_path / "platform_verified_evidence.json"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    original_path = checker.platform_evidence_checker.EVIDENCE_PATH
    checker.platform_evidence_checker.EVIDENCE_PATH = registry_path
    try:
        errors = checker.check_product_readiness()
    finally:
        checker.platform_evidence_checker.EVIDENCE_PATH = original_path

    assert (
        "platform verified evidence registry: platform verified evidence policy must require "
        "review-bundle manifest release asset URL binding"
    ) in errors

import importlib.util
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

"""Detect source-pin drift before disposable browser hosts start preparation."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "tests" / "catalogue-browser"


def test_catalogue_manifests_pin_the_current_product_bytes():
    source = json.loads((CATALOGUE / "source-inputs.json").read_text(encoding="utf-8"))
    inventory = json.loads(
        (CATALOGUE / "product-source-inventory.json").read_text(encoding="utf-8")
    )
    assert source["product_baseline_head"] == inventory["baseline_head"]
    assert re.fullmatch(r"[0-9a-f]{40}", inventory["baseline_head"])
    for rows in (source["product_inputs"], inventory["files"]):
        assert rows and len({row["path"] for row in rows}) == len(rows)
        for row in rows:
            relative = PurePosixPath(row["path"])
            assert not relative.is_absolute() and ".." not in relative.parts
            assert relative.parts[0] in {"src", "apps"}
            # Git checkout can use CRLF on Windows; hosted Linux compares the
            # corresponding LF Git blob bytes before importing any product.
            raw = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
            assert len(raw) == row["size"], row["path"]
            assert hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]


def test_catalogue_inventory_covers_each_product_module_and_selected_inputs():
    source = json.loads((CATALOGUE / "source-inputs.json").read_text(encoding="utf-8"))
    inventory = json.loads(
        (CATALOGUE / "product-source-inventory.json").read_text(encoding="utf-8")
    )
    pinned = {row["path"]: row for row in inventory["files"]}
    modules = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "remote_ops_workspace").glob("*.py")
    }
    assert set(pinned) == modules | {"src/remote_ops_workspace/py.typed"}
    for row in source["product_inputs"]:
        if row["path"].startswith("src/"):
            assert pinned[row["path"]] == row
    assert set(source["gate_inputs"]) == {
        path.name for path in CATALOGUE.iterdir() if path.is_file()
    }

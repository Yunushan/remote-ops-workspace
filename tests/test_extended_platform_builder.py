from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_builder_identity_context_accepts_release_run_and_source_sha() -> None:
    builder = _load_builder()

    errors = builder.check_builder_identity_context(
        "linux-i386",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "a" * 40,
    )

    assert errors == []


def test_builder_identity_context_requires_lowercase_source_sha() -> None:
    builder = _load_builder()

    errors = builder.check_builder_identity_context(
        "linux-armhf",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "A" * 40,
    )

    assert "linux-armhf builder identity --source-head-sha must be a 40-character lowercase Git SHA" in errors


def test_builder_identity_records_source_head_sha() -> None:
    builder = _load_builder()

    identity = builder.builder_identity(
        "linux-i386",
        release_tag="v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        source_head_sha="a" * 40,
    )

    assert identity["source_head_sha"] == "a" * 40


def test_builder_identity_output_path_requires_target_scoped_name(tmp_path: Path) -> None:
    builder = _load_builder()
    output = tmp_path / "builder.json"

    errors = builder.check_builder_identity_output_path("linux-i386", output)

    assert (
        "linux-i386 builder identity output file name must be "
        "builder-identity-linux-i386.json, got 'builder.json'"
    ) in errors


def _load_builder():
    path = Path("scripts/check_extended_platform_builder.py")
    spec = importlib.util.spec_from_file_location("check_extended_platform_builder", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

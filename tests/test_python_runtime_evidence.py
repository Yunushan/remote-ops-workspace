from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_runtime_evidence_distinguishes_release_candidate_from_final_ga() -> None:
    writer = _load_script("write_python_runtime_evidence.py")
    evidence = _synthetic_runtime_evidence(releaselevel="candidate")

    rc_errors = writer.validate_runtime_evidence(
        evidence,
        expected_version="3.15",
        require_standard_gil=True,
        require_final=False,
    )
    final_errors = writer.validate_runtime_evidence(
        evidence,
        expected_version="3.15",
        require_standard_gil=True,
        require_final=True,
    )

    assert rc_errors == []
    assert any("releaselevel=final" in error for error in final_errors)


def test_runtime_evidence_rejects_wrong_line_and_free_threaded_build() -> None:
    writer = _load_script("write_python_runtime_evidence.py")
    evidence = _synthetic_runtime_evidence(releaselevel="final")
    evidence["python"]["version_info"]["minor"] = 14
    evidence["python"]["gil_enabled"] = False
    evidence["python"]["gil_disabled_config"] = True

    errors = writer.validate_runtime_evidence(
        evidence,
        expected_version="3.15",
        require_standard_gil=True,
        require_final=True,
    )

    assert any("expected 3.15" in error for error in errors)
    assert any("free-threaded" in error for error in errors)
    assert any("GIL to be enabled" in error for error in errors)


def test_runtime_evidence_writer_emits_sorted_machine_readable_json(tmp_path: Path) -> None:
    writer = _load_script("write_python_runtime_evidence.py")
    target = tmp_path / "runtime.json"

    writer.write_evidence(target, {"z": 1, "a": {"passed": True}})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "a": {"passed": True},
        "z": 1,
    }
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_distribution_install_checker_requires_exact_wheel_and_sdist(tmp_path: Path) -> None:
    checker = _load_script("check_python_distribution_install.py")
    wheel = tmp_path / "remote_ops_workspace-1.0.21-py3-none-any.whl"
    sdist = tmp_path / "remote_ops_workspace-1.0.21.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")

    assert checker.find_distribution_artifacts(tmp_path) == [
        ("wheel", wheel),
        ("sdist", sdist),
    ]
    assert len(checker.sha256_file(wheel)) == 64

    (tmp_path / "duplicate.whl").write_bytes(b"duplicate")
    try:
        checker.find_distribution_artifacts(tmp_path)
    except ValueError as exc:
        assert "exactly one wheel" in str(exc)
    else:
        raise AssertionError("duplicate wheel set must be rejected")


def test_distribution_install_checker_stages_artifact_bytes(tmp_path: Path) -> None:
    checker = _load_script("check_python_distribution_install.py")
    artifact = tmp_path / "build" / "package.whl"
    artifact.parent.mkdir()
    artifact.write_bytes(b"immutable-wheel-bytes")
    smoke_root = tmp_path / "smoke"

    staged = checker.stage_distribution_artifact(artifact, smoke_root)

    assert staged.parent.parent == smoke_root / "artifacts"
    assert staged.name == "package.whl"
    assert staged.read_bytes() == artifact.read_bytes()
    assert staged != artifact


def _synthetic_runtime_evidence(*, releaselevel: str) -> dict[str, object]:
    writer = _load_script("write_python_runtime_evidence.py")
    return {
        "python": {
            "implementation": "CPython",
            "gil_enabled": True,
            "gil_disabled_config": False,
            "version_info": {
                "major": 3,
                "minor": 15,
                "micro": 0,
                "releaselevel": releaselevel,
                "serial": 1,
            },
        },
        "distributions": {name: "1.0" for name in writer.REQUIRED_DISTRIBUTIONS},
    }


def _load_script(name: str):
    path = Path("scripts") / name
    spec = importlib.util.spec_from_file_location(f"test_{path.stem}_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

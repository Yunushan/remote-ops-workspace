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
    wheel = tmp_path / "remote_ops_workspace-1.0.27-py3-none-any.whl"
    sdist = tmp_path / "remote_ops_workspace-1.0.27.tar.gz"
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


def _gui_source_fixture(tmp_path):
    checker = _load_script("check_python_distribution_install.py")
    for index, module in enumerate(checker.GUI_SOURCE_MODULES):
        path = tmp_path / "src" / "remote_ops_workspace" / (module + ".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("# inert source fixture " + str(index) + "\n").encode())
    return checker


def _gui_archive_fixture(checker, tmp_path, kind, changes=()):
    import gzip
    import io
    import stat
    import tarfile
    import zipfile

    artifact = tmp_path / ("remote_ops_workspace-1.0.27-py3-none-any.whl" if kind == "wheel" else "remote_ops_workspace-1.0.27.tar.gz")
    prefix = "" if kind == "wheel" else "remote_ops_workspace-1.0.27/src/"
    members = [(prefix + "remote_ops_workspace/" + module + ".py", "regular", (tmp_path / "src/remote_ops_workspace" / (module + ".py")).read_bytes()) for module in checker.GUI_SOURCE_MODULES]
    for action, value in changes:
        if action == "remove":
            members.pop(0)
        elif action == "duplicate":
            members.append(members[0])
        elif action == "alias":
            name, member_type, raw = members[0]
            members[0] = (value(name), member_type, raw)
        elif action == "bytes":
            name, member_type, _raw = members[0]
            members[0] = (name, member_type, value)
        elif action == "type":
            name, _member_type, raw = members[0]
            members[0] = (name, value, raw)
    buffer = io.BytesIO()
    if kind == "wheel":
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, member_type, raw in members:
                if member_type == "directory":
                    name += "/"
                info = zipfile.ZipInfo(name)
                # Windows ZipInfo construction normalizes backslashes. Preserve
                # the intended hostile literal bytes in this parser fixture.
                info.filename = name
                info.create_system = 3
                mode = stat.S_IFREG if member_type == "regular" else stat.S_IFLNK if member_type == "symlink" else stat.S_IFDIR
                info.external_attr = (mode | 0o644) << 16
                archive.writestr(info, raw)
        artifact.write_bytes(buffer.getvalue())
    else:
        with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, member_type, raw in members:
                info = tarfile.TarInfo(name)
                info.type = {"regular": tarfile.REGTYPE, "symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE, "directory": tarfile.DIRTYPE}[member_type]
                info.size = len(raw) if member_type == "regular" else 0
                info.linkname = "synthetic-private-link" if member_type in {"symlink", "hardlink"} else ""
                archive.addfile(info, io.BytesIO(raw) if member_type == "regular" else None)
        artifact.write_bytes(gzip.compress(buffer.getvalue(), mtime=0))
    return artifact


def test_gui_distribution_members_equal_all_five_canonical_sources(tmp_path):
    checker = _gui_source_fixture(tmp_path)
    for kind in ("wheel", "sdist"):
        artifact = _gui_archive_fixture(checker, tmp_path, kind)
        result = checker.validate_distribution_gui_sources(kind, artifact, tmp_path)
        assert result["passed"] is True
        assert result["artifact_sha256"] == checker.sha256_file(artifact)
        assert len(result["members"]) == 5
        assert {item["source_path"] for item in result["members"]} == {"src/remote_ops_workspace/" + module + ".py" for module in checker.GUI_SOURCE_MODULES}
        for item in result["members"]:
            source = tmp_path / item["source_path"]
            assert item["sha256"] == checker.sha256_file(source)
            assert item["size"] == source.stat().st_size


def test_gui_distribution_missing_duplicate_modified_and_link_members_refuse(tmp_path):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    for kind in ("wheel", "sdist"):
        changes = [("remove", None), ("duplicate", None), ("bytes", b"changed"), ("type", "symlink"), ("type", "directory")]
        if kind == "sdist":
            changes.append(("type", "hardlink"))
        for change in changes:
            artifact = _gui_archive_fixture(checker, tmp_path, kind, [change])
            with pytest.raises(ValueError):
                checker.validate_distribution_gui_sources(kind, artifact, tmp_path)


def test_gui_distribution_aliases_cannot_satisfy_literal_member_names(tmp_path):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    aliases = (lambda name: name.upper(), lambda name: "./" + name, lambda name: name.replace("/", "\\"), lambda name: "parent/../" + name, lambda name: name + ".", lambda name: name + " ")
    for kind in ("wheel", "sdist"):
        for alias in aliases:
            artifact = _gui_archive_fixture(checker, tmp_path, kind, [("alias", alias)])
            with pytest.raises(ValueError):
                checker.validate_distribution_gui_sources(kind, artifact, tmp_path)


def test_gui_distribution_same_size_modified_source_is_refused(tmp_path):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    for kind in ("wheel", "sdist"):
        original = (tmp_path / "src/remote_ops_workspace/gui_terminal.py").read_bytes()
        artifact = _gui_archive_fixture(checker, tmp_path, kind, [("bytes", b"!" + original[1:])])
        with pytest.raises(ValueError, match="member-bytes-mismatch"):
            checker.validate_distribution_gui_sources(kind, artifact, tmp_path)


def test_gui_distribution_enforces_archive_member_and_expansion_bounds(tmp_path, monkeypatch):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    for kind in ("wheel", "sdist"):
        artifact = _gui_archive_fixture(checker, tmp_path, kind)
        with monkeypatch.context() as scoped:
            scoped.setattr(checker, "GUI_MEMBER_LIMIT", 3)
            with pytest.raises(ValueError):
                checker.validate_distribution_gui_sources(kind, artifact, tmp_path)
        with monkeypatch.context() as scoped:
            scoped.setattr(checker, "GUI_EXPANDED_LIMIT", 32)
            with pytest.raises(ValueError, match="expanded-or-count-bound"):
                checker.validate_distribution_gui_sources(kind, artifact, tmp_path)
        with monkeypatch.context() as scoped:
            scoped.setattr(checker, "GUI_ARCHIVE_LIMIT", 8)
            with pytest.raises(ValueError, match="file-bound-or-type"):
                checker.validate_distribution_gui_sources(kind, artifact, tmp_path)


def test_gui_distribution_refuses_malformed_directory_and_compressed_input(tmp_path):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    for kind in ("wheel", "sdist"):
        artifact = _gui_archive_fixture(checker, tmp_path, kind)
        artifact.write_bytes(b"not-an-archive")
        with pytest.raises((ValueError, OSError, EOFError)):
            checker.validate_distribution_gui_sources(kind, artifact, tmp_path)
    artifact = _gui_archive_fixture(checker, tmp_path, "wheel")
    raw = artifact.read_bytes()
    artifact.write_bytes(raw + b"trailing-data")
    with pytest.raises(ValueError, match="directory-bound"):
        checker.validate_distribution_gui_sources("wheel", artifact, tmp_path)


def test_gui_distribution_revalidates_original_and_checkout_after_read(tmp_path, monkeypatch):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    for kind in ("wheel", "sdist"):
        artifact = _gui_archive_fixture(checker, tmp_path, kind)
        original = checker._gui_regular_bytes
        counts = {}

        def changed(path, maximum, counts=counts, original=original, artifact=artifact):
            counts[path] = counts.get(path, 0) + 1
            result = original(path, maximum)
            return result + b"changed" if path == artifact and counts[path] == 2 else result

        with monkeypatch.context() as scoped:
            scoped.setattr(checker, "_gui_regular_bytes", changed)
            with pytest.raises(ValueError, match="input-changed"):
                checker.validate_distribution_gui_sources(kind, artifact, tmp_path)


def _gui_mock_smoke_calls(checker, monkeypatch):
    import types

    calls = []

    def mocked(command, **kwargs):
        calls.append(command)
        if command[-1] == "--json":
            stdout = json.dumps(dict.fromkeys(("adapter_ready_coverage", "evidence_summary", "feature_family_mapping", "platform_verified_readiness", "production_parity_coverage"), {}))
        elif "-c" in command:
            stdout = json.dumps({"distribution_version": "1.0.27", "package_version": "1.0.27"})
        else:
            stdout = ""
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(checker, "run_checked", mocked)
    return calls


def test_gui_distribution_mock_smoke_retains_all_existing_install_and_probe_steps(tmp_path, monkeypatch):
    checker = _gui_source_fixture(tmp_path)
    artifact = _gui_archive_fixture(checker, tmp_path, "wheel")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    calls = _gui_mock_smoke_calls(checker, monkeypatch)
    result = checker.smoke_distribution("wheel", artifact, expected_version="1.0.27", timeout_seconds=1, root=tmp_path / "smoke")
    assert result["passed"] is True
    assert result["gui_source_members"]["artifact_sha256"] == result["sha256"]
    assert len(calls) == 5
    assert calls[0][1:3] == ["-m", "venv"]
    assert calls[1][1:4] == ["-m", "pip", "install"]
    assert "--no-deps" in calls[1]
    assert calls[2][1:4] == ["-m", "pip", "check"]
    assert calls[3][1:3] == ["-I", "-c"]
    assert calls[4][1:] == ["-I", "-m", "remote_ops_workspace", "features", "--coverage", "--json"]


def test_gui_distribution_modified_staged_artifact_refuses_before_any_child(tmp_path, monkeypatch):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    artifact = _gui_archive_fixture(checker, tmp_path, "wheel")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    calls = _gui_mock_smoke_calls(checker, monkeypatch)
    stage = checker.stage_distribution_artifact

    def tampered(source, root):
        staged = stage(source, root)
        staged.write_bytes(b"tampered-wheel")
        return staged

    monkeypatch.setattr(checker, "stage_distribution_artifact", tampered)
    with pytest.raises(ValueError):
        checker.smoke_distribution("wheel", artifact, expected_version="1.0.27", timeout_seconds=1, root=tmp_path / "smoke")
    assert calls == []


def test_gui_distribution_modified_staged_artifact_after_probe_refuses(tmp_path, monkeypatch):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    artifact = _gui_archive_fixture(checker, tmp_path, "wheel")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    calls = _gui_mock_smoke_calls(checker, monkeypatch)
    mocked = checker.run_checked

    def tampered(command, **kwargs):
        result = mocked(command, **kwargs)
        if command[-1] == "--json":
            Path(calls[1][-1]).write_bytes(b"changed-after-install")
        return result

    monkeypatch.setattr(checker, "run_checked", tampered)
    with pytest.raises(ValueError, match="input-changed"):
        checker.smoke_distribution("wheel", artifact, expected_version="1.0.27", timeout_seconds=1, root=tmp_path / "smoke")
    assert len(calls) == 5


def test_gui_distribution_modified_staged_artifact_after_mock_venv_refuses_before_pip(tmp_path, monkeypatch):
    import pytest

    checker = _gui_source_fixture(tmp_path)
    artifact = _gui_archive_fixture(checker, tmp_path, "wheel")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    calls = _gui_mock_smoke_calls(checker, monkeypatch)
    mocked = checker.run_checked

    def tampered(command, **kwargs):
        result = mocked(command, **kwargs)
        for staged in (tmp_path / "smoke/artifacts").glob("*/*.whl"):
            staged.write_bytes(b"changed-by-mocked-venv")
        return result

    monkeypatch.setattr(checker, "run_checked", tampered)
    with pytest.raises(ValueError, match="staged-input-changed"):
        checker.smoke_distribution("wheel", artifact, expected_version="1.0.27", timeout_seconds=1, root=tmp_path / "smoke")
    assert len(calls) == 1


def test_gui_distribution_reader_keeps_same_api_ctime_guards(tmp_path, monkeypatch):
    import types

    import pytest

    checker = _gui_source_fixture(tmp_path)
    path = tmp_path / "src/remote_ops_workspace/gui_terminal.py"
    original = checker.os.fstat
    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")

    def different_api(fd):
        row = original(fd)
        values = {field: getattr(row, field) for field in fields}
        values["st_ctime_ns"] += 100
        return types.SimpleNamespace(**values)

    with monkeypatch.context() as scoped:
        scoped.setattr(checker.os, "fstat", different_api)
        assert checker._gui_regular_bytes(path, checker.GUI_SOURCE_LIMIT) == path.read_bytes()
    calls = []

    def changed_during_read(fd):
        calls.append(fd)
        row = different_api(fd)
        row.st_ctime_ns += len(calls)
        return row

    with monkeypatch.context() as scoped:
        scoped.setattr(checker.os, "fstat", changed_during_read)
        with pytest.raises(ValueError, match="file-changed"):
            checker._gui_regular_bytes(path, checker.GUI_SOURCE_LIMIT)


def test_gui_distribution_encrypted_alias_refuses_before_archive_open(tmp_path, monkeypatch):
    import struct
    import zipfile

    import pytest

    checker = _gui_source_fixture(tmp_path)
    artifact = _gui_archive_fixture(checker, tmp_path, "wheel", [("alias", lambda name: "PRIVATE/../" + name)])
    raw = bytearray(artifact.read_bytes())
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = raw.index(signature)
        struct.pack_into("<H", raw, start + offset, struct.unpack_from("<H", raw, start + offset)[0] | 1)
    artifact.write_bytes(raw)
    calls = []

    def never_open(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("member must be refused before open")

    monkeypatch.setattr(zipfile.ZipFile, "open", never_open)
    with pytest.raises(ValueError, match="member-missing-duplicate-type-or-size") as failure:
        checker.validate_distribution_gui_sources("wheel", artifact, tmp_path)
    assert calls == []
    assert "PRIVATE" not in str(failure.value)


def test_gui_distribution_unsupported_compression_has_fixed_public_refusal(tmp_path):
    import struct

    import pytest

    checker = _gui_source_fixture(tmp_path)
    artifact = _gui_archive_fixture(checker, tmp_path, "wheel")
    raw = bytearray(artifact.read_bytes())
    for signature, offset in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
        struct.pack_into("<H", raw, raw.index(signature) + offset, 99)
    artifact.write_bytes(raw)
    with pytest.raises(ValueError) as failure:
        checker.validate_distribution_gui_sources("wheel", artifact, tmp_path)
    assert str(failure.value) == "gui-source-archive-malformed"


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

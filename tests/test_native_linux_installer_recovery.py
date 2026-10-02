"""Harmless data/orchestration fixtures: no native packages, sudo or row launch."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path.cwd()
DRAFT = REPO / ".tmp/native-linux-prior-transition-draft-20261002"


@pytest.fixture
def module():
    # At adoption load the canonical tracked controller, never a test-only copy.
    path = REPO / "scripts/native_linux_installer_recovery.py"
    if not path.is_file():
        path = DRAFT / "scripts/native_linux_installer_recovery.py"
    spec = importlib.util.spec_from_file_location("linux_transition_test", path)
    import sys

    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def tar_bytes(rows):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w") as archive:
        for name, data, kind, mode, uid in rows:
            item = tarfile.TarInfo(name)
            item.type, item.mode, item.uid, item.gid = kind, mode, uid, 0
            item.linkname = "../outside" if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE} else ""
            item.size = len(data) if kind == tarfile.REGTYPE else 0
            archive.addfile(item, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
    return result.getvalue()


def payload_rows(module):
    return [
        (name if name != "." else "./", b"", tarfile.DIRTYPE, 0o755, 0)
        for name in sorted(module.DIRECTORIES)
    ] + [
        (
            name,
            b"harmless-fixture:" + name.encode(),
            tarfile.REGTYPE,
            0o755 if name == "usr/bin/row" else 0o644,
            0,
        )
        for name in module.FILES
    ]


def control_rows(version="1.0.24"):
    fields = {
        "Package": "remote-ops-workspace",
        "Version": version,
        "Section": "utils",
        "Priority": "optional",
        "Architecture": "amd64",
        "Installed-Size": "1",
        "Maintainer": "fixture@example.invalid",
        "Description": "harmless fixture\n continuation",
    }
    raw = ("\n".join(name + ": " + value for name, value in fields.items()) + "\n").encode()
    return [("./", b"", tarfile.DIRTYPE, 0o755, 0), ("./control", raw, tarfile.REGTYPE, 0o644, 0)]


def test_default_plan_never_launches_or_writes(module, monkeypatch, capsys):
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected launch")
    )
    monkeypatch.setattr(module, "save", lambda *a, **k: pytest.fail("unexpected receipt write"))
    assert module.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "plan-only"


def test_local_run_refuses_without_spoofing_gate_or_mutation(module, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(
        module.platform, "machine", lambda: pytest.fail("unexpected platform probe")
    )
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected launch")
    )
    monkeypatch.setattr(module, "save", lambda *a, **k: pytest.fail("unexpected receipt write"))
    assert module.main(["run", "--candidate-source-sha", "a" * 40]) == 1
    assert "refused" in capsys.readouterr().err


@pytest.mark.parametrize(
    "value", ["1.0", "01.0.27", "1.00.27", "1.0.27\n", "1.0.27-rc1", 3, "-1.0.1"]
)
def test_version_rejects_noncanonical(module, value):
    with pytest.raises(module.EvidenceError, match="noncanonical"):
        module.version_tuple(value)


def test_version_order_is_numeric(module):
    assert module.version_tuple("1.0.27") > module.version_tuple("1.0.24")
    assert module.version_tuple("1.10.0") > module.version_tuple("1.9.999")


@pytest.mark.parametrize("candidate", ["1.0.24", "1.0.23", "0.99.999"])
def test_same_or_older_candidate_is_not_an_upgrade(module, candidate):
    with pytest.raises(module.EvidenceError, match="not-newer"):
        module.require_newer_version(candidate)


@pytest.mark.parametrize(
    "name",
    [
        "../usr/bin/row",
        "/usr/bin/row",
        "usr//bin/row",
        "usr\\bin\\row",
        "usr/bin/../row",
        "././usr/bin/row",
        "usr/bin/row\x00",
        "usr/bin/row:stream",
    ],
)
def test_unsafe_payload_names(module, name):
    with pytest.raises(module.EvidenceError, match="unsafe"):
        module.member_name(name)


def test_genuine_shape_control_and_payload_are_data_only(module):
    module.control_identity(tar_bytes(control_rows()), "1.0.24")
    payload = module.payload_inventory(tar_bytes(payload_rows(module)), "1.0.24")
    assert len(payload.files) == 6
    assert payload.row_sha256 == hashlib.sha256(b"harmless-fixture:usr/bin/row").hexdigest()


@pytest.mark.parametrize(
    "extra", ["postinst", "preinst", "prerm", "postrm", "triggers", "conffiles"]
)
def test_maintainer_scripts_and_controls_fail_closed(module, extra):
    rows = control_rows() + [(extra, b"never executed", tarfile.REGTYPE, 0o755, 0)]
    with pytest.raises(module.EvidenceError, match="unreviewed"):
        module.control_identity(tar_bytes(rows), "1.0.24")


@pytest.mark.parametrize("change", ["version", "arch", "duplicate", "link", "owner"])
def test_control_identity_and_types(module, change):
    rows = control_rows()
    if change == "version":
        rows = control_rows("1.0.27")
    elif change == "arch":
        name, data, kind, mode, uid = rows[1]
        rows[1] = (name, data.replace(b"amd64", b"arm64"), kind, mode, uid)
    elif change == "duplicate":
        rows.append(rows[1])
    elif change == "link":
        rows[1] = ("control", b"", tarfile.SYMTYPE, 0o644, 0)
    else:
        name, data, kind, mode, _ = rows[1]
        rows[1] = (name, data, kind, mode, 123)
    with pytest.raises(module.EvidenceError):
        module.control_identity(tar_bytes(rows), "1.0.24")


@pytest.mark.parametrize(
    "change",
    ["duplicate", "missing", "symlink", "hardlink", "fifo", "unexpected", "mode", "owner", "bound"],
)
def test_payload_exact_regular_bounded_files(module, change, monkeypatch):
    rows = payload_rows(module)
    index = next(i for i, row in enumerate(rows) if row[0] == "usr/bin/row")
    if change == "duplicate":
        rows.append(rows[index])
    elif change == "missing":
        rows.pop(index)
    elif change == "unexpected":
        rows.append(("etc/unreviewed", b"fixture", tarfile.REGTYPE, 0o644, 0))
    elif change == "bound":
        monkeypatch.setattr(module, "MAX_FILE", 2)
    else:
        name, data, kind, mode, owner = rows[index]
        kind = {
            "symlink": tarfile.SYMTYPE,
            "hardlink": tarfile.LNKTYPE,
            "fifo": tarfile.FIFOTYPE,
        }.get(change, kind)
        rows[index] = (
            name,
            data,
            kind,
            0o4755 if change == "mode" else mode,
            123 if change == "owner" else owner,
        )
    with pytest.raises(module.EvidenceError):
        module.payload_inventory(tar_bytes(rows), "1.0.24")


@pytest.mark.parametrize("status", ["ii ", "rc ", "iU ", "iF ", "un "])
def test_any_dpkg_registration_refuses_before_install(module, status, tmp_path, monkeypatch):
    commands = SimpleNamespace(
        capture=lambda command, **kw: (
            f"remote-ops-workspace\t{status}\t1.0.24\tamd64\n".encode()
            if "dpkg-query" in command[0]
            else b""
        )
    )
    monkeypatch.setattr(module, "ROW", tmp_path / "row")
    monkeypatch.setattr(module, "DOCS", tmp_path / "docs")
    with pytest.raises(module.EvidenceError, match="registration"):
        module.assert_absent(commands)


@pytest.mark.parametrize("case", ["rpm", "row", "docs", "malformed"])
def test_rpm_paths_and_database_uncertainty_refuse(module, case, tmp_path, monkeypatch):
    row, docs = tmp_path / "row", tmp_path / "docs"
    if case in {"row", "docs"}:
        (row if case == "row" else docs).write_bytes(b"preexisting-user-state")
    commands = SimpleNamespace(
        capture=lambda command, **kw: (
            b"invalid\n"
            if case == "malformed"
            else b"remote-ops-workspace\t1.0.24\t1\tx86_64\n"
            if case == "rpm" and "rpm" in command[0]
            else b""
        )
    )
    monkeypatch.setattr(module, "ROW", row)
    monkeypatch.setattr(module, "DOCS", docs)
    with pytest.raises(module.EvidenceError):
        module.assert_absent(commands)
    if case in {"row", "docs"}:
        assert (row if case == "row" else docs).read_bytes() == b"preexisting-user-state"


def test_inventory_preserves_unknown_nested_locks_opaque_and_empty_dirs(module, tmp_path):
    home = tmp_path / "home"
    (home / "plugins/empty").mkdir(parents=True)
    (home / ".profiles.json.lock").write_bytes(b"known advisory")
    (home / "plugins/.plugin.lock").write_bytes(b"opaque\x00\xff")
    (home / "plugins/.profiles.json.lock").write_bytes(b"nested known basename is plugin state")
    before = module.inventory(home)
    (home / ".profiles.json.lock").write_bytes(b"changed advisory")
    assert module.inventory(home) == before
    for name in ("plugins/.plugin.lock", "plugins/.profiles.json.lock"):
        value = (home / name).read_bytes()
        (home / name).write_bytes(b"mutation")
        assert module.inventory(home) != before
        (home / name).write_bytes(value)
    (home / "plugins/empty").rmdir()
    assert module.inventory(home) != before


def test_wrong_native_bytes_prevent_any_launch(module, tmp_path, monkeypatch):
    row = tmp_path / "row"
    row.write_bytes(b"wrong executable bytes")
    commands = SimpleNamespace(capture=lambda *a, **kw: pytest.fail("native launched"))
    drill = module.Drill(tmp_path, commands, "a" * 40)
    drill.current = module.Payload(
        "1.0.24", (("usr/bin/row", 3, hashlib.sha256(b"old").hexdigest(), 0o755),)
    )
    monkeypatch.setattr(module, "ROW", row)
    monkeypatch.setattr(module, "installed_identity", lambda *a: None)
    with pytest.raises(module.EvidenceError, match="before-launch"):
        drill.command(row, ["--version"], {})
    assert drill.probes == []


def test_wrong_rescue_bytes_prevent_any_launch(module, tmp_path):
    row = tmp_path / "rescue"
    row.write_bytes(b"wrong")
    commands = SimpleNamespace(capture=lambda *a, **kw: pytest.fail("rescue launched"))
    drill = module.Drill(tmp_path, commands, "a" * 40)
    drill.rescue, drill.rescue_hash = row, hashlib.sha256(b"right").hexdigest()
    with pytest.raises(module.EvidenceError, match="before-launch"):
        drill.command(row, ["workspace", "backup"], {})


def test_uncertain_cleanup_cannot_query_or_purge(module, tmp_path):
    commands = SimpleNamespace(
        uncertain=True, capture=lambda *a, **kw: pytest.fail("cleanup command launched")
    )
    drill = module.Drill(tmp_path, commands, "a" * 40)
    drill.current = module.Payload("1.0.24", ())
    with pytest.raises(module.EvidenceError, match="uncertain"):
        drill.uninstall()
    assert drill.cleanup["process_tree_cleanup"] == "not-proven"


def test_private_environment_has_no_runner_tokens_loader_or_python_overrides(
    module, tmp_path, monkeypatch
):
    for key in (
        "GITHUB_TOKEN",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "ROW_HOME",
    ):
        monkeypatch.setenv(key, "private-sentinel")
    found = module.private_environment(tmp_path / "home", tmp_path, "vault", "backup")
    assert "private-sentinel" not in json.dumps(found)
    assert found["ROW_VAULT_PASSWORD"] == "vault"


def test_prior_pin_mutation_refused_before_network(module, tmp_path, monkeypatch):
    pins = json.loads(module.EXPECTED_PINS)
    pins["assets"][0]["size"] += 1
    path = tmp_path / module.PINS
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(pins), encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.native, "api_json", lambda *a: pytest.fail("network request"))
    with pytest.raises(module.EvidenceError, match="immutable"):
        module.previous_assets(tmp_path)


def file_snapshot(home):
    return {
        "dirs": [p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_dir()],
        "files": {
            p.relative_to(home).as_posix(): base64.b64encode(p.read_bytes()).decode()
            for p in home.rglob("*")
            if p.is_file()
        },
    }


def restore_snapshot(home, snapshot):
    home.mkdir()
    for name in snapshot["dirs"]:
        (home / name).mkdir(parents=True, exist_ok=True)
    for name, data in snapshot["files"].items():
        (home / name).parent.mkdir(parents=True, exist_ok=True)
        (home / name).write_bytes(base64.b64decode(data))


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "wrong-negative-reason",
        "omit-plugin-lock",
        "wrong-rollback-version",
        "snapshot-mutation",
    ],
)
def test_full_orchestration_prior_candidate_prior_and_restore_guards(
    module, tmp_path, monkeypatch, fault
):
    """Simulated CLI/storage only; asserts transition controller decisions."""
    fixture = json.loads(
        (REPO / "configs/workspace_recovery_fixture.json").read_text(encoding="utf-8")
    )
    calls, snapshots = [], {}

    def worker(runtime, home, payload):
        if payload["mode"] == "seed":
            home.mkdir()
            (home / "profiles.json").write_text(json.dumps(fixture["profiles"]), encoding="utf-8")
            (home / "vault.json").write_text("2", encoding="utf-8")
            for name, data in fixture["opaque_files"].items():
                (home / name).parent.mkdir(parents=True, exist_ok=True)
                (home / name).write_bytes(data.encode())
            for name in fixture["empty_directories"]:
                (home / name).mkdir(parents=True)
        state = [
            (name, (home / name).read_bytes().hex()) for name in ("profiles.json", "vault.json")
        ]
        return {
            "version": "1.0.24" if runtime.name == "wheel" else "1.0.27",
            "vault_version": int((home / "vault.json").read_text()),
            "semantic_sha256": hashlib.sha256(json.dumps(state).encode()).hexdigest(),
            "counts": {"profiles": len(json.loads((home / "profiles.json").read_text()))},
        }

    class FakeDrill:
        root, rescue = tmp_path, tmp_path / "rescue"

        def install(self, package, payload, package_hash):
            calls.append(("install", payload.version))

        def uninstall(self):
            calls.append(("uninstall",))

        def inspect(
            self, row, home, version, environment, secret, vault_version, profiles, new_secret=None
        ):
            calls.append(("inspect", version, vault_version))
            assert int((home / "vault.json").read_text()) == vault_version
            if fault == "wrong-rollback-version" and home.name == "restored-previous":
                raise module.EvidenceError("old-native-refused-v3")
            return {
                "version": version,
                "vault_version": vault_version,
                "profiles": len(profiles),
                "vault_decrypted": True,
            }

        def command(self, executable, arguments, environment, **kw):
            home = Path(environment["ROW_HOME"])
            if arguments[:2] == ["profile", "add"]:
                profiles = json.loads((home / "profiles.json").read_text())
                profiles.append({"name": "current-only"})
                (home / "profiles.json").write_text(json.dumps(profiles), encoding="utf-8")
            elif arguments[:2] == ["vault", "set"]:
                (home / "vault.json").write_text("3", encoding="utf-8")
            elif arguments[:2] == ["workspace", "backup"]:
                target = Path(arguments[arguments.index("--out") + 1])
                snapshots[str(target)] = file_snapshot(home)
                target.write_text(
                    json.dumps({"token": "A" * 64, "fixture": target.name}), encoding="utf-8"
                )
            elif arguments[:2] == ["workspace", "restore"]:
                backup = Path(arguments[arguments.index("--backup") + 1])
                destination = Path(arguments[arguments.index("--destination") + 1])
                if kw.get("expected_success") is False:
                    if fault == "snapshot-mutation":
                        backup.write_bytes(b"mutated encrypted snapshot")
                    if fault == "wrong-negative-reason":
                        return "error: unrelated missing backend"
                    return "error: " + (
                        "restore destination must be a new direct sibling of ROW_HOME"
                        if destination == home
                        else "invalid backup passphrase or corrupted workspace backup"
                    )
                restore_snapshot(destination, snapshots[str(backup)])
                if fault == "omit-plugin-lock":
                    (destination / "plugins/unrecognized/.plugin.lock").unlink()
            return ""

    monkeypatch.setattr(
        module, "state_worker", lambda drill, runtime, home, payload: worker(runtime, home, payload)
    )
    args = (
        FakeDrill(),
        tmp_path / "old.deb",
        tmp_path / "new.deb",
        module.Payload("1.0.24", ()),
        module.Payload("1.0.27", ()),
        "a" * 64,
        "b" * 64,
        tmp_path / "wheel",
        fixture,
        lambda value: calls.append(("phase", value)),
    )
    if fault:
        with pytest.raises(module.EvidenceError):
            module.transition(*args)
    else:
        result = module.transition(*args)
        assert [call[1] for call in calls if call[0] == "install"] == ["1.0.24", "1.0.27", "1.0.24"]
        assert [(call[1], call[2]) for call in calls if call[0] == "inspect"] == [
            ("1.0.24", 2),
            ("1.0.27", 2),
            ("1.0.27", 3),
            ("1.0.27", 3),
            ("1.0.24", 2),
        ]
        assert result["negative_restores"] == {
            "wrong-password": True,
            "tampered": True,
            "in-place": True,
        }
        assert "private-sentinel" not in json.dumps(result)


def test_public_failures_do_not_print_captured_private_text(module, monkeypatch, capsys):
    def refusal(args):
        raise ValueError("synthetic-secret-sentinel captured command text")

    monkeypatch.setattr(module, "run", refusal)
    assert module.main(["run"]) == 1
    assert "synthetic-secret-sentinel" not in capsys.readouterr().err


@pytest.mark.parametrize("fault", ["timeout", "output-bound"])
def test_bounded_command_uncertainty_keeps_owned_handle_and_blocks_followup(
    module, monkeypatch, fault
):
    calls = []

    class FakeChild:
        stdout, stderr = io.BytesIO(b"long fixture"), io.BytesIO(b"")
        stdin = None
        returncode = None

        def wait(self, timeout):
            if fault == "timeout":
                raise module.subprocess.TimeoutExpired("harmless-fake-child", timeout)
            self.returncode = 0
            return 0

    child = FakeChild()
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *a, **kw: calls.append("create") or child
    )
    monkeypatch.setattr(
        module,
        "load_module",
        lambda *a: SimpleNamespace(
            terminate_owned_process=lambda actual, **kw: calls.append(actual)
        ),
    )
    commands = module.Commands()
    with pytest.raises(module.EvidenceError):
        commands.capture(
            ["never-executed-fixture"], timeout=0.01, limit=2 if fault == "output-bound" else 100
        )
    assert calls == ["create", child]
    assert commands.uncertain is True
    assert commands.calls[-1]["process_tree_cleanup"] == "not-proven"
    with pytest.raises(module.EvidenceError, match="lifetime-uncertain"):
        commands.capture(["never-executed-followup"])
    assert calls == ["create", child]


def candidate_fixture(module, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    source = {"head": "a" * 40, "tree": "b" * 40, "checkout_bytes_sha256": "c" * 64}
    paths = module.input_paths()
    for path in paths.values():
        if path == Path(module.__file__):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"harmless fixture input")
    paths["pip_inspect"].write_text(
        json.dumps({"installed": [{"metadata": {"name": "fixture"}}]}), encoding="utf-8"
    )
    archives = [
        {
            "path": "build/native/linux/pyinstaller-dist/row",
            "artifact_sha256": module.digest(paths["original_row"]),
            "toc": [{"name": "fixture", "type": "s"}],
        }
    ]
    paths["archives"].write_text(json.dumps(archives), encoding="utf-8")
    paths["binding"].write_text(
        json.dumps({"status": "complete", "fixture": True}), encoding="utf-8"
    )
    assets = []
    for suffix in (
        "linux-amd64.deb",
        "linux-x86_64.rpm",
        "linux-x86_64.AppImage",
        "linux-x86_64-native.tar.gz",
    ):
        name = "remote-ops-workspace-v1.0.27-" + suffix
        path = tmp_path / "native-dist/linux" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"harmless-data:" + name.encode())
        assets.append(
            {
                "path": path.relative_to(tmp_path).as_posix(),
                "size": path.stat().st_size,
                "sha256": module.digest(path),
            }
        )
    manifest_path = (
        tmp_path
        / "native-dist/linux/remote-ops-workspace-v1.0.27-linux-x86_64-native-manifest.json"
    )
    manifest_path.write_text(
        json.dumps(
            [
                {"file": row["path"], "size_bytes": row["size"], "sha256": row["sha256"]}
                for row in assets
            ]
        ),
        encoding="utf-8",
    )
    assets.append(
        {
            "path": manifest_path.relative_to(tmp_path).as_posix(),
            "size": manifest_path.stat().st_size,
            "sha256": module.digest(manifest_path),
        }
    )
    checksums = (
        tmp_path
        / "native-dist/linux/remote-ops-workspace-v1.0.27-linux-x86_64-native-SHA256SUMS.txt"
    )
    checksums.write_text(
        "".join(row["sha256"] + "  " + Path(row["path"]).name + "\n" for row in assets),
        encoding="ascii",
    )
    assets.append(
        {
            "path": checksums.relative_to(tmp_path).as_posix(),
            "size": checksums.stat().st_size,
            "sha256": module.digest(checksums),
        }
    )
    finish = {
        "source": source,
        "source_unchanged": True,
        "target": module.TARGET,
        "run_id": "123",
        "run_attempt": "1",
        "native_build_outcome": "success",
        "native_smoke_outcome": "success",
        "native_pyinstaller_inventory_complete": True,
        "installed_project_sources_match_checkout": True,
        "pip_inspect_returncode": 0,
        "pip_inspect_json_valid": True,
        "native_executable_byte_binding": {
            "status": "bound",
            "report_path": paths["binding"].relative_to(tmp_path).as_posix(),
            "report_sha256": module.digest(paths["binding"]),
        },
        "pyinstaller_archive_inventory_sha256": module.digest(paths["archives"]),
        "pip_inspect_sha256": module.digest(paths["pip_inspect"]),
        "pip_inspect_stderr_sha256": module.digest(paths["pip_stderr"]),
        "assets": assets,
        "native_packaged_launchers": [
            {
                "path": paths["original_launcher"].relative_to(tmp_path).as_posix(),
                "sha256": module.digest(paths["original_launcher"]),
            }
        ],
    }
    checks = []

    def archive_inventory(path):
        checks.append(("fresh-carchive", path))
        return {**archives[0], "artifact_sha256": module.digest(path)}

    def byte_binding(report, *a):
        checks.append(("per-probe-binding",))
        assert report["status"] == "complete"

    verifier = SimpleNamespace(
        fingerprint=lambda: source,
        archive_inventory=archive_inventory,
        validate_posix_byte_binding=byte_binding,
    )
    monkeypatch.setattr(module, "load_module", lambda *a: verifier)
    monkeypatch.setattr(module, "checkout_fingerprint", lambda *a: source)
    monkeypatch.setattr(module, "git_output", lambda *a: "")
    return paths, finish, checks


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "wrong-head",
        "wrong-tree",
        "wrong-checkout",
        "wrong-run",
        "bad-build",
        "bad-smoke",
        "bad-inventory",
        "bad-pip-exit",
        "bad-pip-json",
        "wrong-binding",
        "changed-original",
        "changed-launcher",
        "changed-asset",
        "wrong-asset-path",
        "malformed-pip",
    ],
)
def test_candidate_finish_fresh_carchive_binding_assets_fail_closed(
    module, tmp_path, monkeypatch, fault
):
    paths, finish, checks = candidate_fixture(module, tmp_path, monkeypatch)
    if fault in {"wrong-head", "wrong-tree", "wrong-checkout"}:
        # verifier's fingerprint has its own copy so mutation cannot pass both.
        finish["source"] = dict(finish["source"])
        key = {
            "wrong-head": "head",
            "wrong-tree": "tree",
            "wrong-checkout": "checkout_bytes_sha256",
        }[fault]
        finish["source"][key] = "d" * len(finish["source"][key])
    elif fault == "wrong-run":
        finish["run_id"] = "999"
    elif fault in {"bad-build", "bad-smoke"}:
        finish["native_build_outcome" if fault == "bad-build" else "native_smoke_outcome"] = (
            "failure"
        )
    elif fault == "bad-inventory":
        finish["native_pyinstaller_inventory_complete"] = False
    elif fault == "bad-pip-exit":
        finish["pip_inspect_returncode"] = False
    elif fault == "bad-pip-json":
        finish["pip_inspect_json_valid"] = False
    elif fault == "wrong-binding":
        finish["native_executable_byte_binding"]["report_sha256"] = "d" * 64
    elif fault in {"changed-original", "changed-launcher"}:
        paths["original_row" if fault == "changed-original" else "original_launcher"].write_bytes(
            b"changed ignored build bytes"
        )
    elif fault == "changed-asset":
        (tmp_path / finish["assets"][0]["path"]).write_bytes(b"changed candidate package")
    elif fault == "wrong-asset-path":
        finish["assets"][0]["path"] = "elsewhere/" + Path(finish["assets"][0]["path"]).name
    elif fault == "malformed-pip":
        paths["pip_inspect"].write_text(json.dumps({"installed": "not a list"}), encoding="utf-8")
        finish["pip_inspect_sha256"] = module.digest(paths["pip_inspect"])
    paths["finish"].write_text(json.dumps(finish), encoding="utf-8")
    if fault:
        with pytest.raises(module.EvidenceError):
            module.candidate_assets(SimpleNamespace(), "a" * 40, "1.0.27")
    else:
        assets, actual, row_sha = module.candidate_assets(SimpleNamespace(), "a" * 40, "1.0.27")
        assert len(assets) == 6 and actual == finish
        assert row_sha == module.digest(paths["original_row"])
        assert checks == [("fresh-carchive", paths["original_row"]), ("per-probe-binding",)]


def test_deb_wrong_bytes_prevent_any_package_tool(module, tmp_path):
    package = tmp_path / "data-only.deb"
    package.write_bytes(b"not a native package")
    commands = SimpleNamespace(capture=lambda *a, **kw: pytest.fail("package tool launched"))
    with pytest.raises(module.EvidenceError, match="before-inspection"):
        module.inspect_deb(commands, package, "1.0.24", "0" * 64)


@pytest.mark.parametrize("fault", [None, "missing", "duplicate", "invalid-hash"])
def test_deb_expected_hashes_come_only_from_original_pins_and_finish(module, fault):
    pins = json.loads(module.EXPECTED_PINS)
    row = {
        "path": "native-dist/linux/remote-ops-workspace-v1.0.27-linux-amd64.deb",
        "sha256": "b" * 64,
    }
    finish = {"assets": [row]}
    if fault == "missing":
        finish["assets"] = []
    elif fault == "duplicate":
        finish["assets"].append(dict(row))
    elif fault == "invalid-hash":
        row["sha256"] = "not an artifact digest"
    if fault:
        with pytest.raises(module.EvidenceError, match="bound-deb-digest"):
            module.bound_deb_hashes(pins, finish, "1.0.27")
    else:
        assert module.bound_deb_hashes(pins, finish, "1.0.27") == (
            "d64ef85359085440798b86515c4751e73ef2633a3cd761f93b6d168d4a8456af",
            "b" * 64,
        )


def test_late_zero_exit_is_uncertain_and_not_success(module, monkeypatch):
    calls = []

    class FakeChild:
        stdout, stderr, stdin = io.BytesIO(b""), io.BytesIO(b""), None
        returncode = None

        def wait(self, timeout):
            module.time.sleep(0.03)
            self.returncode = 0
            return 0

    child = FakeChild()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: child)
    monkeypatch.setattr(
        module,
        "load_module",
        lambda *a: SimpleNamespace(
            terminate_owned_process=lambda actual, **kw: calls.append(actual)
        ),
    )
    commands = module.Commands()
    with pytest.raises(module.EvidenceError, match="late-completed"):
        commands.capture(["never-executed-fixture"], timeout=0.01)
    assert calls == [child]
    assert commands.uncertain and commands.calls[-1]["leader_exit_confirmed"] is True


def test_second_reader_setup_failure_is_owned_and_uncertain(module, monkeypatch):
    calls = []

    class FakeChild:
        stdout, stderr, stdin = io.BytesIO(b""), io.BytesIO(b""), None
        returncode = None

    child = FakeChild()
    start = module.threading.Thread.start

    def fail_second(thread):
        calls.append("reader-start")
        if calls.count("reader-start") == 2:
            raise RuntimeError("synthetic-reader-setup-failure")
        return start(thread)

    monkeypatch.setattr(module.threading.Thread, "start", fail_second)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: child)
    monkeypatch.setattr(
        module,
        "load_module",
        lambda *a: SimpleNamespace(
            terminate_owned_process=lambda actual, **kw: calls.append(actual)
        ),
    )
    commands = module.Commands()
    with pytest.raises(RuntimeError, match="synthetic-reader"):
        commands.capture(["never-executed-fixture"])
    assert calls == ["reader-start", "reader-start", child]
    assert commands.uncertain and commands.calls[-1]["leader_cleanup_attempted"] is True
    assert commands.calls[-1]["failure_type"] == "RuntimeError"


@pytest.mark.parametrize(
    "key,value",
    [
        ("RUNNER_ENVIRONMENT", "self-hosted"),
        ("GITHUB_REPOSITORY", "foreign/repo"),
        ("RUNNER_OS", "Windows"),
        ("RUNNER_ARCH", "ARM64"),
        ("os_name", "nt"),
        ("sys_platform", "darwin"),
        ("machine", "aarch64"),
        ("implementation", "pypy"),
        ("version_info", (3, 10, 0)),
        ("distro_id", "debian"),
        ("distro_version", "22.04"),
        ("workspace_absolute", False),
        ("workspace_resolved", "wrong-checkout"),
        ("controller_resolved", "untracked-prototype"),
        ("GITHUB_RUN_ID", "0"),
        ("GITHUB_RUN_ATTEMPT", "1\n"),
    ],
)
def test_individual_host_predicates_refuse_pure_data_without_spoofing_run(
    module, key, value, monkeypatch
):
    values = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Linux",
        "RUNNER_ARCH": "X64",
        "GITHUB_REPOSITORY": module.REPO,
        "os_name": "posix",
        "sys_platform": "linux",
        "machine": "x86_64",
        "implementation": "cpython",
        "version_info": (3, 14, 7),
        "distro_id": "ubuntu",
        "distro_version": "24.04",
        "workspace_absolute": True,
        "workspace_resolved": str(module.ROOT),
        "controller_resolved": str(module.ROOT / "scripts/native_linux_installer_recovery.py"),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *a, **kw: pytest.fail("unexpected launch")
    )
    monkeypatch.setattr(module, "save", lambda *a, **kw: pytest.fail("unexpected mutation"))
    module.validate_host_values(values, "a" * 40)
    values[key] = value
    with pytest.raises(module.EvidenceError):
        module.validate_host_values(values, "a" * 40)


def test_worker_uses_bounded_stdin_and_output_without_private_summary_fields(module, tmp_path):
    calls = []
    summary = {
        "version": "1.0.24",
        "semantic_sha256": "a" * 64,
        "vault_version": 2,
        "counts": dict.fromkeys(
            ("profiles", "group_defaults", "layouts", "snippets", "macros", "vault_items"), 1
        ),
    }
    commands = SimpleNamespace(
        capture=lambda args, environment, **kw: (
            calls.append((args, environment, kw)) or json.dumps(summary).encode()
        )
    )
    drill = SimpleNamespace(commands=commands, root=tmp_path)
    payload = {"mode": "seed", "secret": "synthetic-stdin-only-sentinel"}
    assert module.state_worker(drill, tmp_path / "wheel", tmp_path / "home", payload) == summary
    arguments, environment, options = calls[0]
    assert arguments[1:3] == ["-I", "-c"] and options["limit"] == 65536
    assert b"synthetic-stdin-only-sentinel" in options["stdin_payload"]
    assert "synthetic-stdin-only-sentinel" not in json.dumps(arguments)
    assert "GITHUB_TOKEN" not in environment


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/usr/bin/row",
        "plugins/unrecognized/../../outside",
        "./plugins/unrecognized/file",
        "elsewhere/file",
    ],
)
def test_fixture_opaque_paths_cannot_escape_private_plugin_subtree(module, path):
    fixture = {"opaque_files": {path: "never written"}, "empty_directories": []}
    with pytest.raises(module.EvidenceError):
        module.validate_fixture_paths(fixture)


def test_checkout_fingerprint_reads_actual_tracked_bytes_through_bounded_metadata(
    module, tmp_path, monkeypatch
):
    (tmp_path / "first").write_bytes(b"one")
    (tmp_path / "second").write_bytes(b"two")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    calls = []

    def capture(arguments, **options):
        calls.append((arguments, options))
        if "ls-files" in arguments:
            return b"first\0second\0"
        return ("a" * 40 if arguments[-1] == "HEAD" else "b" * 40).encode()

    commands = SimpleNamespace(capture=capture)
    before = module.checkout_fingerprint(commands)
    (tmp_path / "second").write_bytes(b"modified")
    after = module.checkout_fingerprint(commands)
    assert before["head"] == after["head"] and before["tree"] == after["tree"]
    assert before["checkout_bytes_sha256"] != after["checkout_bytes_sha256"]
    assert all(options["timeout"] == 30 for _, options in calls)


@pytest.mark.parametrize(
    "arch,build,smoke,proof,expected",
    [
        ("x86_64", "success", "success", "success", True),
        ("aarch64", "success", "success", "success", False),
        ("x86_64", "failure", "success", "success", False),
        ("x86_64", "success", "failure", "success", False),
        ("x86_64", "success", "success", "failure", False),
    ],
)
def test_workflow_recovery_needs_x64_and_actual_basic_finish(
    module, arch, build, smoke, proof, expected
):
    path = (
        REPO / ".github/workflows/native-candidate-validation.yml"
        if (REPO / "scripts/native_linux_installer_recovery.py").is_file()
        else DRAFT / ".github/workflows/native-candidate-validation.yml"
    )
    text = path.read_text(encoding="utf-8")
    section = text[text.index("  linux-native:") :]
    step = section[
        section.index(
            "      - name: Verify previous Linux DEB native upgrade and recovery"
        ) : section.index("      - name: Retain unreleased candidate proof and artifacts")
    ]
    condition = next(
        line.strip()[len("if: ${{ ") : -len(" }}")]
        for line in step.splitlines()
        if line.strip().startswith("if: ${{ ")
    )
    values = {
        "matrix.arch": arch,
        "steps.native-build.outcome": build,
        "steps.native-smoke.outcome": smoke,
        "steps.candidate-proof.outcome": proof,
    }
    expression = condition.replace("&&", "and")
    for key, value in values.items():
        expression = expression.replace(key, repr(value))
    assert eval(expression, {"__builtins__": {}}, {}) is expected
    assert (
        "timeout-minutes: 35" in step and "scripts/native_linux_installer_recovery.py run" in step
    )
    upload = section[
        section.index("      - name: Retain unreleased candidate proof and artifacts") :
    ]
    assert ".tmp/" not in upload and "build/native-smoke/linux-${{ matrix.arch }}/" in upload

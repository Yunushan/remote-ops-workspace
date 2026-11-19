from __future__ import annotations

import subprocess
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from scripts import managed_rpm_update as updater

OLD = updater.Header("1.0.27", "a" * 64, "b" * 64)
NEW = updater.Header("1.0.28", "c" * 64, "d" * 64)
FOREIGN = updater.Header("1.0.28", "e" * 64, "f" * 64)
INSTALLED_ROW = "/usr/bin/row\t-rwxr-xr-x\troot\troot\t" + OLD.launcher_sha256
OLD_METADATA = "\t".join((updater.PACKAGE, "0", OLD.version, "1", updater.ARCH, "8", OLD.header_sha256))


@pytest.mark.parametrize(("header", "files", "refusal"), [
    (OLD_METADATA, INSTALLED_ROW, None),
    (OLD_METADATA.replace("\t0\t", "\t1\t", 1), INSTALLED_ROW, "rpm-header-refused"),
    (OLD_METADATA, INSTALLED_ROW.replace("-rwx", "lrwx"), "rpm-payload-refused"),
    (OLD_METADATA, INSTALLED_ROW + "\n" + OLD_METADATA, "rpm-payload-refused"),
    (OLD_METADATA, INSTALLED_ROW + "\n" + INSTALLED_ROW.replace("/usr/bin/row", "/tmp/row"), "rpm-payload-refused"),
    (OLD_METADATA, "", "rpm-launcher-missing"),
])
def test_rpm_header_requires_a_single_stock_launcher(header, files, refusal, monkeypatch):
    def command(*argv):
        assert argv == (updater.RPM, "--query", updater.PACKAGE, "--queryformat", updater.QUERY)
        return SimpleNamespace(stdout=f"{header}\n{files}\n" if files else f"{header}\n")

    monkeypatch.setattr(updater, "native_command", command)
    if refusal:
        with pytest.raises(updater.UpdateError, match=refusal):
            updater.installed_header()
    else:
        assert updater.installed_header() == OLD


@pytest.mark.parametrize("prepared", [False, True])
def test_retention_authenticates_exact_rpm_and_holds_stage_during_snapshot(tmp_path, monkeypatch, prepared):
    stage, workspace = tmp_path / "stage", tmp_path / "home"
    stage.mkdir()
    if prepared:
        (stage / "manifest.json").write_bytes(b"previously staged")
    policy = object()
    name = f"{updater.PACKAGE}-v{OLD.version}-linux-{updater.ARCH}.rpm"
    artifact = SimpleNamespace(target=updater.TARGET, name=name, size=17, sha256="1" * 64)
    other = SimpleNamespace(target="linux-arm64", name=name, size=18, sha256="2" * 64)
    lease = []
    calls = []

    def fetch(config, root, *, current_home, expected_version):
        assert (config, root, current_home, expected_version) == (policy, stage, workspace, OLD.version)
        calls.append("fetch")

    @contextmanager
    def recover(config, root, *, current_home, expected_version):
        assert (config, root, current_home, expected_version) == (policy, stage, workspace, OLD.version)
        calls.append("verify")
        lease.append(root)
        try:
            yield root, SimpleNamespace(artifacts=(other, artifact)), {}
        finally:
            lease.pop()

    destination = tmp_path / updater.PREVIOUS

    def snapshot(source, selected, dest):
        assert lease == [stage] and source == stage / name and dest == destination and selected is artifact
        calls.append("snapshot")

    def retained(path, record):
        assert not lease and path == destination and record["sha256"] == artifact.sha256
        return OLD

    monkeypatch.setattr(updater, "stage_update", fetch)
    monkeypatch.setattr(updater, "verified_recovered_stage", recover)
    monkeypatch.setattr(updater, "snapshot_installer", snapshot)
    monkeypatch.setattr(updater, "retained_header", retained)
    record, header = updater.retain_package(policy, stage, workspace, OLD.version, destination)
    assert calls == ([] if prepared else ["fetch"]) + ["verify", "snapshot"]
    assert record == {"version": OLD.version, "size": artifact.size, "sha256": artifact.sha256} and header == OLD


@pytest.mark.parametrize("scenario", ["success", "install-failed", "predecessor-mismatch"])
def test_new_update_binds_the_original_installed_rpm_before_freshen(tmp_path, monkeypatch, scenario):
    args = SimpleNamespace(version=NEW.version, stage=tmp_path / "incoming", previous_stage=tmp_path / "rollback-stage",
                           policy=tmp_path / "new-policy.json", previous_policy=tmp_path / "old-policy.json")
    journal = tmp_path / "transaction" / updater.JOURNAL
    workspace = tmp_path / "workspace"
    settings = {"organization": "Publisher", "channel": "stable", "public_key": "fixture",
                "selected_target": updater.TARGET, "minimum_version": OLD.version}
    trace = []
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_: path)
    monkeypatch.setattr(updater, "installed_header", lambda: OLD)
    monkeypatch.setattr(updater, "load_policy", lambda _: SimpleNamespace(settings=settings))

    def retain(_, stage, home, version, path):
        assert home == workspace
        if path.name == updater.PREVIOUS:
            trace.append("retain-previous")
            assert stage == args.previous_stage and version == OLD.version
            repackaged = updater.Header(OLD.version, FOREIGN.header_sha256, FOREIGN.launcher_sha256)
            return {"version": version}, repackaged if scenario == "predecessor-mismatch" else OLD
        trace.append("retain-candidate")
        assert stage == args.stage and version == NEW.version
        return {"version": version}, NEW

    def journal_write(path, state, phase):
        assert path == journal
        trace.append(phase)
        return {**state, "phase": phase}

    def native(*argv):
        assert argv == (updater.RPM, "--freshen", str(journal.parent / updater.CANDIDATE))
        assert trace[-1] == "applying"
        trace.append("rpm-freshen")
        if scenario == "install-failed":
            raise subprocess.CalledProcessError(1, argv)

    def recover(path, state):
        assert path == journal and state["phase"] == "applying"
        trace.append("rollback")
        return {**state, "phase": "rolled-back"}

    monkeypatch.setattr(updater, "retain_package", retain)
    monkeypatch.setattr(updater, "verify_installation", lambda record: trace.append(f"check-{record.version}"))
    monkeypatch.setattr(updater, "journal_write", journal_write)
    monkeypatch.setattr(updater, "native_command", native)
    monkeypatch.setattr(updater, "rollback", recover)
    expected = ["retain-previous", "retain-candidate"]
    if scenario == "predecessor-mismatch":
        with pytest.raises(updater.UpdateError, match="retained-rpm-is-not-installed-predecessor"):
            updater.update(args, journal, workspace)
    else:
        report = updater.update(args, journal, workspace)
        expected += [f"check-{OLD.version}", "applying", "rpm-freshen"]
        if scenario == "install-failed":
            expected += ["rollback"]
            assert report["phase"] == "rolled-back"
        else:
            expected += [f"check-{NEW.version}", "applied"]
            assert report["phase"] == "applied"
    assert trace == expected


@pytest.mark.parametrize(("initial", "phase", "repair", "native_flags", "refusal"), [
    (NEW, "applied", False, ("--upgrade", "--oldpackage"), None),
    (NEW, "applying", False, ("--upgrade", "--oldpackage"), None),
    (OLD, "applying", False, (), None),
    (OLD, "applying", True, ("--reinstall",), None),
    (FOREIGN, "applying", False, (), "installed-rpm-changed"),
    (FOREIGN, "applied", False, (), "installed-rpm-identity-refused"),
    (OLD, "rolled-back", False, (), None),
])
def test_rollback_changes_only_a_bound_rpm(tmp_path, monkeypatch, initial, phase, repair, native_flags, refusal):
    journal = tmp_path / updater.JOURNAL
    state = {"phase": phase, "previous": {"version": OLD.version}, "candidate": {"version": NEW.version}}
    observed = initial
    needs_repair = repair
    calls, phases = [], []

    def retained(path, record):
        expected = OLD if path.name == updater.PREVIOUS else NEW
        assert record["version"] == expected.version
        return expected

    def verify(expected):
        if observed != expected:
            raise updater.UpdateError("installed-rpm-identity-refused")
        if needs_repair:
            raise updater.UpdateError("installed-launcher-digest-refused")

    def native(*argv):
        nonlocal observed, needs_repair
        calls.append(argv)
        assert phases == ["rolling-back"]
        observed, needs_repair = OLD, False

    def journal_write(name, state, next_phase):
        assert name == journal
        phases.append(next_phase)
        return {**state, "phase": next_phase}

    monkeypatch.setattr(updater, "retained_header", retained)
    monkeypatch.setattr(updater, "installed_header", lambda: observed)
    monkeypatch.setattr(updater, "verify_installation", verify)
    monkeypatch.setattr(updater, "native_command", native)
    monkeypatch.setattr(updater, "journal_write", journal_write)
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_: path)
    if refusal:
        with pytest.raises(updater.UpdateError, match=refusal):
            updater.rollback(journal, state)
        assert not phases
    else:
        assert updater.rollback(journal, state)["phase"] == "rolled-back"
        assert observed == OLD
        assert phases == (["rolling-back", "rolled-back"] if native_flags else
                          [] if phase == "rolled-back" else ["rolled-back"])
    assert calls == ([(updater.RPM, *native_flags, str(tmp_path / updater.PREVIOUS))] if native_flags else [])

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from remote_ops_workspace import cli
from remote_ops_workspace.models import Profile


class _Record(SimpleNamespace):
    def to_dict(self) -> dict[str, Any]:
        return {key: _json_value(value) for key, value in vars(self).items()}

    def printable(self) -> str:
        return "tool --flag"


def _json_value(value: Any) -> Any:
    if isinstance(value, _Record):
        return value.to_dict()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _ns(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


def _validation(*, passed: bool = True, summary: bool = True) -> _Record:
    return _Record(
        passed=passed,
        ok=passed,
        evidence_path=Path("evidence.json"),
        assets_dir=Path("assets"),
        summary=(
            {
                "schema": "row.test.v1",
                "release_target": "windows-x64",
                "certificate_id": "cert-1",
                "provider": "microsoft-capi",
                "profile": "edge",
                "remote_path": "/etc/app.conf",
                "syntax": "ini",
            }
            if summary
            else {}
        ),
        warnings=["review warning"],
        errors=["review error"],
    )


def _sftp_plan() -> _Record:
    return _Record(
        profile_name="edge",
        command=["sftp", "edge"],
        batch_commands=["ls /tmp"],
        notes=["safe operation"],
    )


class _ProfileStore:
    def __init__(self, profile: Profile) -> None:
        self.profile = profile

    def get(self, _name: str) -> Profile:
        return self.profile


def test_file_transfer_handlers_cover_all_command_shapes(monkeypatch) -> None:
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10")
    monkeypatch.setattr(cli, "ProfileStore", lambda: _ProfileStore(profile))
    plan = _sftp_plan()
    builders = [
        "build_sftp_interactive_plan",
        "build_sftp_list_plan",
        "build_sftp_get_plan",
        "build_sftp_put_plan",
        "build_sftp_mkdir_plan",
        "build_sftp_rm_plan",
        "build_sftp_rmdir_plan",
        "build_sftp_rename_plan",
        "build_sftp_remote_preview_plan",
    ]
    for name in builders:
        monkeypatch.setattr(cli, name, lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(cli, "run_sftp_interactive", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "run_sftp_batch", lambda *_args, **_kwargs: None)

    assert cli.cmd_files_open(_ns(profile="edge", dry_run=True)) == 0
    assert cli.cmd_files_ls(_ns(profile="edge", remote="/tmp", dry_run=True)) == 0
    assert (
        cli.cmd_files_get(
            _ns(
                profile="edge",
                remote="/tmp/a",
                local=Path("a"),
                recursive=True,
                force=True,
                dry_run=True,
            )
        )
        == 0
    )
    assert (
        cli.cmd_files_put(
            _ns(
                profile="edge",
                local=Path("a"),
                remote="/tmp/a",
                recursive=True,
                force=True,
                dry_run=True,
            )
        )
        == 0
    )
    assert cli.cmd_files_mkdir(_ns(profile="edge", remote="/tmp/new", dry_run=True)) == 0
    assert cli.cmd_files_rm(_ns(profile="edge", remote="/tmp/a", force=True, dry_run=True)) == 0
    assert cli.cmd_files_rmdir(_ns(profile="edge", remote="/tmp/old", force=True, dry_run=True)) == 0
    assert (
        cli.cmd_files_rename(
            _ns(profile="edge", old="/tmp/a", new="/tmp/b", force=True, dry_run=True)
        )
        == 0
    )

    item = _Record(action="get")
    queue_result = _Record(
        ok=True,
        dry_run=True,
        returncode=0,
        progress=[],
        stdout="",
        stderr="",
    )
    monkeypatch.setattr(cli, "parse_transfer_item_spec", lambda _spec: item)
    monkeypatch.setattr(cli, "build_sftp_queue_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(cli, "run_sftp_queue", lambda *_args, **_kwargs: queue_result)
    queue_args = _ns(profile="edge", op=["get /a ./a"], force=False, dry_run=True, json=True)
    assert cli.cmd_files_queue(queue_args) == 0
    queue_args.json = False
    assert cli.cmd_files_queue(queue_args) == 0
    queue_result.ok = False
    assert cli.cmd_files_queue(queue_args) == 1

    preview = _Record(
        path=Path("note.txt"),
        kind="file",
        exists=True,
        size=5,
        children=[],
        binary=False,
        truncated=False,
        text="hello",
        error="",
    )
    monkeypatch.setattr(cli, "preview_local_path", lambda *_args, **_kwargs: preview)
    preview_args = _ns(path=Path("note.txt"), bytes=100, entries=10, json=True)
    assert cli.cmd_files_preview_local(preview_args) == 0
    preview_args.json = False
    assert cli.cmd_files_preview_local(preview_args) == 0
    preview.error = "cannot read"
    assert cli.cmd_files_preview_local(preview_args) == 1

    remote_args = _ns(profile="edge", remote="/tmp/a", dry_run=True, json=True)
    assert cli.cmd_files_preview_remote(remote_args) == 0
    remote_args.json = False
    assert cli.cmd_files_preview_remote(remote_args) == 0


def test_ssh_browser_handlers_cover_preferences_and_reviews(monkeypatch) -> None:
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10")
    monkeypatch.setattr(cli, "ProfileStore", lambda: _ProfileStore(profile))
    preferences = _Record(
        location="side-by-side",
        overwrite_confirmation=True,
        column_widths={"name": 220, "size": 100},
        updated_at="now",
    )
    monkeypatch.setattr(cli, "load_moba_ssh_browser_preferences", lambda: preferences)
    monkeypatch.setattr(cli, "update_moba_ssh_browser_location", lambda _location: preferences)
    monkeypatch.setattr(cli, "update_moba_ssh_browser_columns", lambda _widths: preferences)
    assert cli.cmd_ssh_browser_status(_ns(json=True)) == 0
    assert cli.cmd_ssh_browser_status(_ns(json=False)) == 0
    preferences.overwrite_confirmation = False
    assert cli.cmd_ssh_browser_status(_ns(json=False)) == 0
    assert cli.cmd_ssh_browser_location(_ns(location="left", json=True)) == 0
    assert cli.cmd_ssh_browser_location(_ns(location="left", json=False)) == 0
    columns = _ns(name=220, size=None, modified=None, json=True)
    assert cli.cmd_ssh_browser_columns(columns) == 0
    columns.json = False
    assert cli.cmd_ssh_browser_columns(columns) == 0
    with pytest.raises(ValueError, match="at least one"):
        cli.cmd_ssh_browser_columns(_ns(name=None, size=None, modified=None, json=False))

    plan = _Record(
        command=["sftp", "edge"],
        location="side-by-side",
        terminal_visible=True,
        browser_visible=True,
        notes=["open note"],
    )
    monkeypatch.setattr(cli, "build_moba_ssh_browser_open_plan", lambda _profile: plan)
    assert cli.cmd_ssh_browser_open_plan(_ns(profile="edge", json=True)) == 0
    assert cli.cmd_ssh_browser_open_plan(_ns(profile="edge", json=False)) == 0
    plan.terminal_visible = False
    plan.browser_visible = False
    assert cli.cmd_ssh_browser_open_plan(_ns(profile="edge", json=False)) == 0

    review = _Record(
        allowed=True,
        confirmation_required=True,
        prompt="Overwrite?",
        notes=["review note"],
    )
    monkeypatch.setattr(cli, "review_moba_ssh_browser_overwrite", lambda *_args, **_kwargs: review)
    overwrite_args = _ns(
        action="upload",
        source="a",
        destination="b",
        destination_exists=True,
        force=False,
        json=True,
    )
    assert cli.cmd_ssh_browser_overwrite(overwrite_args) == 0
    overwrite_args.json = False
    assert cli.cmd_ssh_browser_overwrite(overwrite_args) == 0
    review.allowed = False
    review.confirmation_required = False
    review.prompt = ""
    assert cli.cmd_ssh_browser_overwrite(overwrite_args) == 1


def test_smartcard_handlers_cover_plans_reviews_and_evidence(monkeypatch) -> None:
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10")
    monkeypatch.setattr(cli, "ProfileStore", lambda: _ProfileStore(profile))
    inventory = _Record(
        provider="microsoft-capi",
        platform="windows",
        commands=[["certutil", "-scinfo"]],
        management_actions=["add", "remove"],
        notes=["inventory note"],
    )
    monkeypatch.setattr(cli, "build_smartcard_inventory_plan", lambda _provider: inventory)
    assert cli.cmd_smartcard_inventory_plan(_ns(provider="microsoft-capi", json=True)) == 0
    assert cli.cmd_smartcard_inventory_plan(_ns(provider="microsoft-capi", json=False)) == 0

    review = _Record(
        profile_name="edge",
        certificate_id="cert-1",
        allowed=True,
        confirmation_required=True,
        ssh_browser_multiplex_required=True,
        prompt="Use certificate?",
        profile_options={"certificate": "cert-1"},
        notes=["selection note"],
    )
    monkeypatch.setattr(cli, "review_smartcard_certificate_selection", lambda *_args, **_kwargs: review)
    select_args = _ns(
        profile="edge",
        certificate=["cert-1|Operator|microsoft-capi"],
        provider="microsoft-capi",
        certificate_id="cert-1",
        add_to_mobagent=True,
        force=False,
        json=True,
    )
    assert cli.cmd_smartcard_select_review(select_args) == 0
    select_args.json = False
    assert cli.cmd_smartcard_select_review(select_args) == 0
    review.allowed = False
    review.confirmation_required = False
    review.ssh_browser_multiplex_required = False
    review.prompt = ""
    assert cli.cmd_smartcard_select_review(select_args) == 1

    mobagent = _Record(
        action="add",
        certificate_id="cert-1",
        provider="microsoft-capi",
        command=["mobagent", "add"],
        notes=["agent note"],
    )
    monkeypatch.setattr(cli, "build_mobagent_smartcard_plan", lambda *_args, **_kwargs: mobagent)
    mobagent_args = _ns(
        certificate_id="cert-1",
        provider="microsoft-capi",
        action="add",
        agent_socket=None,
        json=True,
    )
    assert cli.cmd_smartcard_mobagent_plan(mobagent_args) == 0
    mobagent_args.json = False
    assert cli.cmd_smartcard_mobagent_plan(mobagent_args) == 0

    browser = _Record(
        profile_name="edge",
        certificate_id="cert-1",
        provider="microsoft-capi",
        ssh_browser_same_parameters=True,
        multiplex_mode_required=True,
        terminal_command=["ssh", "edge"],
        sftp_command=["sftp", "edge"],
        notes=["browser note"],
    )
    monkeypatch.setattr(cli, "build_smartcard_ssh_browser_plan", lambda *_args, **_kwargs: browser)
    browser_args = _ns(
        profile="edge",
        certificate_id="cert-1",
        provider="microsoft-capi",
        add_to_mobagent=True,
        json=True,
    )
    assert cli.cmd_smartcard_ssh_browser_plan(browser_args) == 0
    browser_args.json = False
    assert cli.cmd_smartcard_ssh_browser_plan(browser_args) == 0
    browser.ssh_browser_same_parameters = False
    browser.multiplex_mode_required = False
    assert cli.cmd_smartcard_ssh_browser_plan(browser_args) == 0

    validation = _validation(passed=True)
    bundle = _Record(
        validation=validation,
        evidence_path=Path("smartcard.json"),
        notes=["bundle note"],
    )
    monkeypatch.setattr(cli, "build_smartcard_release_evidence_bundle_plan", lambda *_args, **_kwargs: _Record())
    monkeypatch.setattr(cli, "write_smartcard_release_evidence_bundle", lambda _plan: bundle)
    evidence_args = _ns(
        profile="edge",
        certificate=["cert-1|Operator|microsoft-capi"],
        provider="microsoft-capi",
        certificate_id="cert-1",
        out_dir=Path("artifact"),
        management_evidence=Path("management.txt"),
        selection_evidence=Path("selection.txt"),
        mobagent_evidence=Path("mobagent.txt"),
        browser_evidence=Path("browser.txt"),
        release_target="windows-x64",
        add_to_mobagent=True,
        management_command="inventory",
        selection_command="select",
        mobagent_command="agent",
        browser_command="browser",
        gui_visible=True,
        add_remove_controls=True,
        openssh_public_key_visible=True,
        expert_setting_visible=True,
        certificate_selected=True,
        profile_saved=True,
        global_add_setting=True,
        agent_loaded_certificate=True,
        same_parameters_sftp=True,
        multiplex_mode=True,
        real_connected_session=True,
        sftp_browser_open=True,
        json=True,
    )
    assert cli.cmd_smartcard_evidence_bundle(evidence_args) == 0
    evidence_args.json = False
    validation.passed = False
    assert cli.cmd_smartcard_evidence_bundle(evidence_args) == 1


@pytest.mark.parametrize(
    ("handler_name", "dependency_name"),
    [
        ("cmd_smartcard_evidence_verify", "validate_smartcard_release_evidence"),
        ("cmd_text_evidence_verify", "validate_moba_text_release_evidence"),
        ("cmd_mobapt_cache_verify", "validate_mobapt_cache_evidence"),
        ("cmd_servers_evidence_verify", "validate_moba_server_release_evidence"),
        ("cmd_x11_evidence_verify", "validate_moba_x_server_release_evidence"),
    ],
)
def test_operational_evidence_verifiers_cover_output_and_failures(
    monkeypatch, handler_name: str, dependency_name: str
) -> None:
    result = _validation(passed=True, summary=True)
    monkeypatch.setattr(cli, dependency_name, lambda *_args, **_kwargs: result)
    handler = getattr(cli, handler_name)
    args = _ns(evidence=Path("evidence.json"), assets_dir=Path("assets"), json=True)
    assert handler(args) == 0
    args.json = False
    assert handler(args) == 0
    result.passed = False
    result.ok = False
    result.summary = {}
    assert handler(args) == 1


def test_text_handlers_cover_preview_write_diff_remote_and_evidence(
    monkeypatch, tmp_path: Path
) -> None:
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10")
    monkeypatch.setattr(cli, "ProfileStore", lambda: _ProfileStore(profile))
    preview = _Record(
        path=Path("note.txt"),
        exists=True,
        binary=False,
        size=5,
        sha256="a" * 64,
        line_count=1,
        notes=["preview note"],
        text="hello\n",
    )
    monkeypatch.setattr(cli, "preview_text_document", lambda *_args, **_kwargs: preview)
    preview_args = _ns(path=Path("note.txt"), bytes=100, lines=10, encoding="utf-8", json=True)
    assert cli.cmd_text_preview(preview_args) == 0
    preview_args.json = False
    assert cli.cmd_text_preview(preview_args) == 0
    preview.exists = False
    preview.binary = True
    preview.text = ""
    assert cli.cmd_text_preview(preview_args) == 1

    write_result = _Record(
        path=Path("note.txt"),
        changed=True,
        new_sha256="b" * 64,
        backup_path=Path("note.txt.bak"),
        notes=["write note"],
    )
    monkeypatch.setattr(cli, "write_text_document", lambda *_args, **_kwargs: write_result)
    write_args = _ns(
        path=Path("note.txt"),
        text="hello",
        text_file=None,
        encoding="utf-8",
        create=True,
        force=True,
        expected_sha256=None,
        no_backup=False,
        json=True,
    )
    assert cli.cmd_text_write(write_args) == 0
    write_args.json = False
    assert cli.cmd_text_write(write_args) == 0
    source = tmp_path / "source.txt"
    source.write_text("from file", encoding="utf-8")
    write_args.text = None
    write_args.text_file = source
    write_result.changed = False
    write_result.backup_path = None
    write_result.notes = []
    assert cli.cmd_text_write(write_args) == 0

    diff = _Record(equal=True, added_lines=0, removed_lines=0, hunk_count=0, unified_diff="")
    monkeypatch.setattr(cli, "diff_text_documents", lambda *_args, **_kwargs: diff)
    diff_args = _ns(left=Path("a"), right=Path("b"), context=3, encoding="utf-8", json=True)
    assert cli.cmd_text_diff(diff_args) == 0
    diff_args.json = False
    assert cli.cmd_text_diff(diff_args) == 0
    diff.equal = False
    diff.unified_diff = "--- a\n+++ b\n"
    assert cli.cmd_text_diff(diff_args) == 1

    sftp = _sftp_plan()
    remote_plan = _Record(
        remote_path="/etc/app.conf",
        local_path=Path("app.conf"),
        download_plan=sftp,
        upload_plan=sftp,
        notes=["remote note"],
    )
    monkeypatch.setattr(cli, "build_remote_text_edit_plan", lambda *_args, **_kwargs: remote_plan)
    remote_args = _ns(profile="edge", remote="/etc/app.conf", local=Path("app.conf"), json=True)
    assert cli.cmd_text_remote_plan(remote_args) == 0
    remote_args.json = False
    assert cli.cmd_text_remote_plan(remote_args) == 0

    tab_plan = _Record(
        remote_path="/etc/app.conf",
        local_path=Path("app.conf"),
        syntax="ini",
        encoding="utf-8",
        remote_sha256="a" * 64,
        download_plan=sftp,
        save_plan=sftp,
        conflict_policy="compare-before-save",
        notes=["tab note"],
    )
    monkeypatch.setattr(cli, "build_moba_text_editor_tab_plan", lambda *_args, **_kwargs: tab_plan)
    open_args = _ns(
        profile="edge",
        remote="/etc/app.conf",
        local=Path("app.conf"),
        remote_sha256="a" * 64,
        encoding="utf-8",
        json=True,
    )
    assert cli.cmd_text_open_remote(open_args) == 0
    open_args.json = False
    assert cli.cmd_text_open_remote(open_args) == 0
    tab_plan.remote_sha256 = ""
    assert cli.cmd_text_open_remote(open_args) == 0

    review = _Record(
        remote_path="/etc/app.conf",
        local_path=Path("app.conf"),
        allowed=True,
        conflict=True,
        confirmation_required=True,
        local_sha256="b" * 64,
        prompt="Overwrite?",
        upload_plan=sftp,
        notes=["save note"],
    )
    monkeypatch.setattr(cli, "review_moba_remote_text_save", lambda *_args, **_kwargs: review)
    review_args = _ns(
        profile="edge",
        remote="/etc/app.conf",
        local=Path("app.conf"),
        original_remote_sha256="a" * 64,
        current_remote_sha256="a" * 64,
        force=False,
        json=True,
    )
    assert cli.cmd_text_save_review(review_args) == 0
    review_args.json = False
    assert cli.cmd_text_save_review(review_args) == 0
    review.allowed = False
    review.conflict = False
    review.confirmation_required = False
    review.prompt = ""
    assert cli.cmd_text_save_review(review_args) == 1

    validation = _validation(passed=True)
    bundle = _Record(
        validation=validation,
        evidence_path=Path("text.json"),
        notes=["bundle note"],
    )
    monkeypatch.setattr(cli, "build_moba_text_release_evidence_bundle_plan", lambda *_args, **_kwargs: _Record())
    monkeypatch.setattr(cli, "write_moba_text_release_evidence_bundle", lambda *_args, **_kwargs: bundle)
    evidence_args = _ns(
        profile="edge",
        remote="/etc/app.conf",
        out_dir=Path("artifact"),
        local=Path("app.conf"),
        remote_sha256="a" * 64,
        open_evidence=Path("open.txt"),
        save_review_evidence=Path("review.txt"),
        save_evidence=Path("save.txt"),
        connected_evidence=Path("connected.txt"),
        release_target="windows-x64",
        encoding="utf-8",
        open_command="open",
        save_review_command="review",
        save_command="save",
        real_connected_session=True,
        sftp_browser_open=True,
        editor_tab_visible=True,
        json=True,
    )
    assert cli.cmd_text_evidence_bundle(evidence_args) == 0
    evidence_args.json = False
    validation.passed = False
    assert cli.cmd_text_evidence_bundle(evidence_args) == 1


def test_key_network_mobapt_handlers_cover_runtime_states(monkeypatch, tmp_path: Path) -> None:
    plan = _Record()
    monkeypatch.setattr(cli, "build_keygen_plan", lambda **_kwargs: plan)
    monkeypatch.setattr(cli, "run_keygen", lambda *_args, **_kwargs: None)
    key_args = _ns(
        passphrase_env=None,
        out=tmp_path / "id",
        type="ed25519",
        bits=None,
        comment="operator",
        resident=False,
        dry_run=True,
    )
    assert cli.cmd_keygen(key_args) == 0
    monkeypatch.setenv("KEY_PASS", "secret")
    key_args.passphrase_env = "KEY_PASS"
    assert cli.cmd_keygen(key_args) == 0

    monkeypatch.setattr(cli, "build_network_tool_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(cli, "run_network_tool", lambda *_args, **_kwargs: None)
    assert cli.cmd_nettool_plan(_ns(tool="ping", target="host", count=1, dry_run=True)) == 0
    assert cli.cmd_nettool_plan(_ns(tool="trace", target="host", dry_run=True)) == 0
    monkeypatch.setattr(cli, "check_tcp_port", lambda *_args, **_kwargs: True)
    port_args = _ns(host="host", port=22, timeout=1)
    assert cli.cmd_nettool_port(port_args) == 0
    monkeypatch.setattr(cli, "check_tcp_port", lambda *_args, **_kwargs: False)
    assert cli.cmd_nettool_port(port_args) == 1

    status = _Record(
        system="windows",
        adapter_mode=True,
        embedded_runtime_available=True,
        package_managers=[
            _Record(key="apt", available=True, executable="apt"),
            _Record(key="yum", available=False, executable=""),
        ],
        base_tools=[
            _Record(name="bash", available=True, executable="bash"),
            _Record(name="grep", available=False, executable=""),
        ],
        notes=["status note"],
    )
    monkeypatch.setattr(cli, "build_mobapt_environment_status", lambda: status)
    assert cli.cmd_mobapt_status(_ns(json=True)) == 0
    assert cli.cmd_mobapt_status(_ns(json=False)) == 0
    status.adapter_mode = False
    status.embedded_runtime_available = False
    assert cli.cmd_mobapt_status(_ns(json=False)) == 0

    runtime = _Record(
        embedded_runtime_available=True,
        roots=[Path("runtime")],
        candidates=[
            _Record(name="runtime", available=True, tools=["bash"], packages=["htop"]),
            _Record(name="", available=False, tools=[], packages=[]),
        ],
        notes=["runtime note"],
    )
    monkeypatch.setattr(cli, "build_mobapt_runtime_status", lambda **_kwargs: runtime)
    runtime_args = _ns(root=[Path("runtime")], json=True)
    assert cli.cmd_mobapt_runtime_status(runtime_args) == 0
    runtime_args.json = False
    assert cli.cmd_mobapt_runtime_status(runtime_args) == 0
    runtime.embedded_runtime_available = False
    runtime.candidates = []
    assert cli.cmd_mobapt_runtime_status(runtime_args) == 0

    validation = _validation(passed=True)
    bundle = _Record(
        evidence_validation=validation,
        root=Path("bundle"),
        manifest_path=Path("bundle/manifest.json"),
        package_index_path=Path("bundle/packages.json"),
        evidence_path=Path("bundle/evidence.json"),
        tool_count=2,
        package_count=1,
        shimmed_tools=["bash"],
        synthetic_packages=["htop"],
        notes=["bundle note"],
    )
    monkeypatch.setattr(cli, "build_mobapt_runtime_bundle_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(cli, "write_mobapt_runtime_bundle", lambda _plan: bundle)
    bundle_args = _ns(
        tool_source=["bash=bash.exe"],
        package_source=["htop=htop.zip"],
        out=Path("bundle"),
        tool=["bash"],
        package=["htop"],
        runtime_name="mobapt",
        version="1.0",
        release_target="windows-x64",
        terminal_probe_command="bash --version",
        allow_shims=True,
        copy_host_tools=False,
        json=True,
    )
    assert cli.cmd_mobapt_bundle_runtime(bundle_args) == 0
    bundle_args.json = False
    assert cli.cmd_mobapt_bundle_runtime(bundle_args) == 0
    validation.passed = False
    bundle.shimmed_tools = []
    bundle.synthetic_packages = []
    assert cli.cmd_mobapt_bundle_runtime(bundle_args) == 1

    package_result = _Record(
        executed=True,
        ok=True,
        returncode=0,
        notes=["package note"],
        stdout="installed\n",
        stderr="warning\n",
    )
    monkeypatch.setattr(cli, "build_mobapt_package_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(cli, "run_mobapt_package_plan", lambda *_args, **_kwargs: package_result)
    package_args = _ns(
        action="install",
        package="htop",
        manager="apt",
        execute=True,
        timeout=10,
        json=True,
    )
    assert cli.cmd_mobapt_package(package_args) == 0
    package_args.json = False
    assert cli.cmd_mobapt_package(package_args) == 0
    package_result.executed = False
    package_result.ok = False
    package_result.stdout = ""
    package_result.stderr = ""
    assert cli.cmd_mobapt_package(package_args) == 1


def test_server_handlers_cover_status_bundle_and_lifecycle(monkeypatch) -> None:
    lifecycle = _Record(state="running", pid=42)
    status = _Record(
        system="windows",
        services=[
            _Record(
                key="ssh",
                available=True,
                default_port=22,
                selected_runtime="sshd",
                lifecycle=lifecycle,
            ),
            _Record(
                key="ftp",
                available=False,
                default_port=21,
                selected_runtime="",
                lifecycle=None,
            ),
        ],
        notes=["server note"],
    )
    monkeypatch.setattr(cli, "build_moba_server_suite_status", lambda: status)
    assert cli.cmd_servers_status(_ns(json=True)) == 0
    assert cli.cmd_servers_status(_ns(json=False)) == 0
    lifecycle.pid = None
    assert cli.cmd_servers_status(_ns(json=False)) == 0

    runtime = _Record(
        packaged_available=True,
        roots=[Path("servers")],
        service_coverage={"ssh": True, "ftp": False},
        notes=["runtime note"],
    )
    monkeypatch.setattr(cli, "build_moba_server_runtime_status", lambda **_kwargs: runtime)
    runtime_args = _ns(root=[Path("servers")], json=True)
    assert cli.cmd_servers_runtime_status(runtime_args) == 0
    runtime_args.json = False
    assert cli.cmd_servers_runtime_status(runtime_args) == 0
    runtime.packaged_available = False
    assert cli.cmd_servers_runtime_status(runtime_args) == 0

    plan = _Record(
        service="ssh",
        host="127.0.0.1",
        port=22,
        hardening_profile="strict",
        auth_required=True,
        notes=["plan note"],
    )
    bundle = _Record(
        runtime_status=_Record(service_coverage={"ssh": True}),
        root=Path("bundle"),
        executable_path=Path("bundle/sshd.exe"),
        manifest_path=Path("bundle/manifest.json"),
        runtime_sha256="a" * 64,
        placeholder=True,
        notes=["bundle note"],
    )
    monkeypatch.setattr(cli, "build_moba_server_runtime_bundle_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(cli, "write_moba_server_runtime_bundle", lambda _plan: bundle)
    bundle_args = _ns(
        out=Path("bundle"),
        service="ssh",
        runtime="sshd",
        source=None,
        system="windows",
        release_target="windows-x64",
        executable_name="sshd.exe",
        allow_placeholder=True,
        json=True,
    )
    assert cli.cmd_servers_bundle_runtime(bundle_args) == 0
    bundle_args.json = False
    assert cli.cmd_servers_bundle_runtime(bundle_args) == 0
    bundle.placeholder = False
    bundle.runtime_status.service_coverage["ssh"] = False
    assert cli.cmd_servers_bundle_runtime(bundle_args) == 1

    monkeypatch.setattr(cli, "build_moba_server_config_plan", lambda *_args, **_kwargs: plan)
    config_args = _ns(
        service="ssh",
        host="127.0.0.1",
        port=22,
        root=Path("."),
        hardening_profile="strict",
        require_auth=True,
        require_tls=True,
        allow_public_bind=False,
        json=True,
    )
    assert cli.cmd_servers_config_plan(config_args) == 0
    config_args.json = False
    assert cli.cmd_servers_config_plan(config_args) == 0
    plan.auth_required = False
    assert cli.cmd_servers_config_plan(config_args) == 0

    record = _Record(state="running", pid=42, state_path=Path("server.json"))
    monkeypatch.setattr(cli, "build_moba_server_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(cli, "start_moba_server", lambda *_args, **_kwargs: record)
    start_args = _ns(
        service="ssh",
        host="127.0.0.1",
        port=22,
        root=Path("."),
        allow_public_bind=False,
        dry_run=True,
        json=True,
    )
    assert cli.cmd_servers_start(start_args) == 0
    start_args.json = False
    assert cli.cmd_servers_start(start_args) == 0
    record.pid = None
    assert cli.cmd_servers_start(start_args) == 0
    monkeypatch.setattr(cli, "stop_moba_server", lambda _service: record)
    assert cli.cmd_servers_stop(_ns(service="ssh", json=True)) == 0
    assert cli.cmd_servers_stop(_ns(service="ssh", json=False)) == 0


def test_x11_handlers_cover_runtime_lifecycle_and_smoke(monkeypatch) -> None:
    plan = _Record(command=["xvfb", ":9"], notes=["start note"])
    lifecycle = _Record(state="running", pid=42, state_path=Path("x11.json"), running=True)
    monkeypatch.setattr(cli, "build_moba_x_server_plan", lambda **_kwargs: plan)
    monkeypatch.setattr(cli, "start_moba_x_server", lambda *_args, **_kwargs: lifecycle)
    start_args = _ns(display=":9", dry_run=True, json=True)
    assert cli.cmd_x11_start(start_args) == 0
    start_args.json = False
    assert cli.cmd_x11_start(start_args) == 0
    lifecycle.pid = None
    assert cli.cmd_x11_start(start_args) == 0

    status = _Record(
        display=":9",
        available=True,
        selected_runtime="xvfb",
        display_in_use=True,
        lifecycle=lifecycle,
        candidates=[
            _Record(key="xvfb", available=True, executable="Xvfb"),
            _Record(key="vcxsrv", available=False, executable=""),
        ],
        extensions=[_Record(key="render", status="available", label="Render")],
        notes=["status note"],
    )
    monkeypatch.setattr(cli, "build_moba_x_server_status", lambda **_kwargs: status)
    status_args = _ns(display=":9", json=True)
    assert cli.cmd_x11_status(status_args) == 0
    status_args.json = False
    assert cli.cmd_x11_status(status_args) == 0
    status.available = False
    status.display_in_use = False
    status.lifecycle = None
    assert cli.cmd_x11_status(status_args) == 0

    package_status = _Record(
        system="windows",
        packaged_available=True,
        roots=[Path("x11")],
        candidates=[_Record(key="xvfb", executable="Xvfb")],
        notes=["package note"],
    )
    monkeypatch.setattr(cli, "build_moba_x_server_package_status", lambda **_kwargs: package_status)
    package_args = _ns(root=[Path("x11")], json=True)
    assert cli.cmd_x11_package_status(package_args) == 0
    package_args.json = False
    assert cli.cmd_x11_package_status(package_args) == 0
    package_status.packaged_available = False
    package_status.candidates = []
    assert cli.cmd_x11_package_status(package_args) == 0

    bundle = _Record(
        package_status=_Record(packaged_available=True),
        root=Path("bundle"),
        executable_path=Path("bundle/Xvfb"),
        manifest_path=Path("bundle/manifest.json"),
        runtime_sha256="a" * 64,
        placeholder=True,
        notes=["bundle note"],
    )
    monkeypatch.setattr(cli, "build_moba_x_server_runtime_bundle_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(cli, "write_moba_x_server_runtime_bundle", lambda _plan: bundle)
    bundle_args = _ns(
        out=Path("bundle"),
        runtime="xvfb",
        source=None,
        system="windows",
        release_target="windows-x64",
        executable_name="Xvfb.exe",
        allow_placeholder=True,
        json=True,
    )
    assert cli.cmd_x11_bundle_runtime(bundle_args) == 0
    bundle_args.json = False
    assert cli.cmd_x11_bundle_runtime(bundle_args) == 0
    bundle.placeholder = False
    bundle.package_status.packaged_available = False
    assert cli.cmd_x11_bundle_runtime(bundle_args) == 1

    monkeypatch.setattr(cli, "stop_moba_x_server", lambda: lifecycle)
    assert cli.cmd_x11_stop(_ns(json=True)) == 0
    assert cli.cmd_x11_stop(_ns(json=False)) == 0

    evidence = _Record(
        status="passed",
        display=":9",
        passed=True,
        evidence_path=Path("smoke.json"),
        evidence_sha256="b" * 64,
        notes=["smoke note"],
    )
    monkeypatch.setattr(cli, "run_moba_x_server_smoke", lambda **_kwargs: evidence)
    monkeypatch.setattr(cli, "write_moba_x_server_smoke_evidence", lambda item, _path: item)
    smoke_args = _ns(
        display=":9",
        probe_command="xclock",
        timeout=10,
        out=Path("smoke.json"),
        json=True,
    )
    assert cli.cmd_x11_smoke(smoke_args) == 0
    smoke_args.json = False
    assert cli.cmd_x11_smoke(smoke_args) == 0
    evidence.passed = False
    evidence.evidence_path = None
    evidence.evidence_sha256 = ""
    evidence.notes = None
    smoke_args.out = None
    assert cli.cmd_x11_smoke(smoke_args) == 1


def test_import_team_client_serve_web_and_remaining_helpers(monkeypatch, tmp_path: Path) -> None:
    result = _Record(
        profiles=[Profile(name="edge", protocol="ssh", host="edge")],
        source_format="moba",
        warnings=["import warning"],
    )
    monkeypatch.setattr(cli, "import_profiles_into_store", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(cli, "ProfileStore", lambda: object())
    assert (
        cli.cmd_import(
            _ns(input=Path("profiles.ini"), format="auto", replace=False)
        )
        == 0
    )

    profile_store = object()
    backend = object()
    sentinel = object()
    monkeypatch.setattr(cli, "ProfileStore", lambda: profile_store)
    monkeypatch.setattr(cli, "TeamSyncBackend", lambda root: backend if root == tmp_path else None)
    monkeypatch.setattr(
        cli,
        "TeamSyncClient",
        lambda store, candidate: sentinel if store is profile_store and candidate is backend else None,
    )
    assert cli._team_sync_client(tmp_path) is sentinel

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "serve_web", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setenv("ROW_API_TOKEN", "secret")
    args = _ns(
        api_token=None,
        api_token_env="ROW_API_TOKEN",
        host="127.0.0.1",
        port=8080,
        allow_public_bind=False,
    )
    assert cli.cmd_serve_web(args) == 0
    args.api_token_env = None
    args.api_token = "direct"
    assert cli.cmd_serve_web(args) == 0
    assert [call["api_token"] for call in calls] == ["secret", "direct"]

    monkeypatch.setattr(cli, "write_text_atomic", lambda path, value, private: calls.append({"path": path, "value": value, "private": private}))
    cli._write_secret_file(tmp_path / "secret", "value")
    assert calls[-1]["private"] is True
    assert cli._strip_one_trailing_newline("a\r\n") == "a"
    assert cli._strip_one_trailing_newline("a\n") == "a"
    assert cli._strip_one_trailing_newline("a\r") == "a"
    assert cli._strip_one_trailing_newline("a") == "a"

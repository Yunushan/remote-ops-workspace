from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from remote_ops_workspace.moba_text import (
    MOBA_TEXT_EDITOR_TAB_SCHEMA,
    MOBA_TEXT_RELEASE_EVIDENCE_SCHEMA,
    validate_moba_text_release_evidence,
)
from scripts import check_moba_text_remote_edit_evidence as editor_gate
from scripts import check_release_mobaxterm_parity as published
from scripts import make_mobaxterm_parity_evidence_record as generator


@pytest.fixture
def editor_evidence(tmp_path):
    root = tmp_path / "reviewed" / "moba-text-editor-diff"
    root.mkdir(parents=True)
    package = tmp_path / "row.deb"
    package.write_bytes(b"fixture package")
    source = {
        "repository": "example/row",
        "release_tag": "v1.0.28",
        "head_sha": "a" * 40,
        "workflow_run_url": "https://github.com/example/row/actions/runs/42",
        "run_attempt": 2,
    }
    remote_path = "/home/editor/document copy.txt"
    identity = {
        "release_target": "linux-x86_64", "source": source,
        "release_asset": {"name": package.name, "sha256": hashlib.sha256(package.read_bytes()).hexdigest()},
        "profile": "editor-fixture", "remote_path": remote_path,
    }

    def attach(name, content):
        if not isinstance(content, bytes):
            content = json.dumps(content).encode()
        (root / name).write_bytes(content)
        return {"evidence_file": name, "evidence_sha256": hashlib.sha256(content).hexdigest()}

    opened = attach("opened.txt", b"original\n")
    first = attach("first.txt", b"first revision\n")
    second = attach("second.txt", b"second revision\n")
    staged = attach("staged.txt", b"saved editor bytes\n")
    saved = attach("after.txt", b"saved editor bytes\n")
    readback = attach("readback.txt", b"saved editor bytes\n")
    log = (
        b'Connection from 172.18.0.3 port 50000 on 172.18.0.2 port 2222 rdomain ""\n'
        b"Accepted publickey for editor from 172.18.0.3 port 50000 ssh2: ED25519 SHA256:fixture\n"
        b"Starting session: subsystem 'sftp' for editor from 172.18.0.3 port 50000 id 0\n"
    )
    diagnostics = {
        "status": f"Saved {remote_path} to the remote host", "errors": [],
        "sftp_output": f"sftp> put /tmp/managed.edit '{remote_path}'\n",
    }
    dialogs = [{
        "title": "Remote text diff", "decision": "Ok",
        "detail": f"--- {remote_path}\n+++ {remote_path} (editor)\n@@ -1 +1 @@\n-original\n+saved editor bytes\n",
        "remote_sha256_at_answer": opened["evidence_sha256"],
    }]
    for decision, revision in zip(("No", "Yes", "No", "Yes"), (first, second, second, second), strict=True):
        dialogs.append({
            "title": "Remote file changed", "decision": decision, "default_is_no": True,
            "text": f"{remote_path} changed after it was opened. Overwrite the reviewed remote version?",
            "remote_sha256_at_answer": revision["evidence_sha256"],
        })
    capture = {
        **identity, "schema": editor_gate.CAPTURE_SCHEMA, "status": "passed", "ssh_login": "editor",
        "first_conflict": first, "second_conflict": second, "staged": staged, "server_readback": readback,
        "diagnostics": attach("diagnostics.json", diagnostics), "sshd_log": attach("sshd.log", log),
        "declined_remote_sha256": first["evidence_sha256"],
        "changed_during_approval_remote_sha256": second["evidence_sha256"],
    }
    bundle = {
        **identity, "schema": MOBA_TEXT_RELEASE_EVIDENCE_SCHEMA,
        "editor_tab": {
            "schema": MOBA_TEXT_EDITOR_TAB_SCHEMA, "local_path": "/tmp/managed.edit",
            "syntax": "plain-text", "opened_from_sftp_browser": True, "remote_sha256": opened["evidence_sha256"],
        },
        "open_action": {**opened, "status": "passed", "command": "double-click SFTP browser row"},
        "save_action": {**saved, "status": "passed", "command": "save and read the remote file"},
        "save_review": {"status": "passed", "command": "review the remote overwrite", "conflict_checked": True},
        "connected_session": {
            "real_connected_session": True, "sftp_browser_open": True, "editor_tab_visible": True,
        },
    }

    def write_bundle():
        bundle["connected_session"].update(attach("capture.json", capture))
        bundle["save_review"].update(attach("dialogs.json", dialogs))
        attach("evidence.json", bundle)
        return root / "evidence.json"

    return SimpleNamespace(
        root=root, package=package, source=source, capture=capture, bundle=bundle, dialogs=dialogs,
        attach=attach, write_bundle=write_bundle,
    )


def test_remote_editor_candidate_and_public_audit_verify_capture_and_release_asset(editor_evidence):
    item = editor_evidence
    args = SimpleNamespace(
        article_id="moba-text-editor-diff", release_tag=item.source["release_tag"], release_target="linux-x86_64",
        evidence=item.write_bundle(), assets_dir=item.root,
        release_asset_url=["https://github.com/example/row/releases/download/v1.0.28/row.deb"],
        artifact=[f"row.deb={item.package}"],
    )
    errors, candidate = generator.build_evidence_record(args)
    assert errors == []
    assert candidate["validation_summary"]["summary"]["verified_remote_edit"] is True
    published.verify_article_evidence(candidate, item.root.parent)

    item.package.write_bytes(b"different package")
    errors, _ = generator.build_evidence_record(args)
    assert any("tested release asset must match" in error for error in errors)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("legacy", "JSON"),
        ("source", "tested release source"),
        ("diff", "diff must match"),
        ("approval", "decline and recheck"),
        ("decline", "match distinct snapshots"),
        ("readback", "independent server readback"),
        ("auth", "authenticated SFTP session"),
        ("upload", "successful SFTP upload"),
    ],
)
def test_remote_editor_rejects_hashed_but_incomplete_or_inconsistent_capture(editor_evidence, case, expected):
    item = editor_evidence
    if case == "legacy":
        path = item.write_bundle()
        item.bundle["connected_session"].update(item.attach("passed.txt", b"Connected and saved successfully\n"))
        item.attach("evidence.json", item.bundle)
        assert validate_moba_text_release_evidence(path).passed
    else:
        if case == "source":
            item.capture["source"] = {**item.source, "run_attempt": 3}
        if case == "diff":
            item.dialogs[0]["detail"] = "unrelated diff"
        if case == "approval":
            item.dialogs[3] = item.dialogs[4]
        if case == "decline":
            item.capture["declined_remote_sha256"] = item.capture["changed_during_approval_remote_sha256"]
        if case == "readback":
            item.capture["server_readback"] = item.attach("wrong.txt", b"unrelated server bytes\n")
        if case == "auth":
            item.capture["sshd_log"] = item.attach("unauth.log", b"Connection closed by 172.18.0.3 port 50000\n")
        if case == "upload":
            item.capture["diagnostics"] = item.attach("wrong.json", {
                "status": f"Saved {item.bundle['remote_path']} to the remote host", "errors": [],
                "sftp_output": "sftp> put /tmp/managed.edit /home/editor/unrelated.txt\n",
            })
        path = item.write_bundle()
    result = editor_gate.validate_remote_editor_release_evidence(path)
    assert not result.passed
    assert any(expected in error for error in result.errors)

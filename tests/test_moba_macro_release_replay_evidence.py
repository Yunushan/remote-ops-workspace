from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace.moba_macros import MobaMacroEvent, MobaMacroRecording
from scripts import check_moba_macro_live_evidence as macro_gate
from scripts import check_release_mobaxterm_parity as published
from scripts import make_mobaxterm_parity_evidence_record as generator


@pytest.fixture
def release_evidence(tmp_path):
    root = tmp_path / "reviewed" / "macro-recorder"
    root.mkdir(parents=True)
    package = tmp_path / "row.deb"
    package.write_bytes(b"fixture release bytes")
    source = {
        "repository": "example/row",
        "release_tag": "v1.0.28",
        "head_sha": "a" * 40,
        "workflow_run_url": "https://github.com/example/row/actions/runs/42",
        "run_attempt": 1,
    }
    package_ref = {"name": package.name, "sha256": hashlib.sha256(package.read_bytes()).hexdigest()}

    def attach(name, content):
        if isinstance(content, (dict, list)):
            content = json.dumps(content)
        raw = content.encode()
        (root / name).write_bytes(raw)
        return {"file": name, "sha256": hashlib.sha256(raw).hexdigest()}

    def action(reference, **flags):
        return {
            "status": "passed",
            "command": "Qt terminal capture",
            "evidence_file": reference["file"],
            "evidence_sha256": reference["sha256"],
            **flags,
        }

    recording = MobaMacroRecording(
        name="test-macro",
        source="pyqt-terminal-pane",
        events=[
            MobaMacroEvent(1, "a", False, 0),
            MobaMacroEvent(2, "b", False, 400),
            MobaMacroEvent(3, "", True, 300),
        ],
    ).to_dict()
    cases = {}
    for name, before, after in (
        ("decline", 3, 3),
        ("complete", 3, 6),
        ("cancel", 6, 7),
        ("reconnect", 7, 0),
    ):
        cases[name] = {
            "text": "Replay test-macro in SSH fixture?",
            "default_is_cancel": True,
            "decision": "Cancel" if name == "decline" else "Yes",
            "before": before,
            "after": after,
            "quiet_ms": 900,
        }
    review = {
        "schema": macro_gate.REVIEW_SCHEMA,
        "input_sha256": recording["input_sha256"],
        "profiles": {"lab": cases},
    }
    rows = [
        {"pid": 100, "index": index, "hex": f"{byte:02x}", "monotonic_ns": elapsed * 1_000_000}
        for index, (byte, elapsed) in enumerate(
            zip(b"ab\nab\na", [1000, 1400, 1700, 3000, 3400, 3700, 5000], strict=True), 1
        )
    ]
    auth = "".join(
        f"Connection from 172.18.0.2 port {port} on 172.18.0.3 port 2222\n"
        f"Accepted publickey for probe from 172.18.0.2 port {port} ssh2: ED25519 SHA256:fixture\n"
        f"Starting session: command on pts/0 for probe from 172.18.0.2 port {port} id 0\n"
        for port in (50001, 50002)
    )
    receipt = {
        "schema": macro_gate.SSH_REPLAY_SCHEMA,
        "profile": "lab",
        "source": source,
        "release_asset": package_ref,
        "input_sha256": recording["input_sha256"],
        "receiver_pid": 100,
        "replacement_receiver_pid": 102,
        "destination": "SSH fixture",
        "ssh_user": "probe",
        "enter_byte": "0a",
        "replacement_transcript": attach(
            "replacement.txt", "ROW_MACRO_READY_102 172.18.0.2 50002 172.18.0.3 2222\n"
        ),
        "ssh_log": attach("sshd.log", auth),
    }

    def attach_bytes():
        receipt["server_bytes"] = attach(
            "receiver.jsonl", "\n".join(json.dumps(row) for row in rows) + "\n"
        )
        transcript = (
            "ROW_MACRO_READY_100 172.18.0.2 50001 172.18.0.3 2222\n"
            "[macro recording started]\n[macro recording saved: test-macro]\n"
            "[macro replay queued: 3 event(s)]\n[macro replay cancelled]\n"
        ) + "".join(
            f"ROW_INPUT_{row['index']}_{row['hex']}_{row['monotonic_ns']}\n" for row in rows
        )
        receipt["terminal_transcript"] = attach("transcript.txt", transcript)

    attach_bytes()

    def bundle():
        data = {
            "schema": "row.moba-macro.live-replay-evidence.v1",
            "release_target": "linux-x86_64",
            "source": source,
            "release_asset": package_ref,
            "macro": {k: recording[k] for k in ("name", "event_count", "input_sha256")},
            "capture_session": action(
                attach("recording.json", recording),
                gui_record_button=True,
                gui_stop_button=True,
                gui_cancel_button=True,
                per_event_timing_captured=True,
            ),
            "replay_review": action(
                attach("review.json", review),
                confirmation_prompt=True,
                cancel_prompt_verified=True,
                conflict_checked=True,
            ),
            "replay_sessions": [
                action(
                    attach("replay.json", receipt),
                    profile="lab",
                    real_connected_session=True,
                    live_terminal_pane=True,
                    per_keystroke_timing_replay=True,
                )
            ],
        }
        attach("evidence.json", data)
        return root / "evidence.json"

    return SimpleNamespace(
        root=root,
        package=package,
        source=source,
        bundle=bundle,
        attach=attach,
        attach_bytes=attach_bytes,
        rows=rows,
        receipt=receipt,
        cases=cases,
    )


def test_macro_candidate_and_public_audit_recheck_recorded_bytes_and_release_identity(
    release_evidence,
):
    item = release_evidence
    source = item.source
    args = SimpleNamespace(
        article_id="macro-recorder",
        release_tag=source["release_tag"],
        release_target="linux-x86_64",
        evidence=item.bundle(),
        assets_dir=item.root,
        release_asset_url=[
            f"https://github.com/{source['repository']}/releases/download/{source['release_tag']}/{item.package.name}"
        ],
        artifact=[f"{item.package.name}={item.package}"],
    )
    errors, candidate = generator.build_evidence_record(args)
    assert errors == []
    assert candidate["validation_summary"]["summary"]["verified_macro_replays"] == 1
    published.verify_article_evidence(candidate, item.root.parent)
    item.package.write_bytes(b"different release artifact")
    errors, _ = generator.build_evidence_record(args)
    assert any("tested release asset must match" in error for error in errors)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing-source", "requires source"),
        ("plain-proof", "macro recording must be structured JSON"),
        ("package-drift", "must bind the profile"),
        ("workflow-drift", "must bind the profile"),
        ("bad-timing", "timing differs"),
        ("input-drift", "bytes differ"),
        ("partial-cancel", "nonempty prefix"),
        ("decline-sent", "leave the observed byte count unchanged"),
        ("reconnected-sent", "quiet replacement"),
        ("local-only", "remote PTY connections"),
        ("unrelated-ssh-log", "remote PTY connections"),
        ("client-server-drift", "receiver bytes disagree"),
    ],
)
def test_macro_release_rejects_hash_bound_but_incomplete_or_inconsistent_receipts(
    release_evidence, mutation, message
):
    item = release_evidence
    if mutation == "package-drift":
        item.receipt["release_asset"] = {"name": "other.deb", "sha256": "b" * 64}
    if mutation == "workflow-drift":
        item.receipt["source"] = {**item.source, "run_attempt": 2}
    if mutation == "bad-timing":
        item.rows[4]["monotonic_ns"] -= 300_000_000
        item.attach_bytes()
    if mutation == "input-drift":
        item.rows[4]["hex"] = "63"
        item.attach_bytes()
    if mutation == "partial-cancel":
        item.cases["cancel"]["after"] = 6
    if mutation == "decline-sent":
        item.cases["decline"]["after"] = 4
    if mutation == "reconnected-sent":
        item.receipt["replacement_transcript"] = item.attach(
            "active.txt",
            "ROW_MACRO_READY_102 172.18.0.2 50002 172.18.0.3 2222\nROW_INPUT_1_61_123\n",
        )
    if mutation == "local-only":
        item.receipt["ssh_log"] = item.attach("local.log", "ssh connected\n")
    if mutation == "unrelated-ssh-log":
        altered = (item.root / "sshd.log").read_text().replace("50002", "50003")
        item.receipt["ssh_log"] = item.attach("other-sshd.log", altered)
    if mutation == "client-server-drift":
        altered = (
            (item.root / "transcript.txt").read_text().replace("ROW_INPUT_1_61", "ROW_INPUT_1_62")
        )
        item.receipt["terminal_transcript"] = item.attach("transcript.txt", altered)
    path: Path = item.bundle()
    if mutation == "missing-source":
        data = json.loads(path.read_bytes())
        del data["source"]
        item.attach(path.name, data)
    if mutation == "plain-proof":
        data = json.loads(path.read_bytes())
        attachment = item.attach("plain.txt", "Macro capture passed\n")
        data["capture_session"].update(
            evidence_file=attachment["file"], evidence_sha256=attachment["sha256"]
        )
        item.attach(path.name, data)
    result = macro_gate.validate_macro_release_replay_evidence(path)
    assert not result.passed and any(message in error for error in result.errors)

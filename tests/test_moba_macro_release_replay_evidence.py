from __future__ import annotations

import hashlib
import json
from copy import deepcopy
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
        f"Accepted publickey for {user} from 172.18.0.2 port {port} ssh2: ED25519 SHA256:fixture\n"
        f"Starting session: command on pts/0 for {user} from 172.18.0.2 port {port} id 0\n"
        for port, user in ((50001, "probe"), (50002, "probe"), (50003, "probe"), (50004, "other"))
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

    selected_rows = [
        dict(row, pid=103, monotonic_ns=row["monotonic_ns"] + 9_000_000_000) for row in rows[:3]
    ]
    selected_ready = (
        "ROW_MACRO_READY_103 172.18.0.2 50003 172.18.0.3 2222\n[macro replay queued: 3 event(s)]\n"
    )
    selected_txt = selected_ready + "".join(
        f"ROW_INPUT_{r['index']}_{r['hex']}_{r['monotonic_ns']}\n" for r in selected_rows
    )
    selected = {
        "profile": "lab",
        "destination": "Selected SSH",
        "ssh_user": "probe",
        "receiver_pid": 103,
        "terminal_transcript": attach("selected.txt", selected_txt),
        "server_bytes": attach(
            "selected.jsonl", "".join(json.dumps(row) + "\n" for row in selected_rows)
        ),
    }
    inactive = {
        "profile": "standby",
        "destination": "Inactive SSH",
        "ssh_user": "other",
        "receiver_pid": 104,
        "terminal_transcript": attach(
            "inactive.txt", "ROW_MACRO_READY_104 172.18.0.2 50004 172.18.0.3 2222\n"
        ),
        "server_bytes": attach("inactive.jsonl", ""),
    }
    store = {"version": 1, "macros": [recording]}
    controls = {
        "schema": macro_gate.WORKSPACE_CONTROLS_SCHEMA,
        "macro_name": recording["name"],
        "input_sha256": recording["input_sha256"],
        "capture_app_pid": 20,
        "replay_app_pid": 21,
        "capture_route": {
            "preset": "mobaxterm",
            "menu": "Macros",
            "record": "Record new macro",
            "stop": "Stop recording",
            "stop_object": "mobaStopRecording",
            "prompt": "Please enter a name for this macro",
            "accepted_name": recording["name"],
            "focused_output": "terminalOutput",
        },
        "replay_route": {
            "preset": "mobaxterm",
            "menu": "Macros",
            "saved_section": "Saved macros",
            "selected_entry": recording["name"],
            "active_profile": "lab",
            "active_destination": "Selected SSH",
        },
        "store_before_exit": attach("before.json", store),
        "store_after_restart": attach("after.json", store),
        "selected": selected,
        "inactive": inactive,
        "ssh_log": receipt["ssh_log"],
        "reviews": {
            key: {
                "text": "Replay test-macro in Selected SSH?",
                "default_is_cancel": True,
                "decision": decision,
                "before": 0,
                "after": end,
                "inactive_before": 0,
                "inactive_after": 0,
            }
            for key, decision, end in (("decline", "Cancel", 0), ("complete", "Yes", 3))
        },
    }
    controls["reviews"]["decline"]["quiet_ms"] = 900
    receipt["workspace_controls"] = attach("controls.json", controls)

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
        controls=controls,
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
    assert candidate["validation_summary"]["summary"]["verified_named_macro_replays"] == 1
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


@pytest.mark.parametrize(
    ("tag", "required"), [("v1.0.27", False), ("v1.0.28", True), ("v1.1.0", True)]
)
def test_historical_macro_evidence_retains_its_original_summary(release_evidence, tag, required):
    item = release_evidence
    item.source["release_tag"] = tag
    del item.receipt["workspace_controls"]
    result = macro_gate.validate_macro_release_replay_evidence(item.bundle())
    assert result.passed is (not required)
    assert "verified_named_macro_replays" not in result.summary
    if required:
        assert any("named macro controls" in error for error in result.errors)
    else:
        assert result.summary["verified_macro_replays"] == 1


@pytest.mark.parametrize("tag", ["v1.0.27", "v1.0.28"])
def test_named_replay_counts_independent_profile_observations(release_evidence, tag):
    item = release_evidence
    item.source["release_tag"] = tag
    path = item.bundle()
    bundle = json.loads(path.read_bytes())
    session = deepcopy(bundle["replay_sessions"][0])
    receipt = deepcopy(item.receipt)
    receipt["profile"] = session["profile"] = "another"
    # Both profiles have a complete legacy capture and different original observations.
    journal = (item.root / "receiver.jsonl").read_text()
    transcript = (item.root / "transcript.txt").read_text()
    for row in item.rows:
        at = str(row["monotonic_ns"])
        alternate = str(row["monotonic_ns"] + 15_000_000_000)
        journal = journal.replace(at, alternate)
        transcript = transcript.replace(at, alternate)
    receipt["server_bytes"] = item.attach("another.jsonl", journal)
    receipt["terminal_transcript"] = item.attach("another.txt", transcript)
    if tag == "v1.0.27":
        del receipt["workspace_controls"]
    else:
        controls = deepcopy(item.controls)
        controls["selected"]["profile"] = controls["replay_route"]["active_profile"] = "another"
        journal = (item.root / "selected.jsonl").read_text().replace(": ", ":")
        controls["selected"]["server_bytes"] = item.attach("another-selected.jsonl", journal)
        receipt["workspace_controls"] = item.attach("another-controls.json", controls)
    replay = item.attach("another-replay.json", receipt)
    session.update(evidence_file=replay["file"], evidence_sha256=replay["sha256"])
    bundle["replay_sessions"].append(session)
    review = json.loads((item.root / "review.json").read_bytes())
    review["profiles"]["another"] = item.cases
    ref = item.attach("review.json", review)
    bundle["replay_review"].update(evidence_file=ref["file"], evidence_sha256=ref["sha256"])
    item.attach(path.name, bundle)
    result = macro_gate.validate_macro_release_replay_evidence(path)
    if tag == "v1.0.27":
        assert result.passed, result.errors
        assert result.summary["verified_macro_replays"] == 2
        assert "verified_named_macro_replays" not in result.summary
    else:
        assert not result.passed
        assert any("separate receiver capture" in error for error in result.errors)


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("replay_app_pid",), 20, "separate GUI processes"),
        (("capture_route", "stop_object"), "terminalStop", "Stop and accepted name"),
        (("capture_route", "focused_output"), "fileList", "focused terminal"),
        (("replay_route", "selected_entry"), "Other", "saved menu entry"),
        (("replay_route", "active_profile"), "standby", "clicked tab"),
        (("replay_route", "active_destination"), "Inactive SSH", "clicked tab"),
        (("reviews", "decline", "default_is_cancel"), False, "default-Cancel"),
        (("reviews", "decline", "quiet_ms"), 10, "receiver windows"),
        (("reviews", "decline", "after"), 1, "receiver windows"),
        (("reviews", "complete", "text"), "Replay test-macro in Inactive SSH?", "destination"),
        (("reviews", "complete", "inactive_after"), 1, "receiver windows"),
        (("reviews", "complete", "after"), True, "receiver windows"),
        (("inactive", "receiver_pid"), 103, "distinct SSH receiver processes"),
        (("inactive", "receiver_pid"), 100, "distinct SSH receiver processes"),
        (("inactive", "ssh_user"), "probe", "distinct inactive SSH peer"),
        (("inactive", "ssh_user"), "unrelated", "authenticated remote PTY"),
        (("selected", "profile"), "unrelated", "selected profile"),
    ],
)
def test_named_macro_evidence_rejects_misbound_controls(release_evidence, path, value, reason):
    item = release_evidence
    field = item.controls
    for key in path[:-1]:
        field = field[key]
    field[path[-1]] = value
    item.receipt["workspace_controls"] = item.attach("controls.json", item.controls)
    result = macro_gate.validate_macro_release_replay_evidence(item.bundle())
    assert not result.passed and any(reason in error for error in result.errors)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("unchanged-path", "separate macro store snapshots"),
        ("post-store-drift", "identical workspace bytes"),
        ("saved-delay", "every recorded event and delay"),
        ("second-ready", "own SSH receiver and connection"),
        ("reused-socket", "distinct public-key-authenticated"),
        ("wrong-log", "same authenticated SSH log"),
        ("receiver-only-byte", "independent receiver bytes disagree"),
        ("malformed-extra-marker", "independent receiver bytes disagree"),
        ("wrong-queue", "selected terminal must queue"),
        ("inactive-queue", "selected terminal must queue"),
        ("retimed-delivery", "receiver timing differs"),
        ("inactive-journal", "inactive SSH receiver must remain quiet"),
        ("inactive-transcript", "inactive SSH receiver must remain quiet"),
    ],
)
def test_named_macro_evidence_checks_independent_attachments(release_evidence, mutation, reason):
    item = release_evidence
    controls = item.controls
    if mutation == "unchanged-path":
        controls["store_after_restart"] = controls["store_before_exit"]
    elif mutation in {"post-store-drift", "saved-delay"}:
        store = json.loads((item.root / "before.json").read_bytes())
        store["macros"][0]["events"][1]["delay_ms"] += 2
        controls["store_after_restart"] = item.attach("after.json", store)
        if mutation == "saved-delay":
            controls["store_before_exit"] = item.attach("before.json", store)
    elif mutation in {"second-ready", "reused-socket", "inactive-transcript", "inactive-queue"}:
        text = (item.root / "inactive.txt").read_text()
        if mutation == "second-ready":
            text += text
        elif mutation == "reused-socket":
            text = text.replace("50004", "50002")
        elif mutation == "inactive-queue":
            text += "[macro replay queued: 3 event(s)]\n"
        else:
            text += "ROW_INPUT_1_61_100\n"
        controls["inactive"]["terminal_transcript"] = item.attach("inactive.txt", text)
    elif mutation == "wrong-log":
        controls["ssh_log"] = item.attach("substituted.log", "different server")
    elif mutation == "inactive-journal":
        controls["inactive"]["server_bytes"] = item.attach("inactive.jsonl", '{"index":1}\n')
    elif mutation in {"malformed-extra-marker", "wrong-queue"}:
        text = (item.root / "selected.txt").read_text()
        if mutation == "wrong-queue":
            text = text.replace("3 event(s)", "2 event(s)")
        else:
            text += "ROW_INPUT_4_incomplete\n"
        controls["selected"]["terminal_transcript"] = item.attach("selected.txt", text)
    else:
        selected = controls["selected"]
        rows = [
            json.loads(line) for line in (item.root / "selected.jsonl").read_text().splitlines()
        ]
        rows[1]["monotonic_ns"] -= 300_000_000
        selected["server_bytes"] = item.attach(
            "selected.jsonl", "".join(json.dumps(r) + "\n" for r in rows)
        )
        if mutation == "retimed-delivery":
            transcript = (
                (item.root / "selected.txt").read_text().replace("10400000000", "10100000000")
            )
            selected["terminal_transcript"] = item.attach("selected.txt", transcript)
    item.receipt["workspace_controls"] = item.attach("controls.json", controls)
    result = macro_gate.validate_macro_release_replay_evidence(item.bundle())
    assert not result.passed and any(reason in error for error in result.errors)

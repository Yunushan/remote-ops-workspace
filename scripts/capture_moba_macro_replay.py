"""Capture timed macro recording, replay, and cancellation from the release wheel."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.qt_release_capture import (  # noqa: E402
    FIXTURE,
    HOST,
    MACRO_USER,
    PORT,
    TARGET,
    require_fixture,
    run_capture,
    sha256,
    write_json,
)


def remote_journal(user: str, name: str) -> bytes:
    return subprocess.run(
        ["/usr/bin/ssh", "-T", "-oBatchMode=yes", "-oStrictHostKeyChecking=yes", "-oIdentitiesOnly=yes",
         f"-oUserKnownHostsFile={FIXTURE / 'known_hosts'}", "-i", str(FIXTURE / "identity"),
         "-p", str(PORT), f"{user}@{HOST}", "/bin/cat", f"/home/{user}/{name}"],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=8, check=True,
    ).stdout


def quiet(result, pane, duration, *, inactive=None) -> None:
    from PyQt6.QtTest import QTest

    from scripts.macro_release_workspace import count

    started = time.monotonic_ns()
    QTest.qWait(duration + 150)
    result.update(quiet_ms=(time.monotonic_ns() - started) // 1_000_000, after=count(pane))
    if inactive is not None:
        result["inactive_after"] = count(inactive)


def record_in_workspace(root: Path, raw: Path) -> None:
    from PyQt6.QtWidgets import QMessageBox

    from remote_ops_workspace.moba_macros import MobaMacroStore
    from scripts.macro_release_workspace import (
        MACRO_NAME,
        PROFILE,
        MacroWorkspace,
        count,
        receiver,
        wait_for,
    )

    workspace = MacroWorkspace()
    try:
        store = MobaMacroStore()
        if store.path.exists() or workspace.window.store.load():
            raise ValueError("macro capture requires a fresh workspace")
        workspace.save_profiles()
        pane, _ = workspace.open_receiver(PROFILE)
        original = receiver(pane)
        route = workspace.record(pane)
        recording = store.get(MACRO_NAME)
        if recording.input_text != "ab\n" or pane.macro_last_recording != recording:
            raise ValueError("the named workspace recording differs from the terminal keystrokes")
        (root / "store-before-exit.json").write_bytes(store.path.read_bytes())
        duration = sum(event.delay_ms for event in recording.events)
        decline, _ = workspace.review(pane, QMessageBox.StandardButton.Cancel)
        quiet(decline, pane, duration)
        complete, _ = workspace.review(pane, QMessageBox.StandardButton.Yes)
        wait_for(lambda: not pane.macro_replay_active and count(pane) == 6, "completed timed SSH replay")
        complete["after"] = count(pane)
        cancel, _ = workspace.review(pane, QMessageBox.StandardButton.Yes)
        wait_for(lambda: count(pane) == 7, "first byte before cancellation")
        workspace.menu_action("Cancel replay")
        quiet(cancel, pane, duration)
        (root / "original.txt").write_text(pane.output.toPlainText(), encoding="utf-8")

        reconnect, _ = workspace.review(
            pane, QMessageBox.StandardButton.Yes, before_answer=lambda: pane.request_stop(restart=True),
        )
        if "session changed during review" not in pane.output.toPlainText():
            raise ValueError("the reconnect did not invalidate the named replay review")
        wait_for(lambda: receiver(pane) not in (0, original), "replacement SSH receiver")
        quiet(reconnect, pane, duration)
        (root / "replacement.txt").write_text(pane.output.toPlainText(), encoding="utf-8")
        write_json(raw / "capture-workspace.json", {
            "app_pid": os.getpid(), "route": route,
            "reviews": {"decline": decline, "complete": complete, "cancel": cancel, "reconnect": reconnect},
            "connection": {"receiver_pid": original, "replacement_receiver_pid": receiver(pane),
                           "destination": pane.plan.title, "ssh_user": pane.profile.username},
        })
    finally:
        workspace.close()


def capture_reopened(root: Path, first: dict, recording) -> dict:
    from PyQt6.QtWidgets import QMessageBox

    from remote_ops_workspace.moba_macros import MobaMacroStore
    from scripts.check_moba_macro_live_evidence import WORKSPACE_CONTROLS_SCHEMA
    from scripts.macro_release_workspace import (
        INACTIVE_PROFILE,
        MACRO_NAME,
        PROFILE,
        MacroWorkspace,
        count,
        receiver,
        wait_for,
    )

    workspace = MacroWorkspace()
    try:
        store = MobaMacroStore()
        (root / "store-after-restart.json").write_bytes(store.path.read_bytes())
        if (root / "store-before-exit.json").read_bytes() != store.path.read_bytes() or store.get(MACRO_NAME) != recording:
            raise ValueError("the saved workspace macro changed between application launches")
        selected, index = workspace.open_receiver(PROFILE, reopened=True)
        inactive, _ = workspace.open_receiver(INACTIVE_PROFILE, reopened=True)
        if workspace.window.active_terminal_pane() is not inactive or selected.macro_last_recording is not None:
            raise ValueError("reopened replay requires two fresh destinations with the other tab initially active")
        workspace.select_tab(index, selected)
        active = workspace.window.active_terminal_pane()
        duration = sum(event.delay_ms for event in recording.events)
        decline, _ = workspace.review(selected, QMessageBox.StandardButton.Cancel, inactive=inactive)
        quiet(decline, selected, duration, inactive=inactive)
        complete, route = workspace.review(selected, QMessageBox.StandardButton.Yes, inactive=inactive)
        wait_for(lambda: not selected.macro_replay_active and count(selected) == 3, "saved replay on selected SSH pane")
        complete.update(after=count(selected), inactive_after=count(inactive))
        route.update(preset=workspace.window.current_design_id(), active_profile=active.profile.name,
                     active_destination=active.plan.title)
        destinations = {}
        for role, pane in (("selected", selected), ("inactive", inactive)):
            transcript, journal = root / f"reopened-{role}.txt", root / f"reopened-{role}.jsonl"
            transcript.write_text(pane.output.toPlainText(), encoding="utf-8")
            journal.write_bytes(remote_journal(pane.profile.username, "reopened-input.jsonl"))
            destinations[role] = {
                "profile": pane.profile.name, "destination": pane.plan.title, "ssh_user": pane.profile.username,
                "receiver_pid": receiver(pane), "terminal_transcript": attachment(transcript),
                "server_bytes": attachment(journal),
            }
        return {
            "schema": WORKSPACE_CONTROLS_SCHEMA, "macro_name": recording.name,
            "input_sha256": recording.to_dict()["input_sha256"], "capture_app_pid": first["app_pid"],
            "replay_app_pid": os.getpid(), "capture_route": first["route"], "replay_route": route,
            "store_before_exit": attachment(root / "store-before-exit.json"),
            "store_after_restart": attachment(root / "store-after-restart.json"),
            "reviews": {"decline": decline, "complete": complete}, **destinations,
        }
    finally:
        workspace.close()


def attachment(path: Path) -> dict[str, str]:
    return {"file": path.name, "sha256": sha256(path.read_bytes())}


def capture(root: Path, raw: Path, identity: dict) -> None:
    from remote_ops_workspace.moba_macros import (
        MobaMacroStore,
        build_macro_live_evidence_bundle_plan,
        write_macro_live_evidence_bundle,
    )
    from remote_ops_workspace.storage import ProfileStore
    from scripts.check_moba_macro_live_evidence import (
        REVIEW_SCHEMA,
        SSH_REPLAY_SCHEMA,
        capture_recording,
        validate_macro_release_replay_evidence,
        verify_replay_capture,
        verify_workspace_controls,
    )
    from scripts.macro_release_workspace import MACRO_NAME, PROFILE

    # The capture process must terminate before the second workspace starts.
    subprocess.run([sys.executable, "-I", __file__, "--record-workspace", str(root), str(raw)], timeout=75, check=True)
    first = json.loads((raw / "capture-workspace.json").read_bytes())
    profile = ProfileStore().get(PROFILE)
    recording = MobaMacroStore().get(MACRO_NAME)
    reviews, connection = first["reviews"], first["connection"]
    workspace_receipt = capture_reopened(root, first, recording)
    wire = remote_journal(MACRO_USER, "observed-input.jsonl")
    original_input = [json.loads(line)["hex"] for line in wire.splitlines()[:3]]
    if len(original_input) != 3 or original_input[:2] != ["61", "62"] or original_input[2] not in {"0a", "0d"}:
        raise ValueError("SSH receiver did not observe the typed fixture and a terminal Enter byte")
    (root / "server-input.jsonl").write_bytes(wire)
    (root / "sshd.log").write_bytes((FIXTURE / "sshd.log").read_bytes())
    workspace_receipt["ssh_log"] = attachment(root / "sshd.log")
    write_json(root / "workspace-controls.json", workspace_receipt)
    data = recording.to_dict()
    write_json(raw / "recording.json", data)
    write_json(raw / "review.json", {
        "schema": REVIEW_SCHEMA, "input_sha256": data["input_sha256"], "profiles": {profile.name: reviews},
    })
    receipt = {
        "schema": SSH_REPLAY_SCHEMA, "profile": profile.name, "input_sha256": data["input_sha256"],
        "terminal_transcript": attachment(root / "original.txt"),
        "replacement_transcript": attachment(root / "replacement.txt"),
        "server_bytes": attachment(root / "server-input.jsonl"), "ssh_log": attachment(root / "sshd.log"),
        "enter_byte": original_input[2], "workspace_controls": attachment(root / "workspace-controls.json"),
        **connection, **identity,
    }
    write_json(raw / "replay.json", receipt)
    plan = build_macro_live_evidence_bundle_plan(
        recording, [profile], out_dir=root, capture_evidence=raw / "recording.json",
        review_evidence=raw / "review.json", replay_evidence={profile.name: raw / "replay.json"},
        release_target=TARGET, connected_profiles=[profile.name],
        capture_command="Moba Macros menu, recording ribbon Stop and named save dialog",
        review_command="Saved Macros menu entry, active SSH destination review and cancellation",
        replay_commands={profile.name: "Named Moba macro reopened and confirmed on the selected SSH tab"},
        gui_record_button=True, gui_stop_button=True, gui_cancel_button=True,
        per_event_timing_captured=True, confirmation_prompt=True, cancel_prompt_verified=True,
        conflict_checked=True, real_connected_session=True, live_terminal_pane=True, per_keystroke_timing_replay=True,
    )
    bundle = write_macro_live_evidence_bundle(plan)
    if not bundle.validation.passed:
        raise ValueError(f"macro evidence bundle failed: {bundle.validation.errors}")
    path = Path(bundle.evidence_path).rename(root / "evidence.json")
    manifest = {**json.loads(path.read_bytes()), **identity}
    write_json(path, manifest)
    if "source" in identity:
        result = validate_macro_release_replay_evidence(path, assets_dir=root)
        if not result.passed:
            raise ValueError(f"release macro evidence failed: {result.errors}")
    else:
        observed = capture_recording(raw / "recording.json", manifest["macro"])
        verify_replay_capture(root, receipt, observed, reviews)
        verify_workspace_controls(root, receipt, observed)
        write_json(root / "local-qualification.json", {
            **identity, "verified_macro_replays": 1, "verified_named_macro_replays": 1, "production_acceptance": False,
        })


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--record-workspace":
        require_fixture()
        if not os.environ.get("ROW_HOME"):
            raise ValueError("the recording subprocess requires an isolated workspace")
        record_in_workspace(Path(sys.argv[2]), Path(sys.argv[3]))
        return 0
    run_capture(capture, __doc__ or "")
    print("Verified timed macro replay and cancellation, and the reopened named macro on the selected SSH receiver")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

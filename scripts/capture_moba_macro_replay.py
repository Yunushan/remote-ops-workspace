"""Capture timed macro recording, replay, and cancellation from the release wheel."""

from __future__ import annotations

import json
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
    run_capture,
    sha256,
    write_json,
)

TITLE = "Macro release capture receiver"
RECEIVER = "/usr/local/lib/row-macro-receiver.py"


def ssh_command(*remote: str, tty: bool = False) -> list[str]:
    return [
        "/usr/bin/ssh", *(["-tt"] if tty else ["-T"]), "-oBatchMode=yes",
        "-oStrictHostKeyChecking=yes", "-oIdentitiesOnly=yes",
        f"-oUserKnownHostsFile={FIXTURE / 'known_hosts'}", "-i", str(FIXTURE / "identity"),
        "-p", str(PORT), f"{MACRO_USER}@{HOST}", *remote,
    ]


def capture_terminal(root: Path):
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from remote_ops_workspace.gui_terminal import TerminalPane
    from remote_ops_workspace.models import Profile
    from remote_ops_workspace.terminal import TerminalPanePlan
    from scripts.check_moba_macro_live_evidence import TRANSCRIPT_BYTE, TRANSCRIPT_READY

    profile = Profile(name="macro-fixture", protocol="ssh", host=HOST, port=PORT, username=MACRO_USER,
                      identity_file=str(FIXTURE / "identity"))
    app = QApplication([])
    command = ssh_command("/usr/local/bin/python", "-u", RECEIVER, tty=True)
    plan = TerminalPanePlan(title=TITLE, command=command, source=f"profile:{profile.name}")
    pane = TerminalPane(plan, profile=profile, autostart=False)
    pane.resize(960, 570)
    pane.show()
    pane.start()

    def transcript() -> str:
        return pane.output.toPlainText()

    def receiver() -> int:
        rows = TRANSCRIPT_READY.findall(transcript())
        return int(rows[0][0]) if len(rows) == 1 else 0

    def count() -> int:
        return len(TRANSCRIPT_BYTE.findall(transcript()))

    def wait_for(predicate) -> None:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise TimeoutError(f"macro terminal observation timed out:\n{transcript()[-3000:]}")

    def click(button) -> None:
        if not button.isVisible() or not button.isEnabled():
            raise ValueError(f"macro control is unavailable: {button.text()}")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    def review(button, before_answer=None) -> dict:
        result = {"before": count()}
        errors = []
        timer = QTimer()

        def answer() -> None:
            dialog = app.activeModalWidget()
            if not isinstance(dialog, QMessageBox):
                return
            timer.stop()
            try:
                result.update(
                    text=dialog.text(), decision=button.name,
                    default_is_cancel=dialog.defaultButton() is dialog.button(QMessageBox.StandardButton.Cancel),
                )
                if before_answer is not None:
                    before_answer()
                dialog.button(button).click()
            except Exception as exc:
                errors.append(str(exc))
                dialog.reject()

        timer.timeout.connect(answer)
        timer.start(20)
        try:
            click(pane.macro_replay_button)
        finally:
            timer.stop()
        if errors or result.get("default_is_cancel") is not True:
            raise ValueError(f"macro replay did not present its default-Cancel review: {errors}")
        return result

    def quiet(result, duration: int) -> None:
        started = time.monotonic_ns()
        QTest.qWait(duration + 150)
        result.update(quiet_ms=(time.monotonic_ns() - started) // 1_000_000, after=count())

    try:
        wait_for(receiver)
        original = receiver()
        click(pane.macro_record_button)
        QTest.keyClicks(pane.output, "a")
        QTest.qWait(420)
        QTest.keyClicks(pane.output, "b")
        QTest.qWait(330)
        QTest.keyClick(pane.output, Qt.Key.Key_Return)
        wait_for(lambda: count() == 3)
        click(pane.macro_stop_button)
        recording = pane.macro_last_recording
        if recording is None or recording.to_dict()["input_text"] != "ab\n":
            raise ValueError("the Qt macro recorder did not retain exactly the typed fixture")
        duration = sum(event.delay_ms for event in recording.events)

        decline = review(QMessageBox.StandardButton.Cancel)
        quiet(decline, duration)
        complete = review(QMessageBox.StandardButton.Yes)
        wait_for(lambda: not pane.macro_replay_active and count() == 6)
        complete["after"] = count()
        cancel = review(QMessageBox.StandardButton.Yes)
        wait_for(lambda: count() == 7)
        click(pane.macro_cancel_button)
        quiet(cancel, duration)
        (root / "original.txt").write_text(transcript(), encoding="utf-8")

        reconnect = review(QMessageBox.StandardButton.Yes, lambda: pane.request_stop(restart=True))
        if "session changed during review" not in transcript():
            raise ValueError("the replay review did not reject its stale pane after a reconnect")
        wait_for(lambda: receiver() not in (0, original))
        quiet(reconnect, duration)
        (root / "replacement.txt").write_text(transcript(), encoding="utf-8")
        return profile, recording, {"decline": decline, "complete": complete, "cancel": cancel, "reconnect": reconnect}, {
            "receiver_pid": original, "replacement_receiver_pid": receiver(),
            "destination": TITLE, "ssh_user": MACRO_USER,
        }
    finally:
        pane.stop()
        pane.close()
        app.processEvents()


def attachment(path: Path) -> dict[str, str]:
    return {"file": path.name, "sha256": sha256(path.read_bytes())}


def capture(root: Path, raw: Path, identity: dict) -> None:
    from remote_ops_workspace.moba_macros import (
        build_macro_live_evidence_bundle_plan,
        write_macro_live_evidence_bundle,
    )
    from scripts.check_moba_macro_live_evidence import (
        REVIEW_SCHEMA,
        SSH_REPLAY_SCHEMA,
        capture_recording,
        validate_macro_release_replay_evidence,
        verify_replay_capture,
    )

    profile, recording, reviews, connection = capture_terminal(root)
    wire = subprocess.run(
        ssh_command("/bin/cat", f"/home/{MACRO_USER}/observed-input.jsonl"),
        stdin=subprocess.DEVNULL, capture_output=True, timeout=8, check=True,
    ).stdout
    original_input = [json.loads(line)["hex"] for line in wire.splitlines()[:3]]
    if len(original_input) != 3 or original_input[:2] != ["61", "62"] or original_input[2] not in {"0a", "0d"}:
        raise ValueError("SSH receiver did not observe the typed fixture and a terminal Enter byte")
    (root / "server-input.jsonl").write_bytes(wire)
    (root / "sshd.log").write_bytes((FIXTURE / "sshd.log").read_bytes())
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
        "enter_byte": original_input[2], **connection, **identity,
    }
    write_json(raw / "replay.json", receipt)
    plan = build_macro_live_evidence_bundle_plan(
        recording, [profile], out_dir=root, capture_evidence=raw / "recording.json",
        review_evidence=raw / "review.json", replay_evidence={profile.name: raw / "replay.json"},
        release_target=TARGET, connected_profiles=[profile.name],
        capture_command="Qt terminal Record and Stop controls",
        review_command="Qt terminal Replay confirmation and live session identity check",
        replay_commands={profile.name: "Qt terminal Replay and Cancel controls"},
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
        write_json(root / "local-qualification.json", {
            **identity, "verified_macro_replays": 1, "production_acceptance": False,
        })


def main() -> int:
    run_capture(capture, __doc__ or "")
    print("Verified timed macro replay, cancellation and a quiet replacement SSH receiver")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

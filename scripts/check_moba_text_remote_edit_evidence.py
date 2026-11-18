from __future__ import annotations

import argparse
import difflib
import hashlib
import ipaddress
import json
import re
import shlex
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for location in (ROOT, SRC):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.moba_text import (  # noqa: E402
    MobaTextReleaseEvidenceValidation,
    validate_moba_text_release_evidence,
)
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import secure_regular_file  # noqa: E402

CAPTURE_SCHEMA = "row.moba-text.connected-edit-capture.v1"
MAX_CAPTURE_BYTES = 1024 * 1024
CONNECT = re.compile(r"^Connection from (\S+) port (\d+) on (\S+) port (\d+)\b", re.MULTILINE)
AUTH = re.compile(r"^Accepted \S+ for (\S+) from (\S+) port (\d+)\b", re.MULTILINE)
SFTP = re.compile(r"^Starting session: subsystem 'sftp' for (\S+) from (\S+) port (\d+)\b", re.MULTILINE)


def capture_bytes(path: Path, label: str) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_CAPTURE_BYTES + 1)
    if not data or len(data) > MAX_CAPTURE_BYTES:
        raise ValueError(f"{label} must contain between 1 byte and 1 MiB")
    return data


def capture_object(data: Any, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def parse_capture_json(content: bytes, label: str) -> Any:
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc


def read_attachment(root: Path, pointer: Any, label: str) -> tuple[Path, bytes]:
    attachment = capture_object(pointer, label)
    path, error = secure_regular_file(root, attachment.get("evidence_file"), label)
    if path is None:
        raise ValueError(error)
    content = capture_bytes(path, label)
    if hashlib.sha256(content).hexdigest() != attachment.get("evidence_sha256"):
        raise ValueError(f"{label} SHA-256 differs from the evidence")
    return path, content


def verify_sftp_transport(sshd_log: str, login: str) -> None:
    authenticated = set(AUTH.findall(sshd_log))
    subsystems = set(SFTP.findall(sshd_log))
    for client, port, server, _ in CONNECT.findall(sshd_log):
        key = (login, client, port)
        if key in authenticated and key in subsystems:
            if ipaddress.ip_address(client) != ipaddress.ip_address(server):
                return
    raise ValueError("SSH server log must show an authenticated SFTP session for the captured login")


def verify_editor_dialogs(
    dialogs: Any, remote_path: str, opened: bytes, staged: bytes, digests: dict[str, str],
) -> None:
    if not isinstance(dialogs, list) or len(dialogs) != 5:
        raise ValueError("editor review must capture its diff and four overwrite decisions")
    diff = capture_object(dialogs[0], "editor diff")
    expected_diff = "".join(difflib.unified_diff(
        opened.decode("utf-8").splitlines(keepends=True),
        staged.decode("utf-8").splitlines(keepends=True),
        fromfile=remote_path, tofile=f"{remote_path} (editor)", n=3,
    ))
    if (
        diff.get("title") != "Remote text diff" or diff.get("decision") != "Ok"
        or diff.get("remote_sha256_at_answer") != digests["opened"]
        or diff.get("detail") != expected_diff
    ):
        raise ValueError("editor diff must match the downloaded and staged text bytes")
    for row, decision, snapshot in zip(
        dialogs[1:], ("No", "Yes", "No", "Yes"), ("first", "second", "second", "second"), strict=True,
    ):
        dialog = capture_object(row, "overwrite decision")
        if (
            dialog.get("title") != "Remote file changed" or dialog.get("decision") != decision
            or dialog.get("default_is_no") is not True
            or not str(dialog.get("text", "")).startswith(f"{remote_path} changed after it was opened.")
            or dialog.get("remote_sha256_at_answer") != digests[snapshot]
        ):
            raise ValueError("overwrite review must decline and recheck the captured remote revisions")


def verify_editor_capture(
    root: Path, bundle: dict[str, Any], capture: dict[str, Any],
    actions: dict[str, tuple[Path, bytes]],
) -> dict[str, Any]:
    profile, remote_path = bundle.get("profile"), bundle.get("remote_path")
    if (
        capture.get("schema") != CAPTURE_SCHEMA
        or not isinstance(profile, str) or not profile or capture.get("profile") != profile
        or not isinstance(remote_path, str) or not PurePosixPath(remote_path).is_absolute()
        or capture.get("remote_path") != remote_path or capture.get("status") != "passed"
    ):
        raise ValueError("connected editor capture must bind the profile and absolute remote file")

    opened_path, opened = actions["open_action"]
    final_path, final = actions["save_action"]
    attachments = {
        name: read_attachment(root, capture.get(name), name)
        for name in ("first_conflict", "second_conflict", "staged", "server_readback", "diagnostics", "sshd_log")
    }
    staged_path, staged = attachments["staged"]
    readback_path, readback = attachments["server_readback"]
    text_files = (opened_path, final_path, staged_path, readback_path,
                  attachments["first_conflict"][0], attachments["second_conflict"][0])
    if len({path.resolve() for path in text_files}) != len(text_files):
        raise ValueError("editor and server snapshots must be separate attachments")
    if staged != final or staged != readback:
        raise ValueError("saved remote bytes and independent server readback must match the staged editor")

    digests = {
        "opened": hashlib.sha256(opened).hexdigest(),
        "first": hashlib.sha256(attachments["first_conflict"][1]).hexdigest(),
        "second": hashlib.sha256(attachments["second_conflict"][1]).hexdigest(),
        "saved": hashlib.sha256(final).hexdigest(),
    }
    editor_tab = capture_object(bundle.get("editor_tab"), "editor tab")
    if (
        len(set(digests.values())) != len(digests)
        or digests["opened"] != editor_tab.get("remote_sha256")
        or digests["first"] != capture.get("declined_remote_sha256")
        or digests["second"] != capture.get("changed_during_approval_remote_sha256")
    ):
        raise ValueError("downloaded, declined, rereviewed and uploaded bytes must match distinct snapshots")

    dialogs = parse_capture_json(actions["save_review"][1], "editor review")
    verify_editor_dialogs(dialogs, remote_path, opened, staged, digests)
    diagnostics_data = parse_capture_json(attachments["diagnostics"][1], "editor diagnostics")
    diagnostics = capture_object(diagnostics_data, "editor diagnostics")
    if (
        diagnostics.get("status") != f"Saved {remote_path} to the remote host"
        or diagnostics.get("errors") != []
        or not any(
            line.startswith("sftp> put ") and shlex.split(line)[-1] == remote_path
            for line in str(diagnostics.get("sftp_output", "")).splitlines()
        )
    ):
        raise ValueError("editor diagnostics must show a successful SFTP upload to the captured remote path")
    login = capture.get("ssh_login")
    if not isinstance(login, str) or not login:
        raise ValueError("connected editor capture must identify the SSH login")
    verify_sftp_transport(attachments["sshd_log"][1].decode("utf-8"), login)
    return {"verified_remote_edit": True, "opened_sha256": digests["opened"], "saved_sha256": digests["saved"]}


def validate_remote_editor_release_evidence(
    evidence_path: Path, *, assets_dir: Path | None = None,
) -> MobaTextReleaseEvidenceValidation:
    root = assets_dir if assets_dir is not None else evidence_path.parent
    try:
        relative = evidence_path.absolute().relative_to(root.absolute()).as_posix()
        evidence, error = secure_regular_file(root, relative, "remote-edit release evidence")
        if evidence is None:
            raise ValueError(error)
        raw_bundle = parse_capture_json(capture_bytes(evidence, "release evidence"), "release evidence")
        bundle = capture_object(raw_bundle, "release evidence")
        identity = capture_release_identity(bundle, "remote-edit release evidence")
        actions = {
            stage: read_attachment(root, bundle.get(stage), stage)
            for stage in ("open_action", "save_review", "save_action", "connected_session")
        }
        raw_capture = parse_capture_json(actions["connected_session"][1], "connected editor capture")
        capture = capture_object(raw_capture, "connected editor capture")
        if capture_release_identity(capture, "connected editor capture") != identity or (
            capture.get("release_target") != bundle.get("release_target")
        ):
            raise ValueError("connected editor capture must match the tested release source, target and asset")
        verified = verify_editor_capture(root, bundle, capture, actions)
        result = validate_moba_text_release_evidence(evidence, assets_dir=root)
        result.summary.update(identity, **verified)
        return result
    except (OSError, ValueError) as exc:
        return MobaTextReleaseEvidenceValidation(str(evidence_path), str(root), False, [str(exc)], [], {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify MobaTextEditor-style connected remote-edit release evidence.")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = validate_remote_editor_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba text remote-edit evidence passed")
    else:
        for error in result.errors:
            print(f"moba text remote-edit evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

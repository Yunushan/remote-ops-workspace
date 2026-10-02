"""Prove offline encrypted recovery and compatibility with a released wheel.

Only a sanitized report is retained. Synthetic homes, ciphertext, random secrets
and passphrases live in a temporary directory which is removed on exit. This is
source and released-wheel state evidence; it is not native-installer evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "configs" / "workspace_recovery_fixture.json"
REPORT_SCHEMA = "row.workspace-recovery-smoke.v1"
EXPECTED_WHEEL_SHA256 = "9fe56c3b4f09365cdc7a21249a41b9b60d5944f2ce0f596f9b45443184db585e"
EXPECTED_WHEEL_SIZE = 542385
EXPECTED_WHEEL_NAME = "remote_ops_workspace-1.0.24-py3-none-any.whl"
EXPECTED_WHEEL_URL = "https://github.com/Yunushan/remote-ops-workspace/releases/download/v1.0.24/" + EXPECTED_WHEEL_NAME
CHECK_NAMES = (
    "verified_released_wheel", "previous_loaders_seeded_state", "current_loaders_read_previous_state",
    "vault_mutation_upgraded_format", "current_restore_exact_state", "previous_restore_exact_state",
    "released_previous_loaders_decrypted_rollback", "unresolved_profiles_and_group_defaults_preserved",
    "layout_splitters_preserved", "opaque_plugin_state_preserved", "post_snapshot_state_absent",
    "original_home_unchanged_by_restore", "wrong_passphrase_rejected", "tampered_ciphertext_rejected",
    "in_place_restore_rejected",
)

# A fresh interpreter with -I prevents the caller's checkout/PYTHONPATH from
# replacing released code. The chosen wheel or source path is the only explicit
# import override. Secrets travel through stdin, never process arguments.
_WORKER = r'''
import hashlib, json, os, sys
from pathlib import Path
runtime, home = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(runtime))
os.environ["ROW_HOME"] = str(home)
import remote_ops_workspace as package
assert str(package.__file__).startswith(str(runtime) + os.sep), "wrong runtime origin"
from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore
from remote_ops_workspace.layouts import Layout, LayoutStore
from remote_ops_workspace.snippets import Snippet, SnippetStore
from remote_ops_workspace.moba_macros import MobaMacroRecording, MobaMacroStore
from remote_ops_workspace.moba_ssh_browser import (
    MobaSshBrowserPreferences, load_moba_ssh_browser_preferences,
    save_moba_ssh_browser_preferences,
)
from remote_ops_workspace.vault import LocalVault
payload = json.load(sys.stdin)
fixture, mode = payload["fixture"], payload["mode"]
vault = LocalVault(home / "vault.json")
profiles = ProfileStore(home / "profiles.json")
layouts = LayoutStore(home / "layouts.json")
snippets = SnippetStore(home / "snippets.json")
macros = MobaMacroStore(home / "moba-macros.json")
browser_path = home / "moba-ssh-browser-state.json"
if mode == "seed":
    home.mkdir()
    profiles.init(with_examples=False)
    profiles.save(Profile.from_dict(row) for row in fixture["profiles"])
    for group, defaults in fixture["group_defaults"].items():
        profiles.set_group_defaults(group, defaults, replace=True)
    layouts.save(Layout.from_dict(row) for row in fixture["layouts"])
    snippets.save(Snippet.from_dict(row) for row in fixture["snippets"])
    macros.save(MobaMacroRecording.from_dict(row) for row in fixture["macros"])
    save_moba_ssh_browser_preferences(MobaSshBrowserPreferences.from_dict(fixture["browser_preferences"]), browser_path)
    vault.init(payload["vault_passphrase"])
    vault.set("recovery-secret", payload["secret"], payload["vault_passphrase"])
    for name, content in fixture["opaque_files"].items():
        target = home / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
    for name in fixture["empty_directories"]:
        (home / name).mkdir(parents=True)
elif mode == "mutate":
    profiles.add(Profile(name="current-only", protocol="ssh", host="current.invalid", group="recovery"))
    profiles.set_group_defaults("recovery", {"username": "upgraded-user", "options": {"x11": "false", "compression": "true"}}, replace=True)
    changed = layouts.load()
    changed[0].splitter_sizes = [[901, 99], [111, 889]]
    layouts.save(changed)
    snippets.add(Snippet(name="current-only", command="printf upgraded"))
    changed_macros = macros.load()
    changed_macros[0].events[0].text = "printf upgraded"
    macros.save(changed_macros)
    preferences = load_moba_ssh_browser_preferences(browser_path)
    preferences.location = "hidden"
    preferences.column_widths["name"] = 499
    save_moba_ssh_browser_preferences(preferences, browser_path)
    vault.set("current-only", payload["new_secret"], payload["vault_passphrase"])
    (home / "plugins/unrecognized/state.json").write_bytes(b"current-plugin-state")
    (home / "current-only.dat").write_bytes(b"current-only-state")
elif mode != "inspect":
    raise ValueError("unknown worker mode")
unresolved = [row.to_dict() for row in profiles.load(resolve=False)]
resolved = [row.to_dict() for row in profiles.load()]
defaults = profiles.group_defaults()
layout_rows = [row.to_dict() for row in layouts.load()]
snippet_rows = [row.to_dict() for row in snippets.load()]
macro_rows = [row.to_dict() for row in macros.load()]
browser = load_moba_ssh_browser_preferences(browser_path).to_dict()
secret_rows = {name: vault.get(name, payload["vault_passphrase"]) for name in vault.list()}
assert secret_rows["recovery-secret"] == payload["secret"], "secret changed"
if mode == "seed":
    assert unresolved[0]["username"] is None and unresolved[0]["port"] is None
    assert resolved[0]["username"] == fixture["group_defaults"]["recovery"]["username"]
    assert resolved[0]["options"] == {**fixture["group_defaults"]["recovery"]["options"], **fixture["profiles"][0]["options"]}
    assert defaults == fixture["group_defaults"]
    assert layout_rows[0]["splitter_sizes"] == fixture["layouts"][0]["splitter_sizes"]
    assert snippet_rows == [Snippet.from_dict(row).to_dict() for row in fixture["snippets"]]
    assert macro_rows == [MobaMacroRecording.from_dict(row).to_dict() for row in fixture["macros"]]
    assert {key: value for key, value in browser.items() if key != "updated_at"} == {key: value for key, value in fixture["browser_preferences"].items() if key != "updated_at"}
state = {"unresolved": unresolved, "resolved": resolved, "defaults": defaults,
         "layouts": layout_rows, "snippets": snippet_rows, "macros": macro_rows,
         "browser": browser, "secrets": secret_rows}
canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
print(json.dumps({"version": package.__version__, "semantic_sha256": hashlib.sha256(canonical).hexdigest(),
    "vault_version": vault.status().version,
    "counts": {"profiles": len(unresolved), "group_defaults": len(defaults), "layouts": len(layout_rows),
               "snippets": len(snippet_rows), "macros": len(macro_rows), "vault_items": len(secret_rows)}}))
'''


def load_fixture(path: Path = FIXTURE) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    previous = fixture["previous_release"]
    if fixture.get("schema_version") != 1 or previous != {
        "version": "1.0.24", "filename": EXPECTED_WHEEL_NAME, "url": EXPECTED_WHEEL_URL,
        "size": EXPECTED_WHEEL_SIZE, "sha256": EXPECTED_WHEEL_SHA256, "vault_version": 2,
    }:
        raise ValueError("previous released-wheel identity changed")
    return fixture


def verify_previous_wheel(path: Path) -> None:
    if path.name != EXPECTED_WHEEL_NAME or path.stat().st_size != EXPECTED_WHEEL_SIZE:
        raise ValueError("previous released-wheel name or size mismatch")
    if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED_WHEEL_SHA256:
        raise ValueError("previous released-wheel SHA256 mismatch")


def download_previous_wheel(path: Path) -> None:
    """Use system TLS trust and a bounded read; verify before writing or loading."""
    import truststore

    truststore.inject_into_ssl()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(EXPECTED_WHEEL_URL, timeout=30) as response:
                data = response.read(EXPECTED_WHEEL_SIZE + 1)
            break
        except urllib.error.HTTPError as exc:
            if attempt == 2 or exc.code not in {429, 500, 502, 503, 504}:
                raise
            time.sleep(attempt + 1)
    if len(data) != EXPECTED_WHEEL_SIZE or hashlib.sha256(data).hexdigest() != EXPECTED_WHEEL_SHA256:
        raise ValueError("downloaded previous wheel does not match its pinned release digest")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    verify_previous_wheel(path)


def _worker(runtime: Path, home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-I", "-c", _WORKER, str(runtime.resolve()), str(home.resolve())],
        input=json.dumps(payload), capture_output=True, text=True,
        cwd=home.parent, timeout=180, check=False,
    )
    # Do not forward tracebacks, stdin, store rows, or decrypted vault values.
    if result.returncode:
        raise RuntimeError("isolated state worker failed")
    summary = json.loads(result.stdout)
    if set(summary) != {"version", "semantic_sha256", "vault_version", "counts"}:
        raise ValueError("isolated state worker returned unexpected evidence")
    return summary


def _tree_summary(home: Path) -> dict[str, Any]:
    directories, rows = [], []
    for path in sorted(home.rglob("*")):
        name = path.relative_to(home).as_posix()
        if path.is_dir():
            directories.append(name)
        elif not re.fullmatch(r"\..+\.lock", path.name):
            data = path.read_bytes()
            rows.append([name, len(data), hashlib.sha256(data).hexdigest()])
    digest = hashlib.sha256(json.dumps([directories, rows], separators=(",", ":")).encode()).hexdigest()
    return {"sha256": digest, "file_count": len(rows), "directory_count": len(directories), "total_bytes": sum(row[1] for row in rows)}


def _assert_same(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    if expected != actual:
        raise AssertionError("restored full-state evidence differs")


def run_drill(previous_wheel: Path) -> dict[str, Any]:
    verify_previous_wheel(previous_wheel)
    fixture = load_fixture()
    sys.path.insert(0, str(ROOT / "src"))
    from remote_ops_workspace.workspace_backup import (
        WorkspaceBackupError,
        create_workspace_backup,
        restore_workspace_backup,
    )

    work_root = ROOT / ".tmp"
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="row-workspace-recovery-", dir=work_root) as temporary:
        root = Path(temporary)
        home = root / "original"
        payload = {"fixture": fixture, "vault_passphrase": secrets.token_urlsafe(32),
                   "secret": secrets.token_urlsafe(48), "new_secret": secrets.token_urlsafe(48)}
        backup_passphrase = secrets.token_urlsafe(32)
        old = _worker(previous_wheel, home, {**payload, "mode": "seed"})
        if old["version"] != "1.0.24" or old["vault_version"] != 2:
            raise AssertionError("previous wheel did not create the released vault format")
        old_tree = _tree_summary(home)
        old_backup = root / "previous.rowbackup"
        create_workspace_backup(home, old_backup, backup_passphrase, offline_confirmed=True)
        current = ROOT / "src"
        loaded = _worker(current, home, {**payload, "mode": "inspect"})
        _assert_same(old["counts"], loaded["counts"])
        if loaded["semantic_sha256"] != old["semantic_sha256"] or loaded["vault_version"] != 2:
            raise AssertionError("current loaders changed previous state before mutation")
        _assert_same(old_tree, _tree_summary(home))
        upgraded = _worker(current, home, {**payload, "mode": "mutate"})
        if upgraded["vault_version"] != 3 or upgraded["semantic_sha256"] == old["semantic_sha256"]:
            raise AssertionError("current mutation did not upgrade the legacy vault")
        upgraded_tree = _tree_summary(home)
        current_backup = root / "current.rowbackup"
        create_workspace_backup(home, current_backup, backup_passphrase, offline_confirmed=True)

        # Corrupt every known store and opaque state, then add files after the
        # snapshot. Exact inventory equality proves none leak into restoration.
        for name in ("profiles.json", "vault.json", "layouts.json", "snippets.json", "moba-macros.json", "moba-ssh-browser-state.json", "plugins/unrecognized/state.json"):
            (home / name).write_bytes(b"corrupted-after-snapshot")
        (home / "after-snapshot-only.dat").write_bytes(b"not-in-either-snapshot")
        corrupted_tree = _tree_summary(home)
        if corrupted_tree == upgraded_tree:
            raise AssertionError("corruption fixture did not change state")

        restored = root / "restored-current"
        restore_workspace_backup(current_backup, restored, backup_passphrase, current_home=home, offline_confirmed=True)
        _assert_same(upgraded_tree, _tree_summary(restored))
        _assert_same(upgraded, _worker(current, restored, {**payload, "mode": "inspect"}))
        _assert_same(corrupted_tree, _tree_summary(home))
        for bad_backup, bad_passphrase, target in (
            (current_backup, secrets.token_urlsafe(32), root / "wrong-passphrase"),
            (current_backup, backup_passphrase, home),
        ):
            try:
                restore_workspace_backup(bad_backup, target, bad_passphrase, current_home=home, offline_confirmed=True)
            except WorkspaceBackupError:
                if target != home and target.exists():
                    raise AssertionError("failed restore created a destination") from None
            else:
                raise AssertionError("unsafe recovery unexpectedly succeeded")
        tampered = root / "tampered.rowbackup"
        envelope = json.loads(current_backup.read_text(encoding="utf-8"))
        token = envelope["token"]
        envelope["token"] = token[:30] + ("A" if token[30] != "A" else "B") + token[31:]
        tampered.write_text(json.dumps(envelope), encoding="utf-8")
        try:
            restore_workspace_backup(tampered, root / "tampered-restore", backup_passphrase, current_home=home, offline_confirmed=True)
        except WorkspaceBackupError:
            if (root / "tampered-restore").exists():
                raise AssertionError("tampered restore created a destination") from None
        else:
            raise AssertionError("tampered ciphertext unexpectedly restored")

        rollback = root / "restored-previous"
        restore_workspace_backup(old_backup, rollback, backup_passphrase, current_home=home, offline_confirmed=True)
        _assert_same(old_tree, _tree_summary(rollback))
        _assert_same(old, _worker(previous_wheel, rollback, {**payload, "mode": "inspect"}))
        rollback_current = _worker(current, rollback, {**payload, "mode": "inspect"})
        if rollback_current["semantic_sha256"] != old["semantic_sha256"]:
            raise AssertionError("current loaders could not read rolled-back state")
        _assert_same(corrupted_tree, _tree_summary(home))
        report = {
            "schema": REPORT_SCHEMA, "status": "passed",
            "scope": "source-and-released-wheel-state-compatibility",
            "previous_version": old["version"], "current_version": upgraded["version"],
            "previous_wheel_sha256": EXPECTED_WHEEL_SHA256,
            "previous_vault_version": old["vault_version"], "upgraded_vault_version": upgraded["vault_version"],
            "previous": {"counts": old["counts"], "tree": old_tree, "semantic_sha256": old["semantic_sha256"]},
            "current": {"counts": upgraded["counts"], "tree": upgraded_tree, "semantic_sha256": upgraded["semantic_sha256"]},
            "checks": dict.fromkeys(CHECK_NAMES, True),
        }
        validate_report(report)
        return report


def validate_report(report: dict[str, Any]) -> None:
    """Allow only the evidence contract, so upload paths cannot reveal payloads."""
    expected_keys = {"schema", "status", "scope", "previous_version", "current_version", "previous_wheel_sha256", "previous_vault_version", "upgraded_vault_version", "previous", "current", "checks"}
    if set(report) != expected_keys or report["schema"] != REPORT_SCHEMA or report["status"] != "passed" or report["scope"] != "source-and-released-wheel-state-compatibility":
        raise ValueError("invalid recovery evidence contract")
    if report["previous_version"] != "1.0.24" or not re.fullmatch(r"\d+\.\d+\.\d+", report["current_version"]):
        raise ValueError("invalid recovery evidence versions")
    if report["previous_wheel_sha256"] != EXPECTED_WHEEL_SHA256 or report["previous_vault_version"] != 2 or report["upgraded_vault_version"] != 3:
        raise ValueError("invalid released wheel or vault evidence")
    for stage in ("previous", "current"):
        row = report[stage]
        if set(row) != {"counts", "tree", "semantic_sha256"} or set(row["counts"]) != {"profiles", "group_defaults", "layouts", "snippets", "macros", "vault_items"} or set(row["tree"]) != {"sha256", "file_count", "directory_count", "total_bytes"}:
            raise ValueError("unexpected payload field in recovery evidence")
        if not re.fullmatch(r"[0-9a-f]{64}", row["semantic_sha256"]) or not re.fullmatch(r"[0-9a-f]{64}", row["tree"]["sha256"]):
            raise ValueError("invalid recovery evidence hash")
        counts = [*row["counts"].values(), *(row["tree"][key] for key in ("file_count", "directory_count", "total_bytes"))]
        if any(type(count) is not int or count < 1 for count in counts):
            raise ValueError("invalid recovery evidence counts")
    if set(report["checks"]) != set(CHECK_NAMES) or any(value is not True for value in report["checks"].values()):
        raise ValueError("missing or failed recovery evidence check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--previous-wheel", type=Path, default=ROOT / ".tmp" / EXPECTED_WHEEL_NAME)
    parser.add_argument("--download-previous-wheel", action="store_true")
    args = parser.parse_args(argv)
    try:
        load_fixture()
        if args.download_previous_wheel:
            download_previous_wheel(args.previous_wheel)
        report = run_drill(args.previous_wheel)
    except Exception as exc:
        report = {"schema": REPORT_SCHEMA, "status": "failed", "failure_type": type(exc).__name__}
        result = 1
    else:
        result = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Workspace recovery drill: {report['status']}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

"""Capture the Professional deployment policy across a live desktop and Web workspace."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import secrets
import selectors
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOST = "127.0.0.1"
PORT = 1
ALLOWED = "ssh"
DENIED = "telnet"
OPERATOR_UID = 65534
MACHINE = Path("/etc/remote-ops-workspace/policy.json")
READY = "OPERATOR READY"
APPLY = "MACHINE INSTALLED"
TOKEN_ENV = "ROW_POLICY_QUALIFICATION_TOKEN"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile(name: str, protocol: str) -> dict[str, Any]:
    return {"name": name, "protocol": protocol, "host": HOST, "port": PORT}


def row_command(*arguments: str) -> list[str]:
    return [sys.executable, "-I", "-m", "remote_ops_workspace", *arguments]


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


class Desktop:
    def __init__(self, app: Any, window: Any) -> None:
        self.app = app
        self.window = window

    def action(self, callable_: Callable[[], Any], inspect: Callable[[Any, list], None]) -> list:
        from PyQt6.QtCore import QTimer

        messages: list = []
        failures: list[str] = []

        def observe() -> None:
            modal = self.app.activeModalWidget()
            if modal is not None:
                try:
                    inspect(modal, messages)
                except Exception as error:
                    failures.append(str(error))
                    modal.reject()

        def timeout() -> None:
            modal = self.app.activeModalWidget()
            if modal is not None:
                failures.append("the expected desktop dialog did not finish")
                modal.reject()

        timer = QTimer()
        timer.timeout.connect(observe)
        abort = QTimer()
        abort.setSingleShot(True)
        abort.timeout.connect(timeout)
        timer.start(20)
        abort.start(5000)
        try:
            callable_()
        finally:
            timer.stop()
            abort.stop()
        self.app.processEvents()
        if failures:
            raise ValueError("\n".join(failures))
        return messages

    @staticmethod
    def message_box(modal: Any, messages: list) -> None:
        from PyQt6.QtWidgets import QMessageBox

        if not isinstance(modal, QMessageBox):
            raise ValueError("the desktop did not show a policy message")
        messages.append({"title": modal.windowTitle(), "text": modal.text()})
        modal.accept()

    def edit(self, name: str, protocol: str) -> list:
        attempted = False

        def submit(dialog: Any, messages: list) -> None:
            nonlocal attempted
            if not attempted:
                dialog.fields["name"].setText(name)
                dialog.fields["protocol"].setCurrentText(protocol)
                dialog.fields["host"].setText(HOST)
                dialog.fields["port"].setText(str(PORT))
                attempted = True
                dialog.submit()
            elif dialog.validation_error.isVisible():
                messages.append(dialog.validation_error.text())
                dialog.reject()

        return self.action(self.window.create_profile, submit)

    def launch(self, action: Callable[[], Any], prepare: Callable[[str], None]) -> dict[str, Any]:
        original = self.window.tabs.count()
        prepare(DENIED)
        denied = self.action(action, self.message_box)
        refusal_tabs = self.window.tabs.count()
        prepare(ALLOWED)
        allowed = self.action(action, self.message_box)
        if allowed:
            raise ValueError("the allowed desktop operation unexpectedly displayed a message")
        return {"denied": denied, "tabs_before": original, "tabs_after_denial": refusal_tabs,
                "tabs_after_allowance": self.window.tabs.count()}

    def close(self) -> None:
        from PyQt6.QtWidgets import QMessageBox

        def accept_close(modal: Any, _messages: list) -> None:
            if not isinstance(modal, QMessageBox) or modal.windowTitle() != "Quit Remote Ops Workspace":
                raise ValueError("an unexpected desktop dialog prevented cleanup")
            modal.button(QMessageBox.StandardButton.Yes).click()

        self.action(self.window.close, accept_close)


def web_request(port: int, token: str, method: str, path: str, data: dict | None = None) -> dict[str, Any]:
    connection = http.client.HTTPConnection(HOST, port, timeout=3)
    try:
        connection.request(method, path, body=json.dumps(data) if data is not None else None, headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        })
        reply = connection.getresponse()
        return {"status": reply.status, "body": json.loads(reply.read())}
    finally:
        connection.close()


def await_policy_endpoint(web: subprocess.Popen, status: Callable[[], dict]) -> dict:
    deadline = time.monotonic() + 12
    while web.poll() is None and time.monotonic() < deadline:
        try:
            return status()
        except ConnectionRefusedError:
            time.sleep(0.05)
    raise ValueError("the authenticated local Web process did not open its policy endpoint")


def observe_profile_write(store: Any, surface: str, write: Callable[[str, str], Any]) -> dict[str, Any]:
    original = digest(store.path)
    denied = write(f"{surface}-denied", DENIED)
    refused = digest(store.path)
    name = f"{surface}-allowed"
    allowed = write(name, ALLOWED)
    report = {"denied": denied, "store_before": original, "store_after_denial": refused,
              "store_after_allowance": digest(store.path), "saved_protocol": store.get(name).protocol}
    if surface != "profile-editor":
        report["allowed"] = allowed
    elif allowed:
        raise ValueError("the allowed Profile Editor write displayed a refusal")
    return report


def cli_write(name: str, protocol: str) -> dict[str, Any]:
    command = row_command("profile", "add", "--name", name, "--protocol", protocol, "--host", HOST, "--port", str(PORT))
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=18, check=False)
    return {"exit": result.returncode, "stderr": result.stderr}


def operator(home: Path) -> None:
    from remote_ops_workspace.enterprise_policy import load_enterprise_policy
    from remote_ops_workspace.gui import create_main_window
    from remote_ops_workspace.launcher import build_launch_plan
    from remote_ops_workspace.layouts import Layout, LayoutPane
    from remote_ops_workspace.models import Profile
    from remote_ops_workspace.storage import ProfileStore

    if os.geteuid() != OPERATOR_UID or os.path.lexists(MACHINE):
        raise ValueError("the desktop needs the unprivileged lab account before machine policy installation")
    portable = home / "policy.json"
    portable.write_text('{"schema_version": 1, "locked_settings": []}\n', encoding="utf-8")
    historical = ProfileStore(home / "historical-profiles.json")
    for protocol in (DENIED, ALLOWED):
        historical.add(Profile(**profile(f"historical-{protocol}", protocol)))
    app, window = create_main_window(["professional-policy-qualification"], show=True)
    app.processEvents()
    desktop = Desktop(app, window)
    if not window.isVisible() or window.store.policy_path != portable:
        raise ValueError("the live desktop did not start with its portable policy")
    with socket.socket() as reservation:
        reservation.bind((HOST, 0))
        port = reservation.getsockname()[1]
    token = secrets.token_urlsafe(32)
    web = subprocess.Popen(
        row_command("serve-web", "--host", HOST, "--port", str(port), "--api-token-env", TOKEN_ENV),
        env={**os.environ, TOKEN_ENV: token}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    )

    def status():
        return web_request(port, token, "GET", "/enterprise-policy.json")

    def post(name, protocol):
        return web_request(port, token, "POST", "/api/v1/profiles", profile(name, protocol))

    try:
        initial = await_policy_endpoint(web, status)
        if initial["status"] != 200 or initial["body"].get("locked_settings") != []:
            raise ValueError("the running Web process did not start with its portable policy")
        if post("pre-install", ALLOWED)["status"] != 201:
            raise ValueError("the authenticated Web API did not accept a baseline write")
        gui_before, web_before = os.getpid(), web.pid
        print(READY, flush=True)
        if sys.stdin.readline().strip() != APPLY:
            raise ValueError("the supervisor did not install the test machine policy")

        selected = load_enterprise_policy()
        if not selected.machine_enforced or selected.path != MACHINE:
            raise ValueError("the installed package did not select the protected machine policy")
        original_policy = digest(MACHINE)
        try:
            with MACHINE.open("r+"):
                raise ValueError("the unprivileged account can open the machine policy for writing")
        except PermissionError:
            pass
        with portable.open("r+"):
            pass
        after = status()
        store = window.store
        report = {
            "web": observe_profile_write(store, "web", post),
            "cli": observe_profile_write(store, "cli", cli_write),
            "profile-editor": observe_profile_write(store, "profile-editor", desktop.edit),
        }
        try:
            build_launch_plan(Profile(**profile("launcher-denied", DENIED)))
        except ValueError as error:
            launcher_denial = str(error)
        else:
            raise ValueError("the launcher accepted the locked protocol")
        allowed = Profile(**profile("launcher-allowed", ALLOWED))
        report["launcher"] = {"denied": launcher_denial, "allowed_protocol": allowed.protocol,
                              "allowed_argv": build_launch_plan(allowed).command}

        window.store = historical
        window.refresh_profiles()
        for protocol in (DENIED, ALLOWED):
            name = f"historical-{protocol}"
            window.layout_store.add(Layout(name=name, panes=[LayoutPane(profile=name)]))
            window.layout_select.addItem(name)
        report["gui"] = desktop.launch(window.open_selected_layout, lambda p: window.layout_select.setCurrentText(f"historical-{p}"))
        report["quick-connect"] = desktop.launch(window.run_quick_connect, lambda p: window.quick_connect.setText(f"{p}://{HOST}:{PORT}"))
        if web.poll() is not None or not window.isVisible():
            raise ValueError("a tested workspace process stopped before the capture completed")
        report.update({
            "attempts": {"denied_protocol": DENIED, "allowed_protocol": ALLOWED},
            "public_policy_before": initial, "public_policy": after,
            "machine_policy_write_refused": True, "portable_policy_writable": True,
            "machine_policy_unchanged": digest(MACHINE) == original_policy,
            "machine_policy_sha256": original_policy, "gui_and_web_started_before_machine_install": True,
            "gui_process": {"before": gui_before, "after": os.getpid()},
            "web_process": {"before": web_before, "after": web.pid}, "operator_uid": os.geteuid(),
        })
        print(json.dumps(report), flush=True)
    finally:
        stop(web)
        desktop.close()


def observe_policy(policy: bytes) -> dict[str, Any]:
    if os.path.lexists(MACHINE.parent):
        raise ValueError("the disposable container already has an enterprise policy directory")
    with TemporaryDirectory(prefix="row-policy-operator-") as temporary:
        home = Path(temporary)
        os.chown(home, OPERATOR_UID, OPERATOR_UID)
        env = {"PATH": os.environ.get("PATH", os.defpath), "LC_ALL": "C.UTF-8", "ROW_HOME": str(home),
               "HOME": str(home), "QT_QPA_PLATFORM": "offscreen"}
        with subprocess.Popen(
            [sys.executable, "-I", __file__, "--operator", str(home)],
            user=OPERATOR_UID, group=OPERATOR_UID, extra_groups=[], env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
        ) as child:
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(child.stdout, selectors.EVENT_READ)
                    if not selector.select(45) or child.stdout.readline().strip() != READY:
                        raise ValueError("the unprivileged desktop and Web process did not become ready")
                MACHINE.parent.mkdir(mode=0o755)
                MACHINE.parent.chmod(0o755)
                staged = MACHINE.with_suffix(".new")
                with staged.open("xb") as stream:
                    stream.write(policy)
                staged.chmod(0o644)
                staged.rename(MACHINE)
                output, _ = child.communicate(APPLY + "\n", timeout=65)
                if child.returncode:
                    raise ValueError(f"the unprivileged capture worker failed with exit status {child.returncode}")
                return json.loads(output)
            finally:
                stop(child)


def capture(wheel: Path, bundle: Path, output: Path, *, local: bool) -> Path:
    from scripts.isolated_linux_fixture import require_offline_container
    from scripts.qt_release_capture import verify_wheel, write_json

    require_offline_container()
    if output.exists() or output.is_symlink():
        raise ValueError("policy capture output must be a new directory")
    output = output.absolute()
    tag, asset = verify_wheel(wheel)

    # Import the review helpers after checking which wheel the capture imports.
    from scripts.check_moba_professional_deployment_evidence import (
        POLICY_CAPTURE_SCHEMA,
        decode_object,
        read_small,
        verify_policy_document,
        verify_policy_surfaces,
    )
    from scripts.check_mobaxterm_parity_evidence import capture_release_identity
    from scripts.check_release_license_compliance import secure_regular_file, sha256_file
    from scripts.debian_release_fixture import actions_source

    provenance: dict[str, Any] = {"release_asset": asset}
    if not local:
        provenance["source"] = actions_source(tag)
        capture_release_identity(provenance, "Professional policy capture")
    references = []
    for name in ("manifest.json", "config/policy.json"):
        path, error = secure_regular_file(bundle, name, "customizer bundle")
        if path is None:
            raise ValueError(error)
        references.append(read_small(path, f"customizer {name}"))
    manifest, policy = references
    manifest_data = decode_object(manifest, "customizer manifest")
    if manifest_data.get("project_version") != tag.removeprefix("v"):
        raise ValueError("the customizer bundle and installed wheel have different versions")
    installed_digest = verify_policy_document(manifest_data, policy)
    locked_settings = decode_object(policy, "customizer policy").get("locked_settings")
    if locked_settings != [{"key": "protocol", "value": ALLOWED}]:
        raise ValueError("this qualification fixture requires a customizer bundle with a single SSH protocol lock")
    report = observe_policy(policy)
    with TemporaryDirectory(prefix=".professional-policy-", dir=output.parent) as temporary:
        root = Path(temporary) / "review"
        root.mkdir()
        (root / "bundle-manifest.json").write_bytes(manifest)
        document = root / "policy.json"
        document.write_bytes(policy)
        report.update(provenance, schema=POLICY_CAPTURE_SCHEMA, installed_policy_sha256=installed_digest,
                      policy_document={"evidence_file": document.name, "evidence_sha256": installed_digest})
        capture_path = root / "policy-capture.json"
        write_json(capture_path, report)
        evidence = {
            **provenance,
            "bundle_manifest": {"evidence_file": "bundle-manifest.json", "evidence_sha256": digest(root / "bundle-manifest.json")},
            "policy_locks": {"locked_settings": locked_settings, "evidence_file": capture_path.name,
                             "evidence_sha256": digest(capture_path)},
        }
        evidence["verified_policy_metadata"] = verify_policy_surfaces(root, evidence, report)
        if sha256_file(wheel) != asset["sha256"]:
            raise ValueError("the release wheel changed during the capture")
        write_json(root / "policy-review.json", evidence)
        root.rename(output)
    return output / "policy-review.json"


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--operator":
        operator(Path(sys.argv[2]))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True, help="the exact wheel installed in the fixture")
    parser.add_argument("--bundle", type=Path, required=True, help="the original customizer bundle")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--local", action="store_true", help="rehearse without release provenance")
    args = parser.parse_args()
    try:
        review = capture(args.wheel, args.bundle, args.out, local=args.local)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Professional machine policy capture failed: {error}\n")
    print(f"Verified the Professional policy surfaces in {review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

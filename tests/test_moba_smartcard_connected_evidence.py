import base64
import datetime as dt
import hashlib
import json
import sys
from shutil import copytree
from types import SimpleNamespace

import pytest

from scripts import check_moba_smartcard_evidence as smartcard
from scripts import check_release_mobaxterm_parity as audit
from scripts import make_mobaxterm_parity_evidence_record as generator
from scripts import stage_smartcard_release_evidence as staging

ARTICLE = "ssh-browser-26-4-smartcard"


@pytest.fixture
def capture(tmp_path):
    x509 = pytest.importorskip("cryptography.x509")
    ed25519 = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    key = ed25519.Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "Qualification fixture")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + dt.timedelta(days=1)).sign(key, None))
    der = cert.public_bytes(serialization.Encoding.DER)
    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
    digest = hashlib.sha256(base64.b64decode(public.split()[1])).digest()
    fingerprint = "SHA256:" + base64.b64encode(digest).decode().rstrip("=")

    package = tmp_path / "remote-ops-workspace-linux-x86_64.deb"
    package.write_bytes(b"synthetic test package bytes")
    repository, tag = "example/remote-ops-workspace", "v1.0.2"
    identity = {
        "release_target": "linux-x86_64",
        "source": {"repository": repository, "release_tag": tag, "head_sha": "a" * 40,
                   "workflow_run_url": f"https://github.com/{repository}/actions/runs/12", "run_attempt": 2},
        "release_asset": {"name": package.name, "sha256": hashlib.sha256(package.read_bytes()).hexdigest()},
    }
    root = tmp_path / ARTICLE
    root.mkdir()
    provider, certificate_id = "/usr/lib/Card Middleware/opensc-pkcs11.so", "card-test"
    socket = "/tmp/row-ssh-1000/cm-abcdefghijklmnopqrstuvwx"
    token = "pkcs11:manufacturer=Fixture;serial=123;token=ROW-test-card"
    fixture = f"row-smartcard-{'b' * 32}.txt"
    login, client, host, port = "operator", "192.0.2.12", "192.0.2.20", 2222
    target = f"{login}@{host}"
    profile = {"name": "token", "host": host, "username": login, "port": port, "protocol": "ssh",
               "options": {"smartcard_certificate_id": certificate_id, "smartcard_provider": f"pkcs11:{provider}",
                           "add_smartcard_to_mobagent": "true"}}

    def save(filename, data):
        if isinstance(data, dict):
            data = json.dumps(data).encode()
        (root / filename).write_bytes(data)
        return {"evidence_file": filename, "evidence_sha256": hashlib.sha256(data).hexdigest()}

    probe = f"Token 0:\n\tURL: {token}\n\tLabel: ROW-test-card\n\tType: Hardware token\n".encode()
    management = {"token_url": token, "certificate_der": save("card.der", der),
                  "exported_openssh_public_key": public.decode(), "present_tokens": save("inserted.txt", probe),
                  "removed_tokens": save("removed.txt", b"")}
    log = (f"Connection from {client} port 31223 on {host} port {port} rdomain \"\"\n"
           f"Accepted publickey for {login} from {client} port 31223 ssh2: ED25519 {fingerprint}\n"
           f"Starting session: shell on pts/0 for {login} from {client} port 31223 id 0\n"
           f"Starting session: subsystem 'sftp' for {login} from {client} port 31223 id 1\n").encode()
    browser = {
        **identity, "schema": smartcard.CAPTURE_SCHEMA, "profile": profile["name"], "control_path": socket,
        "terminal_argv": ["ssh", "-p", str(port), "-I", provider, "-o", "ControlMaster=auto",
                          "-o", f"ControlPath={socket}", target],
        "sftp_argv": ["sftp", "-P", str(port), "-o", f'PKCS11Provider="{provider}"', "-o", "ControlMaster=no",
                      "-o", f"ControlPath={socket}", "-o", "BatchMode=yes", target],
        "fixture_name": fixture, "file_rows": ["..", fixture], "sshd_log": save("openssh.log", log),
        "sftp_listing": save("listing.txt", f"-rw------- 1 {login} {login} 16 Nov 18 08:00 {fixture}\n".encode()),
    }
    bundle = {
        **identity, "schema": "row.moba-smartcard.release-evidence.v1",
        "certificate": {"id": certificate_id, "provider": f"pkcs11:{provider}",
                        "fingerprint_sha256": hashlib.sha256(der).hexdigest(), "openssh_public_key": public.decode()},
    }

    def action(name, data, *flags):
        suffix = ".json" if isinstance(data, dict) else ".txt"
        bundle[name] = {**save(f"{name}{suffix}", data), "status": "passed", "command": name,
                        **dict.fromkeys(flags, True)}

    action("management_interface", management, "gui_visible", "add_remove_controls", "openssh_public_key_visible")
    action("ssh_session_selection", profile, "expert_setting_visible", "certificate_selected", "profile_saved")
    action("mobagent", public + b" agent label\n", "global_add_setting", "agent_loaded_certificate")
    action("ssh_browser", browser, "same_parameters_sftp", "multiplex_mode", "real_connected_session", "sftp_browser_open")
    save("evidence.json", bundle)
    return SimpleNamespace(root=root, package=package, identity=identity, bundle=bundle, management=management,
                           profile=profile, browser=browser, save=save, log=log, probe=probe, fingerprint=fingerprint)


def test_smartcard_capture_is_replayed_by_candidate_and_release_audit(capture):
    source = capture.identity["source"]
    name = capture.package.name
    url = f"https://github.com/{source['repository']}/releases/download/{source['release_tag']}/{name}"
    arguments = SimpleNamespace(article_id=ARTICLE, release_tag=source["release_tag"],
                                release_target=capture.identity["release_target"], evidence=capture.root / "evidence.json",
                                assets_dir=capture.root, release_asset_url=[url], artifact=[f"{name}={capture.package}"])

    errors, record = generator.build_evidence_record(arguments)
    assert not errors
    summary = record["validation_summary"]["summary"]
    assert summary["openssh_key_fingerprint"] == capture.fingerprint
    assert summary["verified_hardware_smartcard"] and summary["verified_multiplexed_sftp"]
    audit.verify_article_evidence(record, capture.root.parent)

    capture.package.write_bytes(b"changed package bytes")
    errors, _ = generator.build_evidence_record(arguments)
    assert any("tested release asset must match" in error for error in errors)


def test_workflow_seals_only_the_run_bound_physical_capture(capture, tmp_path, monkeypatch, capsys):
    work = tmp_path / "runner"
    work.mkdir()
    (work / "review").mkdir()
    source = capture.identity["source"]
    monkeypatch.setattr(staging, "require_native_runner", lambda: None)
    monkeypatch.setattr(staging, "verify_wheel", lambda path: (source["release_tag"], capture.identity["release_asset"]))
    monkeypatch.setattr(staging, "actions_source", lambda tag: source)
    monkeypatch.setattr(staging.secrets, "token_hex", lambda length: "b" * (2 * length))
    argv = ["stage", "--wheel", str(capture.package), "--work", str(work)]
    monkeypatch.setattr(sys, "argv", [*argv, "prepare"])
    assert staging.main() == 0
    fixture = capsys.readouterr().out.strip()
    assert json.loads((work / "capture-request.json").read_bytes()) == {**capture.identity, "fixture_name": fixture}

    inventory = generator.evidence_assets_sha256(capture.root)
    capture.save("private-extra.txt", b"deliberately excluded lab file")
    copytree(capture.root, work / "inbox" / "ready")
    monkeypatch.setattr(sys, "argv", [*argv, "collect", "--fixture", fixture])
    assert staging.main() == 0
    assert generator.evidence_assets_sha256(work / "review" / ARTICLE) == inventory


@pytest.mark.parametrize(("failure", "message"), [
    ("attempt", "current workflow attempt"),
    ("asset", "exact release wheel"),
    ("challenge", "challenge issued for this workflow attempt"),
    ("tampered-file", "SHA-256 differs"),
    ("outside-path", "file path is invalid"),
    ("duplicate-path", "unique visible capture path"),
    ("semantic-proof", "SFTP listing must contain"),
])
def test_workflow_refuses_unbound_or_invalid_captures(capture, tmp_path, failure, message):
    identity, fixture = capture.identity, capture.browser["fixture_name"]
    if failure == "attempt":
        identity = {**identity, "source": {**identity["source"], "run_attempt": 3}}
    elif failure == "asset":
        identity = {**identity, "release_asset": {**identity["release_asset"], "sha256": "e" * 64}}
    elif failure == "challenge":
        fixture = "row-smartcard-" + "c" * 32 + ".txt"
    elif failure == "tampered-file":
        capture.save("openssh.log", b"changed while preparing capture")
    else:
        if failure == "outside-path":
            capture.browser["sftp_listing"]["evidence_file"] = "../not-a-capture.txt"
        elif failure == "duplicate-path":
            capture.browser["sftp_listing"] = capture.browser["sshd_log"]
        else:
            capture.browser["sftp_listing"] = capture.save("listing.txt", b"unrelated files\n")
        capture.bundle["ssh_browser"].update(capture.save("ssh_browser.json", capture.browser))
        capture.save("evidence.json", capture.bundle)

    staged = tmp_path / "staged"
    with pytest.raises(ValueError, match=message):
        staging.stage_capture(capture.root, staged, identity, fixture)
    assert not staged.exists()


@pytest.mark.parametrize("agent", ["none", "/tmp/agent.sock"])
def test_saved_card_release_capture_requires_identity_file_and_exclusive_auth(capture, agent):
    from remote_ops_workspace.smartcard_keys import PINNED_SMARTCARD_KEY

    certificate = capture.bundle["certificate"]
    capture.profile["options"].update({PINNED_SMARTCARD_KEY: certificate["openssh_public_key"], "identity_agent": agent})
    capture.bundle["ssh_session_selection"].update(capture.save("ssh_session_selection.json", capture.profile))
    browser = capture.browser
    for name in ("terminal_argv", "sftp_argv"):
        argv = browser[name]
        if agent != "none":
            index = argv.index("-I") if name == "terminal_argv" else 3
            argv[index:index + 2] = ["-o", "PKCS11Provider=none"]
        argv[-1:-1] = ["-o", 'IdentityFile="/tmp/chosen.pub"', "-o", "IdentitiesOnly=yes", "-o", f"IdentityAgent={agent}"]
    capture.bundle["ssh_browser"].update(capture.save("ssh_browser.json", browser))
    capture.save("evidence.json", capture.bundle)
    result = smartcard.validate_smartcard_connected_release_evidence(capture.root / "evidence.json")
    assert result.passed, result.errors

    browser["sftp_argv"] = [arg for arg in browser["sftp_argv"] if arg != 'IdentityFile="/tmp/chosen.pub"']
    capture.bundle["ssh_browser"].update(capture.save("ssh_browser.json", browser))
    capture.save("evidence.json", capture.bundle)
    result = smartcard.validate_smartcard_connected_release_evidence(capture.root / "evidence.json")
    assert not result.passed and "shared socket" in result.errors[0]


@pytest.mark.parametrize(("case", "message"), [
    ("software-token", "selected hardware token only while inserted"),
    ("always-present", "selected hardware token only while inserted"),
    ("wrong-certificate", "certificate fingerprint"),
    ("fake-certificate", "supported OpenSSH public key"),
    ("other-agent-key", "agent identities must match"),
    ("profile-selection", "saved SSH profile must select"),
    ("actual-session", "one remote terminal and SFTP connection"),
    ("other-fingerprint", "one remote terminal and SFTP connection"),
    ("unrelated-sftp", "one remote terminal and SFTP connection"),
    ("wrong-socket", "shared socket"),
    ("display-only", "SFTP listing must contain"),
    ("wrong-source", "tested release source, target and asset"),
    ("tampered", "SHA-256 differs"),
    ("pass-flags", "structured JSON"),
])
def test_smartcard_capture_rejects_incomplete_or_inconsistent_proof(capture, case, message):
    def publish(action, data):
        entry = capture.bundle[action]
        entry.update(capture.save(entry["evidence_file"], data))

    if case in {"software-token", "always-present", "wrong-certificate", "fake-certificate"}:
        if case == "software-token":
            capture.management["present_tokens"] = capture.save("inserted.txt", capture.probe.replace(b"Hardware", b"Generic"))
        elif case == "always-present":
            capture.management["removed_tokens"] = capture.save("removed.txt", capture.probe)
        else:
            data = b"different certificate bytes"
            capture.management["certificate_der"] = capture.save("card.der", data)
            if case == "fake-certificate":
                capture.bundle["certificate"]["fingerprint_sha256"] = hashlib.sha256(data).hexdigest()
        publish("management_interface", capture.management)
    elif case == "other-agent-key":
        publish("mobagent", b"ssh-ed25519 other-key\n")
    elif case == "profile-selection":
        capture.profile["options"]["smartcard_certificate_id"] = "another-card"
        publish("ssh_session_selection", capture.profile)
    elif case == "tampered":
        capture.save("openssh.log", b"changed log")
    elif case == "pass-flags":
        publish("ssh_browser", b"all smart-card checks passed")
    else:
        if case == "actual-session":
            capture.browser["sshd_log"] = capture.save("openssh.log", b"all checks passed")
        elif case == "other-fingerprint":
            log = capture.log.replace(capture.fingerprint.encode(), b"SHA256:" + b"x" * 43)
            capture.browser["sshd_log"] = capture.save("openssh.log", log)
        elif case == "unrelated-sftp":
            capture.browser["sshd_log"] = capture.save("openssh.log", capture.log.replace(b"31223 id 1", b"31224 id 1"))
        elif case == "wrong-socket":
            capture.browser["sftp_argv"] = [arg for arg in capture.browser["sftp_argv"] if not arg.startswith("ControlPath=")]
        elif case == "display-only":
            capture.browser["sftp_listing"] = capture.save("listing.txt", b"unrelated files\n")
        elif case == "wrong-source":
            capture.browser["source"] = {**capture.browser["source"], "head_sha": "d" * 40}
        publish("ssh_browser", capture.browser)
    capture.save("evidence.json", capture.bundle)

    result = smartcard.validate_smartcard_connected_release_evidence(capture.root / "evidence.json")
    assert not result.passed
    assert any(message in error for error in result.errors)

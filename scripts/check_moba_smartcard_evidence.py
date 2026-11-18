from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import re
import sys
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for location in (ROOT, SRC):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.moba_smartcards import (  # noqa: E402
    MobaSmartCardReleaseEvidenceValidation,
    validate_smartcard_release_evidence,
)
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import secure_regular_file  # noqa: E402

CAPTURE_SCHEMA = "row.moba-smartcard.connected-capture.v1"
MAX_CAPTURE_BYTES = 1024 * 1024
TOKEN_HEADER = re.compile(r"^Token \d+:$", re.MULTILINE)
TOKEN = re.compile(r"^Token \d+:\n[ \t]+URL: (pkcs11:\S+)\n[ \t]+Label: [^\n]*\n[ \t]+Type: (.+)$", re.MULTILINE)
CONNECT = re.compile(r"^Connection from (\S+) port (\d+) on (\S+) port (\d+)\b", re.MULTILINE)
AUTH = re.compile(r"^Accepted publickey for (\S+) from (\S+) port (\d+) ssh2: \S+ (SHA256:[A-Za-z0-9+/]{43})(?:\s|$)", re.MULTILINE)
SHELL = re.compile(r"^Starting session: shell on \S+ for (\S+) from (\S+) port (\d+) id (\d+)$", re.MULTILINE)
SFTP = re.compile(r"^Starting session: subsystem 'sftp' for (\S+) from (\S+) port (\d+) id (\d+)$", re.MULTILINE)


def read_capture(root: Path, name: Any, label: str) -> tuple[Path, bytes]:
    path, error = secure_regular_file(root, name, label)
    if path is None:
        raise ValueError(error)
    with path.open("rb") as stream:
        data = stream.read(MAX_CAPTURE_BYTES + 1)
    if len(data) > MAX_CAPTURE_BYTES:
        raise ValueError(f"{label} exceeds 1 MiB")
    return path, data


def attachment(root: Path, entry: Any, label: str) -> bytes:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} requires a file and SHA-256")
    _, content = read_capture(root, entry.get("evidence_file"), label)
    if hashlib.sha256(content).hexdigest() != entry.get("evidence_sha256"):
        raise ValueError(f"{label} SHA-256 differs from the evidence")
    return content


def json_object(content: bytes, label: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain structured JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return data


def captured_tokens(content: bytes) -> dict[str, list[str]]:
    text = "\n".join(content.decode().splitlines())
    entries = TOKEN.findall(text)
    tokens = {url: types.split(", ") for url, types in entries}
    if len(entries) != len(tokens) or len(TOKEN_HEADER.findall(text)) != len(tokens) or (text.strip() and not tokens):
        raise ValueError("token inventories must contain p11tool --list-tokens output")
    return tokens


def verify_card_key(root: Path, certificate: dict[str, Any], management: dict[str, Any], agent: bytes) -> str:
    try:
        from cryptography import x509
        from cryptography.exceptions import UnsupportedAlgorithm
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    except ImportError as exc:
        raise ValueError("install ROW's security extra to verify the captured smart-card certificate") from exc

    present = captured_tokens(attachment(root, management.get("present_tokens"), "inserted card"))
    removed = captured_tokens(attachment(root, management.get("removed_tokens"), "removed card"))
    token = management.get("token_url")
    if (
        not isinstance(token, str) or "Hardware token" not in present.get(token, []) or token in removed
        or not removed.keys() <= present.keys()
    ):
        raise ValueError("token inventories must show the selected hardware token only while inserted")

    der = attachment(root, management.get("certificate_der"), "card certificate")
    if hashlib.sha256(der).hexdigest() != certificate["fingerprint_sha256"]:
        raise ValueError("exported card certificate differs from the selected certificate fingerprint")
    try:
        key = x509.load_der_x509_certificate(der).public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
    except (UnsupportedAlgorithm, ValueError) as exc:
        raise ValueError("card certificate must contain a supported OpenSSH public key") from exc
    expected = key.split()
    exported = management.get("exported_openssh_public_key")
    if (
        not isinstance(exported, str) or exported.encode().split()[:2] != expected
        or certificate["openssh_public_key"].encode().split()[:2] != expected
        or expected not in [line.split()[:2] for line in agent.splitlines()]
    ):
        raise ValueError("exported OpenSSH and agent identities must match the card certificate public key")
    digest = hashlib.sha256(base64.b64decode(expected[1], validate=True)).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def verify_transport(log: str, login: str, host: str, port: int, fingerprint: str) -> None:
    connections = [match for match in CONNECT.finditer(log) if match.group(3, 4) == (host, str(port))]
    accepted = [match for match in AUTH.finditer(log) if match.group(1) == login]
    if len(accepted) == 1:
        auth = accepted[0]
        client, source_port = auth.group(2, 3)
        connection = [match for match in connections if match.group(1, 2) == (client, source_port)]
        sessions = (login, client, source_port)
        shells = [match for match in SHELL.finditer(log) if match.group(1) == login]
        transfers = [match for match in SFTP.finditer(log) if match.group(1) == login]
        if (
            len(connection) == 1 and len(shells) == 1 and transfers and auth.group(4) == fingerprint
            and shells[0].group(1, 2, 3) == sessions and connection[0].start() < auth.start() < shells[0].start()
            and all(transfer.group(1, 2, 3) == sessions and shells[0].start() < transfer.start()
                    and shells[0].group(4) != transfer.group(4) for transfer in transfers)
            and ipaddress.ip_address(client) != ipaddress.ip_address(host)
            and not ipaddress.ip_address(client).is_loopback and not ipaddress.ip_address(host).is_loopback
            and 0 < int(source_port) < 65536
        ):
            return
    raise ValueError("OpenSSH log must show the selected key authenticating one remote terminal and SFTP connection")


def uses_options(argv: Any, program: str, target: str, required: tuple[tuple[str, str], ...]) -> bool:
    if (
        not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv)
        or PurePosixPath(argv[0]).name != program or argv[-1] != target
    ):
        return False
    pairs = list(pairwise(argv))
    return all(pairs.count(pair) == 1 for pair in required)


def verify_browser(root: Path, browser: dict[str, Any], profile: dict[str, Any], provider: str) -> None:
    terminal, sftp = browser.get("terminal_argv"), browser.get("sftp_argv")
    socket, fixture = browser.get("control_path"), browser.get("fixture_name")
    if (
        not isinstance(socket, str) or not socket.startswith("/")
        or not isinstance(fixture, str) or not re.fullmatch(r"row-smartcard-[0-9a-f]{32}\.txt", fixture)
        or browser.get("profile") != profile.get("name")
        or not isinstance(browser.get("file_rows"), list) or fixture not in browser["file_rows"]
    ):
        raise ValueError("file browser capture must record the selected profile, control socket and unique remote file row")
    quoted = provider.replace("\\", "\\\\").replace('"', '\\"')
    target = f"{profile['username']}@{profile['host']}"
    port = str(profile["port"])
    control_path = ("-o", f"ControlPath={socket}")
    if not (
        uses_options(terminal, "ssh", target, (("-p", port), ("-I", provider), control_path, ("-o", "ControlMaster=auto")))
        and uses_options(sftp, "sftp", target, (("-P", port), ("-o", f'PKCS11Provider="{quoted}"'), control_path,
                                                ("-o", "ControlMaster=no"), ("-o", "BatchMode=yes")))
    ):
        raise ValueError("terminal and SFTP commands must use the selected provider, target and shared socket")
    listing = attachment(root, browser.get("sftp_listing"), "SFTP listing").decode()
    if not any(line.rstrip().endswith((f" {fixture}", f"/{fixture}")) for line in listing.splitlines()):
        raise ValueError("SFTP listing must contain the remote file shown in the browser")


def validate_smartcard_connected_release_evidence(
    evidence_path: Path, *, assets_dir: Path | None = None,
) -> MobaSmartCardReleaseEvidenceValidation:
    root = assets_dir if assets_dir is not None else evidence_path.parent
    try:
        relative = evidence_path.absolute().relative_to(root.absolute()).as_posix()
        evidence, content = read_capture(root, relative, "smart-card release evidence")
        bundle = json_object(content, "smart-card release evidence")
        identity = capture_release_identity(bundle, "smart-card release evidence")
        actions = {name: attachment(root, bundle.get(name), name) for name in (
            "management_interface", "ssh_session_selection", "mobagent", "ssh_browser",
        )}
        result = validate_smartcard_release_evidence(evidence, assets_dir=root)
        if not result.passed:
            return result

        certificate = bundle["certificate"]
        management = json_object(actions["management_interface"], "card management capture")
        profile = json_object(actions["ssh_session_selection"], "saved SSH profile")
        browser = json_object(actions["ssh_browser"], "connected browser capture")
        if (
            browser.get("schema") != CAPTURE_SCHEMA or browser.get("release_target") != bundle["release_target"]
            or capture_release_identity(browser, "connected browser capture") != identity
        ):
            raise ValueError("connected browser capture must match the tested release source, target and asset")
        provider = certificate["provider"]
        options = profile.get("options")
        if (
            not provider.startswith("pkcs11:") or not PurePosixPath(provider.removeprefix("pkcs11:")).is_absolute()
            or not isinstance(options, dict) or options.get("smartcard_certificate_id") != certificate["id"]
            or options.get("smartcard_provider") != provider or options.get("add_smartcard_to_mobagent") != "true"
            or profile.get("protocol") != "ssh" or not isinstance(profile.get("name"), str) or not profile["name"]
            or not isinstance(profile.get("username"), str) or not profile["username"]
            or not isinstance(profile.get("host"), str) or type(profile.get("port")) is not int
            or not 0 < profile["port"] < 65536
        ):
            raise ValueError("saved SSH profile must select the card provider, certificate and agent handoff")
        fingerprint = verify_card_key(root, certificate, management, actions["mobagent"])
        verify_browser(root, browser, profile, provider.removeprefix("pkcs11:"))
        verify_transport(
            attachment(root, browser.get("sshd_log"), "SSH server log").decode(),
            profile["username"], profile["host"], profile["port"], fingerprint,
        )
        result.summary.update(identity, verified_hardware_smartcard=True, verified_multiplexed_sftp=True,
                              openssh_key_fingerprint=fingerprint)
        return result
    except (OSError, ValueError) as exc:
        return MobaSmartCardReleaseEvidenceValidation(str(evidence_path), str(root), False, [str(exc)], [], {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify MobaXterm 26.4 smart-card management evidence.")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = validate_smartcard_connected_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba smart-card evidence passed")
    else:
        for error in result.errors:
            print(f"moba smart-card evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

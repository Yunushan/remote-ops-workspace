from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.cli import build_parser  # noqa: E402
from remote_ops_workspace.features import load_feature_manifest  # noqa: E402
from remote_ops_workspace.keys import build_keygen_plan  # noqa: E402
from remote_ops_workspace.launcher import build_launch_plan  # noqa: E402
from remote_ops_workspace.models import Profile, Tunnel  # noqa: E402

SAMPLE_HOST = "row-feature-check.example"

IMPLEMENTED_STATUS_PREFIX = "implemented"

FEATURE_REALITY_RULES: dict[str, dict[str, Any]] = {
    "protocol.ssh": {
        "protocols": ["ssh"],
        "module_attrs": ["remote_ops_workspace.launcher:build_launch_plan"],
    },
    "protocol.sftp": {
        "protocols": ["sftp"],
        "cli": ["files open", "files ls", "files get", "files put", "files queue"],
        "module_attrs": ["remote_ops_workspace.file_transfer:build_sftp_interactive_plan"],
    },
    "moba.ssh-browser": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_moba_connected_session_state"],
        "source_tokens": {
            "src/remote_ops_workspace/gui.py": ["MobaConnectedSessionPanel", "mobaSftpBrowser", "mobaSftpFileTable"]
        },
    },
    "moba.follow-terminal-folder": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_follow_terminal_folder_plan"],
        "source_tokens": {
            "src/remote_ops_workspace/gui.py": ["mobaFollowTerminalFolder", "follow_folder_plan"]
        },
    },
    "moba.remote-monitoring": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_remote_monitoring_plan"],
        "source_tokens": {
            "src/remote_ops_workspace/gui.py": ["mobaRemoteMonitoring", "mobaMonitoringMetric"]
        },
    },
    "moba.telemetry-status-bar": {
        "module_attrs": ["remote_ops_workspace.moba_connected:RemoteMonitoringSnapshot"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["mobaTelemetryBar", "mobaTelemetryItem"]},
    },
    "moba.ssh-connection-banner": {
        "module_attrs": ["remote_ops_workspace.moba_connected:build_ssh_connection_banner"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["mobaSshBanner", "mobaSshBannerLine"]},
    },
    "protocol.scp": {"protocols": ["scp"]},
    "protocol.rdp": {"protocols": ["rdp"]},
    "protocol.vnc": {"protocols": ["vnc"]},
    "protocol.telnet": {"protocols": ["telnet"]},
    "protocol.rlogin": {"protocols": ["rlogin"]},
    "protocol.rsh": {"protocols": ["rsh"]},
    "protocol.ftp": {"protocols": ["ftp"]},
    "protocol.mosh": {"protocols": ["mosh"]},
    "protocol.spice": {"protocols": ["spice"]},
    "protocol.x2go": {"protocols": ["x2go"]},
    "protocol.xdmcp": {"protocols": ["xdmcp"]},
    "protocol.ica": {"protocols": ["ica"]},
    "protocol.http": {"protocols": ["http", "https"]},
    "protocol.raw": {"protocols": ["raw"]},
    "protocol.serial": {"protocols": ["serial"]},
    "terminal.tabs": {
        "module_attrs": ["remote_ops_workspace.terminal:TerminalPanePlan"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["class TerminalPane"]},
    },
    "terminal.local-shell": {
        "protocols": ["local-shell"],
        "module_attrs": ["remote_ops_workspace.terminal:default_shell_plan"],
    },
    "terminal.splits": {
        "module_attrs": ["remote_ops_workspace.terminal:split_shell_plans"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["def add_split"]},
    },
    "terminal.layouts": {
        "cli": ["layout save", "layout run"],
        "module_attrs": ["remote_ops_workspace.layouts:build_layout_terminal_plans"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["open_selected_layout"]},
    },
    "terminal.broadcast": {
        "cli": ["broadcast"],
        "module_attrs": ["remote_ops_workspace.broadcast:run_broadcast"],
    },
    "terminal.shortcuts": {
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["QShortcut("]},
    },
    "terminal.search": {
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["def find_log_text"]},
    },
    "terminal.macros": {
        "cli": ["snippet add", "snippet run"],
        "module_attrs": ["remote_ops_workspace.snippets:SnippetStore"],
    },
    "session.profiles": {
        "cli": ["profile add", "profile list", "profile show"],
        "module_attrs": ["remote_ops_workspace.storage:ProfileStore"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["class ProfileDialog"]},
    },
    "session.inheritance": {
        "cli": ["profile defaults"],
        "module_attrs": ["remote_ops_workspace.storage:ProfileStore.set_group_defaults"],
    },
    "session.quick-connect": {
        "cli": ["connect"],
        "source_tokens": {"src/remote_ops_workspace/gui.py": ["def connect_selected"]},
    },
    "session.import-export": {
        "cli": ["export", "import"],
        "module_attrs": [
            "remote_ops_workspace.profile_importers:import_profiles",
            "remote_ops_workspace.sync:BackupService",
        ],
    },
    "security.vault": {
        "cli": ["vault init", "vault set", "vault get", "vault delete", "vault status"],
        "module_attrs": ["remote_ops_workspace.vault:LocalVault"],
    },
    "security.keys": {
        "cli": ["keygen"],
        "module_attrs": ["remote_ops_workspace.keys:build_keygen_plan"],
        "key_types": ["ed25519", "rsa"],
    },
    "security.fido": {
        "cli": ["keygen"],
        "module_attrs": ["remote_ops_workspace.keys:SECURITY_KEY_TYPES"],
        "key_types": ["ed25519-sk", "ecdsa-sk"],
    },
    "security.audit": {
        "module_attrs": ["remote_ops_workspace.audit:append_event"],
    },
    "network.tunnels": {
        "module_attrs": ["remote_ops_workspace.models:Tunnel"],
        "plans": [
            {
                "profile": Profile(
                    name="tunnel-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    tunnels=[
                        Tunnel(
                            mode="local",
                            local_port=15432,
                            remote_host="127.0.0.1",
                            remote_port=5432,
                        )
                    ],
                ),
                "contains": ["-L", "127.0.0.1:15432:127.0.0.1:5432"],
            }
        ],
    },
    "network.proxy": {
        "module_attrs": ["remote_ops_workspace.launcher:_ssh_proxy_args"],
        "plans": [
            {
                "profile": Profile(
                    name="proxy-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    options={"proxy_jump": "jump.example"},
                ),
                "contains": ["-J", "jump.example"],
            }
        ],
    },
    "network.tools": {
        "cli": ["nettool ping", "nettool trace", "nettool dns", "nettool whois", "nettool port"],
        "module_attrs": ["remote_ops_workspace.network_tools:build_network_tool_plan"],
    },
    "x11.forwarding": {
        "plans": [
            {
                "profile": Profile(
                    name="x11-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    options={"x11": "true"},
                ),
                "contains": ["-X"],
            },
            {
                "profile": Profile(
                    name="trusted-x11-proof",
                    protocol="ssh",
                    host=SAMPLE_HOST,
                    options={"x11": "trusted"},
                ),
                "contains": ["-Y"],
            },
        ],
    },
    "x11.server": {
        "cli": ["x11 start"],
        "module_attrs": ["remote_ops_workspace.x11:build_x_server_plan"],
    },
    "sync.local": {
        "cli": ["export", "import"],
        "module_attrs": ["remote_ops_workspace.sync:BackupService"],
    },
    "sync.cloud": {
        "cli": ["sync push", "sync pull"],
        "module_attrs": ["remote_ops_workspace.sync:DirectorySyncProvider"],
    },
    "web.pwa": {
        "cli": ["serve-web"],
        "module_attrs": ["remote_ops_workspace.web_server:serve_web"],
        "files": ["apps/web/index.html", "apps/web/app.js", "apps/web/manifest.json", "apps/web/sw.js"],
    },
    "android.termux": {
        "files": ["installers/install-termux.sh", "docs/ANDROID.md"],
    },
    "portable.mode": {
        "cli": ["init", "welcome"],
        "module_attrs": ["remote_ops_workspace.paths:data_dir"],
        "source_tokens": {"src/remote_ops_workspace/paths.py": ["ROW_HOME"]},
    },
    "plugins.entrypoints": {
        "cli": ["plugins list", "plugins validate", "plugins scaffold", "doctor"],
        "module_attrs": [
            "remote_ops_workspace.plugins:load_plugin_registry",
            "remote_ops_workspace.plugin_dev:validate_installed_plugins",
            "remote_ops_workspace.plugin_dev:scaffold_plugin",
        ],
    },
}


def main() -> int:
    errors = check_feature_reality()
    if errors:
        for error in errors:
            print(f"feature reality: {error}", file=sys.stderr)
        return 1
    print("feature reality alignment passed")
    return 0


def check_feature_reality() -> list[str]:
    errors: list[str] = []
    manifest = load_feature_manifest()
    features = manifest.get("features", [])
    feature_ids = {str(item.get("id", "")) for item in features}

    unknown_rule_ids = sorted(set(FEATURE_REALITY_RULES) - feature_ids)
    for feature_id in unknown_rule_ids:
        errors.append(f"reality rule references unknown feature id: {feature_id}")

    for item in features:
        feature_id = str(item.get("id", ""))
        status = str(item.get("status", ""))
        if status.startswith(IMPLEMENTED_STATUS_PREFIX) and feature_id not in FEATURE_REALITY_RULES:
            errors.append(f"{feature_id} has status {status} but no executable reality rule")

    command_paths = collect_cli_command_paths(build_parser())
    for feature_id in sorted(feature_ids & set(FEATURE_REALITY_RULES)):
        rule = FEATURE_REALITY_RULES[feature_id]
        errors.extend(check_cli_paths(feature_id, rule.get("cli", []), command_paths))
        errors.extend(check_protocol_plans(feature_id, rule.get("protocols", [])))
        errors.extend(check_named_plans(feature_id, rule.get("plans", [])))
        errors.extend(check_module_attrs(feature_id, rule.get("module_attrs", [])))
        errors.extend(check_files(feature_id, rule.get("files", [])))
        errors.extend(check_source_tokens(feature_id, rule.get("source_tokens", {})))
        errors.extend(check_key_types(feature_id, rule.get("key_types", [])))
    return errors


def collect_cli_command_paths(parser: argparse.ArgumentParser) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()

    def walk(current: argparse.ArgumentParser, prefix: tuple[str, ...]) -> None:
        subparser_actions = [
            action for action in current._actions if isinstance(action, argparse._SubParsersAction)
        ]
        if not subparser_actions:
            if prefix:
                paths.add(prefix)
            return
        for action in subparser_actions:
            for name, child in action.choices.items():
                walk(child, (*prefix, name))

    walk(parser, ())
    return paths


def check_cli_paths(
    feature_id: str,
    required_paths: list[str],
    command_paths: set[tuple[str, ...]],
) -> list[str]:
    errors: list[str] = []
    for required in required_paths:
        path = tuple(required.split())
        if path not in command_paths:
            errors.append(f"{feature_id} requires CLI command path: {required}")
    return errors


def check_protocol_plans(feature_id: str, protocols: list[str]) -> list[str]:
    errors: list[str] = []
    for protocol in protocols:
        try:
            plan = build_launch_plan(sample_profile(protocol))
        except Exception as exc:
            errors.append(f"{feature_id} cannot build {protocol} launch plan: {exc}")
            continue
        if not plan.command:
            errors.append(f"{feature_id} {protocol} launch plan has an empty command")
    return errors


def check_named_plans(feature_id: str, plan_specs: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for spec in plan_specs:
        profile = spec["profile"]
        try:
            plan = build_launch_plan(profile)
        except Exception as exc:
            errors.append(f"{feature_id} cannot build named launch plan {profile.name}: {exc}")
            continue
        for token in spec.get("contains", []):
            if token not in plan.command:
                errors.append(f"{feature_id} plan {profile.name} missing argv token: {token}")
    return errors


def check_module_attrs(feature_id: str, refs: list[str]) -> list[str]:
    errors: list[str] = []
    for ref in refs:
        module_name, separator, attr_path = ref.partition(":")
        if not separator:
            errors.append(f"{feature_id} module attribute ref must use module:attr: {ref}")
            continue
        try:
            obj: object = importlib.import_module(module_name)
            for attr in attr_path.split("."):
                obj = getattr(obj, attr)
        except Exception as exc:
            errors.append(f"{feature_id} missing module attribute {ref}: {exc}")
    return errors


def check_files(feature_id: str, required_files: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in required_files:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{feature_id} requires shipped file: {relative}")
    return errors


def check_source_tokens(feature_id: str, token_map: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    for relative, tokens in token_map.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{feature_id} source evidence file missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                errors.append(f"{feature_id} source evidence {relative} missing token: {token}")
    return errors


def check_key_types(feature_id: str, key_types: list[str]) -> list[str]:
    errors: list[str] = []
    for key_type in key_types:
        try:
            plan = build_keygen_plan(Path("feature-check-key"), key_type=key_type)
        except Exception as exc:
            errors.append(f"{feature_id} cannot build keygen plan for {key_type}: {exc}")
            continue
        if key_type not in plan.command:
            errors.append(f"{feature_id} keygen plan missing key type: {key_type}")
    return errors


def sample_profile(protocol: str) -> Profile:
    if protocol in {"http", "https"}:
        return Profile(name=f"{protocol}-proof", protocol=protocol, url=f"{protocol}://{SAMPLE_HOST}")
    if protocol == "raw":
        return Profile(name="raw-proof", protocol=protocol, host=SAMPLE_HOST, port=443)
    if protocol == "serial":
        return Profile(name="serial-proof", protocol=protocol, path="COM1", options={"baud": "115200"})
    if protocol == "local-shell":
        return Profile(name="local-shell-proof", protocol=protocol)
    if protocol == "ica":
        return Profile(name="ica-proof", protocol=protocol, path="sample.ica")
    if protocol in {"ssh1", "sshv1"}:
        return Profile(
            name=f"{protocol}-proof",
            protocol=protocol,
            host=SAMPLE_HOST,
            options={"allow_insecure_sshv1": "true"},
        )
    return Profile(name=f"{protocol}-proof", protocol=protocol, host=SAMPLE_HOST, username="operator")


if __name__ == "__main__":
    raise SystemExit(main())

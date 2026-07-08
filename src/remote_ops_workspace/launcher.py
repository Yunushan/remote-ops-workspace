from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from . import command_safety as safe
from .enterprise_policy import assert_profile_launch_allowed
from .models import Profile, Tunnel
from .plugins import LoadedPlugin, load_plugin_registry
from .profile_validation import prepare_profile


@dataclass(slots=True)
class LaunchPlan:
    protocol: str
    command: list[str]
    notes: list[str]

    def printable(self) -> str:
        return shlex.join(self.command)


class LauncherError(RuntimeError):
    pass


DEFAULT_PORTS: dict[str, int] = {
    "ssh": 22,
    "ssh1": 22,
    "sshv1": 22,
    "sftp": 22,
    "scp": 22,
    "mosh": 22,
    "telnet": 23,
    "rlogin": 513,
    "rsh": 514,
    "ftp": 21,
    "rdp": 3389,
    "vnc": 5900,
    "spice": 5900,
    "x2go": 22,
    "xdmcp": 177,
    "ica": 1494,
    "http": 80,
    "https": 443,
    "raw": 0,
    "serial": 0,
    "local-shell": 0,
}

SSH_V1_PROTOCOLS = {"ssh1", "sshv1"}
SSH_V1_OPT_IN_OPTIONS = ("allow_insecure_sshv1", "allow_unsafe_sshv1")
WINDOWS_XP_LEGACY_TARGETS = frozenset(
    {
        "windows-xp-32",
        "windows-xp-64",
    }
)
LEGACY_TARGET_OPTIONS = ("legacy_target",)
LEGACY_CRYPTO_OPT_IN_OPTIONS = ("allow_legacy_crypto", "allow_insecure_legacy_crypto")
LEGACY_RDP_SECURITY_OPT_IN_OPTIONS = ("allow_legacy_rdp_security", "allow_insecure_rdp_security")
CAPI_SMARTCARD_PROVIDER_ALIASES = frozenset(
    {
        "capi",
        "cryptoapi",
        "microsoft-capi",
        "microsoft-cryptoapi",
        "windows-capi",
        "windows-cryptoapi",
    }
)
WEAK_SSH_ALGORITHMS_BY_OPTION = {
    "ciphers": frozenset(
        {
            "3des-cbc",
            "aes128-cbc",
            "aes192-cbc",
            "aes256-cbc",
            "arcfour",
            "arcfour128",
            "arcfour256",
            "blowfish-cbc",
            "cast128-cbc",
            "none",
            "rijndael-cbc@lysator.liu.se",
        }
    ),
    "host_key_algorithms": frozenset({"ssh-dss", "ssh-rsa"}),
    "kex_algorithms": frozenset(
        {
            "diffie-hellman-group-exchange-sha1",
            "diffie-hellman-group1-sha1",
            "diffie-hellman-group14-sha1",
        }
    ),
    "macs": frozenset(
        {
            "hmac-md5",
            "hmac-md5-96",
            "hmac-ripemd160",
            "hmac-ripemd160@openssh.com",
            "hmac-sha1",
            "hmac-sha1-96",
            "umac-64@openssh.com",
        }
    ),
}


def build_launch_plan(profile: Profile) -> LaunchPlan:
    plugin_registry = load_plugin_registry()
    profile = prepare_profile(profile, extra_protocols=plugin_registry.protocols)
    protocol = profile.protocol.lower().strip()
    notes: list[str] = []

    plugin = plugin_registry.plugin_for_protocol(protocol)
    if plugin is not None:
        return _build_plugin_plan(plugin, profile)

    if protocol in {"ssh", *SSH_V1_PROTOCOLS, "sftp", "scp"}:
        return _build_ssh_family(profile, protocol)
    if protocol == "mosh":
        return _build_mosh(profile)
    if protocol == "rdp":
        return _build_rdp(profile)
    if protocol == "vnc":
        return _build_vnc(profile)
    if protocol == "spice":
        return _build_spice(profile)
    if protocol == "x2go":
        return _build_x2go(profile)
    if protocol == "xdmcp":
        return _build_xdmcp(profile)
    if protocol == "ica":
        return _build_ica(profile)
    if protocol in {"telnet", "rlogin", "rsh", "ftp"}:
        port = _port(profile, protocol)
        target = _host(profile)
        return LaunchPlan(protocol, [protocol, target, str(port)], notes)
    if protocol in {"http", "https", "www"}:
        return _build_url(profile, protocol)
    if protocol == "raw":
        executable = _first_available(["nc", "ncat", "netcat"])
        if not executable:
            executable = "nc"
            notes.append("Install nc/ncat/netcat for raw socket profiles.")
        return LaunchPlan(protocol, [executable, _host(profile), str(_port(profile, "raw", required=True))], notes)
    if protocol == "serial":
        return _build_serial(profile)
    if protocol in {"local", "local-shell", "shell"}:
        shell = os.environ.get("SHELL") or os.environ.get("COMSPEC") or ("cmd.exe" if _is_windows() else "/bin/sh")
        return LaunchPlan("local-shell", [shell], notes)
    if protocol == "custom":
        if not profile.command:
            raise LauncherError("custom profile requires command")
        return LaunchPlan(protocol, safe.argv(profile.command, "custom command"), ["Custom command profile."])

    raise LauncherError(f"unsupported protocol: {protocol}")


def launch(profile: Profile, dry_run: bool = False) -> LaunchPlan:
    assert_profile_launch_allowed(profile, surface="launcher")
    plan = build_launch_plan(profile)
    safe.argv_list(plan.command, "launch command")
    if dry_run:
        return plan
    subprocess.Popen(plan.command)  # noqa: S603 - command is built as an argv list, not shell=True
    return plan


def protocol_clients() -> dict[str, list[str]]:
    clients = {
        "ssh": ["ssh"],
        "ssh1": ["ssh"],
        "sshv1": ["ssh"],
        "sftp": ["sftp"],
        "scp": ["scp"],
        "mosh": ["mosh"],
        "rdp": ["mstsc", "xfreerdp", "wlfreerdp"],
        "vnc": ["vncviewer", "tigervnc", "realvnc-vnc-viewer"],
        "spice": ["remote-viewer", "virt-viewer"],
        "x2go": ["x2goclient"],
        "xdmcp": ["Xorg", "Xquartz", "vcxsrv", "xnest"],
        "ica": ["wfica"],
        "telnet": ["telnet"],
        "rlogin": ["rlogin"],
        "rsh": ["rsh"],
        "ftp": ["ftp", "lftp"],
        "raw": ["nc", "ncat", "netcat"],
        "serial": ["picocom", "screen", "cu", "putty"],
        "keygen": ["ssh-keygen"],
    }
    for protocol, executables in load_plugin_registry().protocol_clients().items():
        clients[protocol] = executables
    return clients


def _build_plugin_plan(plugin: LoadedPlugin, profile: Profile) -> LaunchPlan:
    plan = plugin.object.build(profile)
    if not isinstance(plan, LaunchPlan):
        raise LauncherError(f"plugin {plugin.name} returned invalid launch plan for protocol {profile.protocol}")
    command = safe.argv_list(plan.command, f"plugin {plugin.name} launch command")
    protocol = safe.clean_text(plan.protocol or profile.protocol, f"plugin {plugin.name} protocol").strip().lower()
    notes = [f"Built by plugin: {plugin.name}", *plan.notes]
    return LaunchPlan(protocol, command, notes)


def _build_ssh_family(profile: Profile, protocol: str) -> LaunchPlan:
    host = _host(profile)
    port = _port(profile, protocol)
    target = _target(profile, host)
    notes: list[str] = []

    if protocol in {"ssh", *SSH_V1_PROTOCOLS}:
        cmd = ["ssh"]
        if protocol in SSH_V1_PROTOCOLS:
            _require_sshv1_opt_in(profile)
            cmd.append("-1")
            notes.append("SSHv1 is insecure, obsolete, and disabled unless allow_insecure_sshv1=true is set.")
            notes.append("Use only for isolated legacy systems; protocol v1 cannot provide modern SSH security.")
            notes.append("Requires an SSH client build that still supports protocol version 1.")
        cmd.extend(["-p", str(port)])
        cmd.extend(_ssh_identity_args(profile))
        cmd.extend(_ssh_connection_option_args(profile.options))
        notes.extend(_ssh_smartcard_notes(profile.options))
        cmd.extend(_ssh_proxy_args(profile, notes))
        cmd.extend(_ssh_tunnel_args(profile.tunnels))
        if profile.options.get("x11", "").lower() in {"1", "true", "yes", "trusted"}:
            cmd.append("-Y" if profile.options.get("x11") == "trusted" else "-X")
            notes.append("X11 forwarding requested. Ensure XQuartz, Xorg or VcXsrv is running locally.")
        if _option_bool(profile.options, "agent_forward", "forward_agent"):
            cmd.append("-A")
        cmd.append(target)
        return LaunchPlan(protocol, cmd, notes)

    if protocol == "sftp":
        cmd = ["sftp", "-P", str(port)]
        cmd.extend(_ssh_identity_args(profile))
        cmd.extend(_ssh_connection_option_args(profile.options))
        notes.extend(_ssh_smartcard_notes(profile.options))
        cmd.extend(_ssh_proxy_args(profile, notes))
        cmd.append(target)
        return LaunchPlan(protocol, cmd, notes)

    cmd = ["scp", "-P", str(port)]
    cmd.extend(_ssh_identity_args(profile))
    cmd.extend(_ssh_connection_option_args(profile.options))
    notes.extend(_ssh_smartcard_notes(profile.options))
    cmd.extend(_ssh_proxy_args(profile, notes))
    cmd.append(target)
    notes.append("SCP profile needs source/destination arguments for real transfer.")
    return LaunchPlan(protocol, cmd, notes)


def _ssh_identity_args(profile: Profile) -> list[str]:
    if not profile.identity_file:
        return []
    return ["-i", safe.path_arg(profile.identity_file, "identity file")]


def _ssh_connection_option_args(options: Mapping[str, str]) -> list[str]:
    args: list[str] = []
    if _option_bool(options, "compression"):
        args.append("-C")

    for option_name, open_ssh_name in (
        ("connect_timeout", "ConnectTimeout"),
        ("keepalive_interval", "ServerAliveInterval"),
        ("server_alive_interval", "ServerAliveInterval"),
        ("keepalive_count", "ServerAliveCountMax"),
        ("server_alive_count_max", "ServerAliveCountMax"),
    ):
        value = _option_positive_int(options, option_name)
        if value is not None:
            args.extend(["-o", f"{open_ssh_name}={value}"])

    strict_host_key_checking = _option_enum(
        options,
        "strict_host_key_checking",
        allowed={"accept-new", "ask", "no", "yes"},
    )
    if strict_host_key_checking:
        args.extend(["-o", f"StrictHostKeyChecking={strict_host_key_checking}"])

    user_known_hosts_file = _option(options, "user_known_hosts_file", "known_hosts_file")
    if user_known_hosts_file:
        args.extend(["-o", f"UserKnownHostsFile={safe.path_arg(user_known_hosts_file, 'user_known_hosts_file')}"])

    identity_agent = _option(options, "identity_agent", "ssh_identity_agent", "mobagent_socket")
    if identity_agent:
        args.extend(["-o", f"IdentityAgent={safe.path_arg(identity_agent, 'identity_agent')}"])

    certificate_file = _option(
        options,
        "certificate_file",
        "ssh_certificate_file",
        "cert_file",
        "smartcard_certificate_file",
        "smart_card_certificate_file",
        "smartcard_cert_file",
    )
    if certificate_file:
        args.extend(["-o", f"CertificateFile={safe.path_arg(certificate_file, 'certificate_file')}"])

    security_key_provider = _option(options, "security_key_provider", "ssh_security_key_provider", "sk_provider")
    if security_key_provider:
        args.extend(
            [
                "-o",
                f"SecurityKeyProvider={safe.path_arg(security_key_provider, 'security_key_provider')}",
            ]
        )

    pkcs11_provider = _option(options, "pkcs11_provider", "smartcard_pkcs11_provider", "smart_card_pkcs11_provider")
    smartcard_provider = _option(options, "smartcard_provider", "smart_card_provider")
    provider_path = _smartcard_provider_path(pkcs11_provider, "pkcs11_provider")
    smartcard_provider_path = _smartcard_provider_path(smartcard_provider, "smartcard_provider")
    if provider_path and smartcard_provider_path and provider_path != smartcard_provider_path:
        raise LauncherError("pkcs11_provider and smartcard_provider must reference the same provider when both are set")
    provider_path = provider_path or smartcard_provider_path
    if provider_path:
        args.extend(["-I", provider_path])

    log_level = _option_enum(
        options,
        "log_level",
        allowed={"debug", "debug1", "debug2", "debug3", "error", "fatal", "info", "quiet", "verbose"},
    )
    if log_level:
        args.extend(["-o", f"LogLevel={log_level.upper()}"])

    for option_name, open_ssh_name in (
        ("ciphers", "Ciphers"),
        ("host_key_algorithms", "HostKeyAlgorithms"),
        ("kex_algorithms", "KexAlgorithms"),
        ("macs", "MACs"),
    ):
        value = _option(options, option_name)
        if value:
            _validate_ssh_algorithm_override(options, option_name, value)
            args.extend(["-o", f"{open_ssh_name}={_option_token(value, option_name)}"])

    return args


def _smartcard_provider_path(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    text = safe.clean_text(value, label).strip()
    if not text:
        return None
    if text.lower() in CAPI_SMARTCARD_PROVIDER_ALIASES:
        return None
    if text.lower().startswith("pkcs11:"):
        text = text.split(":", 1)[1].strip()
        if not text:
            raise LauncherError(f"{label} pkcs11: value requires a provider path")
    return safe.option_value(text, label)


def _ssh_smartcard_notes(options: Mapping[str, str]) -> list[str]:
    smartcard_requested = any(
        _option(options, name)
        for name in (
            "smartcard_auth",
            "smart_card_auth",
            "smartcard_provider",
            "smart_card_provider",
            "pkcs11_provider",
            "smartcard_pkcs11_provider",
            "smart_card_pkcs11_provider",
            "certificate_file",
            "ssh_certificate_file",
            "cert_file",
            "smartcard_certificate_file",
            "smart_card_certificate_file",
            "smartcard_cert_file",
            "identity_agent",
            "ssh_identity_agent",
            "mobagent_socket",
            "security_key_provider",
            "ssh_security_key_provider",
            "sk_provider",
            "mobagent_smartcard",
            "add_smartcard_to_mobagent",
        )
    )
    if not smartcard_requested:
        return []
    notes = [
        "Smart-card/certificate SSH auth requested; OpenSSH options are emitted for configured certificate, PKCS#11 provider, security-key provider or agent handoff."
    ]
    provider = _option(options, "smartcard_provider", "smart_card_provider")
    if provider and safe.clean_text(provider, "smartcard_provider").strip().lower() in CAPI_SMARTCARD_PROVIDER_ALIASES:
        notes.append(
            "Microsoft CryptoAPI/CAPI smart-card provider requested; use a Windows OpenSSH/CAPI provider or MobAgent-compatible agent bridge."
        )
    if _option_bool(options, "mobagent_smartcard", "add_smartcard_to_mobagent"):
        notes.append("MobAgent smart-card handoff requested through the configured SSH agent/IdentityAgent.")
    return notes


def _ssh_proxy_args(profile: Profile, notes: list[str]) -> list[str]:
    args: list[str] = []
    proxy_jump = profile.options.get("proxy_jump") or profile.options.get("jump_host")
    proxy_command = profile.options.get("proxy_command")
    if proxy_jump:
        args.extend(["-J", _validate_proxy_jump(proxy_jump)])
    if proxy_command:
        if profile.options.get("allow_unsafe_proxy_command", "").lower() not in {"1", "true", "yes"}:
            raise LauncherError("proxy_command is disabled by default; use proxy_jump or set allow_unsafe_proxy_command=true")
        args.extend(["-o", f"ProxyCommand={safe.shellish_text(proxy_command, 'proxy_command')}"])
        notes.append("ProxyCommand is executed by OpenSSH; only use trusted profile data.")
    return args


def _ssh_tunnel_args(tunnels: Iterable[Tunnel]) -> list[str]:
    args: list[str] = []
    for tunnel in tunnels:
        mode = tunnel.mode.lower()
        if mode == "local":
            local_host = safe.host(tunnel.local_host, "tunnel local host")
            local_port = safe.port(tunnel.local_port, "tunnel local port")
            remote_host = safe.host(tunnel.remote_host, "tunnel remote host")
            remote_port = safe.port(tunnel.remote_port, "tunnel remote port")
            args.extend(["-L", f"{local_host}:{local_port}:{remote_host}:{remote_port}"])
        elif mode == "remote":
            local_host = safe.host(tunnel.local_host, "tunnel local host")
            local_port = safe.port(tunnel.local_port, "tunnel local port")
            remote_host = safe.host(tunnel.remote_host, "tunnel remote host")
            remote_port = safe.port(tunnel.remote_port, "tunnel remote port")
            args.extend(["-R", f"{local_host}:{local_port}:{remote_host}:{remote_port}"])
        elif mode == "dynamic":
            local_host = safe.host(tunnel.local_host, "tunnel local host")
            local_port = safe.port(tunnel.local_port, "tunnel local port")
            args.extend(["-D", f"{local_host}:{local_port}"])
        else:
            raise LauncherError(f"unsupported tunnel mode: {tunnel.mode}")
    return args


def _build_mosh(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    port = _port(profile, "mosh")
    target = _target(profile, host)
    notes: list[str] = []
    ssh_cmd = ["ssh", "-p", str(port)]
    ssh_cmd.extend(_ssh_identity_args(profile))
    ssh_cmd.extend(_ssh_connection_option_args(profile.options))
    ssh_cmd.extend(_ssh_proxy_args(profile, notes))
    if _option_bool(profile.options, "agent_forward", "forward_agent"):
        ssh_cmd.append("-A")

    cmd = ["mosh", "--ssh", shlex.join(ssh_cmd)]
    mosh_port = _option(profile.options, "mosh_port", "mosh_ports")
    if mosh_port:
        cmd.append(f"--port={_mosh_port(mosh_port)}")
    server = _option(profile.options, "mosh_server")
    if server:
        cmd.append(f"--server={_option_token(server, 'mosh_server')}")
    predict = _option_enum(profile.options, "predict", "mosh_predict", allowed={"adaptive", "always", "experimental", "never"})
    if predict:
        cmd.append(f"--predict={predict}")
    bind_server = _option(profile.options, "bind_server", "mosh_bind_server")
    if bind_server:
        cmd.append(f"--bind-server={_option_token(bind_server, 'bind_server')}")
    if profile.tunnels:
        notes.append("Mosh does not carry SSH tunnels; tunnel definitions are ignored for this launch.")
    cmd.append(target)
    return LaunchPlan("mosh", cmd, notes)


def _require_sshv1_opt_in(profile: Profile) -> None:
    if _option_bool(profile.options, *SSH_V1_OPT_IN_OPTIONS) and _legacy_crypto_enabled(profile.options):
        return
    raise LauncherError(
        "SSHv1 is disabled by default; set allow_insecure_sshv1=true, "
        "legacy_target=windows-xp-32 or windows-xp-64, and allow_legacy_crypto=true "
        "only for isolated legacy systems"
    )


def _build_rdp(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    port = _port(profile, "rdp")
    notes: list[str] = []
    security = _option_enum(profile.options, "security", "rdp_security", allowed={"ext", "nla", "rdp", "tls"})
    if security == "rdp":
        _require_legacy_rdp_security_opt_in(profile.options)
        notes.append("RDP native security is a legacy compatibility mode; use only for isolated XP remote targets.")
    if _is_windows():
        cmd = ["mstsc", f"/v:{host}:{port}"]
        if _option_bool(profile.options, "fullscreen"):
            cmd.append("/f")
        else:
            cmd.extend(_rdp_dimension_args(profile.options))
        for option_name, mstsc_flag in (
            ("admin", "/admin"),
            ("multimon", "/multimon"),
            ("prompt", "/prompt"),
            ("public", "/public"),
            ("remote_guard", "/remoteGuard"),
            ("restricted_admin", "/restrictedAdmin"),
            ("span", "/span"),
        ):
            if _option_bool(profile.options, option_name):
                cmd.append(mstsc_flag)
        return LaunchPlan("rdp", cmd, [*notes, "Uses Windows MSTSC."])
    executable = _first_available(["xfreerdp", "wlfreerdp"]) or "xfreerdp"
    cmd = [executable, f"/v:{host}:{port}"]
    if profile.username:
        cmd.append(f"/u:{safe.clean_text(profile.username, 'username')}")
    domain = _option(profile.options, "domain")
    if domain:
        cmd.append(f"/d:{_option_token(domain, 'rdp domain')}")
    if _option_bool(profile.options, "fullscreen"):
        cmd.append("/f")
    else:
        cmd.extend(_rdp_dimension_args(profile.options))
    if _option_bool(profile.options, "dynamic_resolution", default=True):
        cmd.append("/dynamic-resolution")
    certificate_mode = _option_enum(profile.options, "cert", "certificate", allowed={"deny", "ignore", "name", "tofu"})
    if _option_bool(profile.options, "cert_ignore"):
        certificate_mode = "ignore"
    if certificate_mode:
        cmd.append(f"/cert:{certificate_mode}")
    if security:
        cmd.append(f"/sec:{security}")
    clipboard = _option(profile.options, "clipboard")
    if clipboard is not None:
        cmd.append("/clipboard" if _bool_value(clipboard, "clipboard") else "/clipboard:false")
    drive = _option(profile.options, "drive")
    if drive:
        cmd.append(f"/drive:{_rdp_drive(drive)}")
    scale = _option_bounded_int(profile.options, "scale", minimum=10, maximum=500)
    if scale is not None:
        cmd.append(f"/scale:{scale}")
    for option_name, freerdp_flag in (
        ("admin", "/admin"),
        ("audio", "/sound"),
        ("fonts", "/fonts"),
        ("gfx", "/gfx"),
        ("microphone", "/microphone"),
        ("multimon", "/multimon"),
        ("span", "/span"),
        ("themes", "/themes"),
    ):
        if _option_bool(profile.options, option_name):
            cmd.append(freerdp_flag)
    notes.append("Install FreeRDP for non-Windows RDP sessions.")
    return LaunchPlan("rdp", cmd, notes)


def _build_vnc(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    port = _port(profile, "vnc")
    executable = _first_available(["vncviewer", "tigervnc", "realvnc-vnc-viewer"]) or "vncviewer"
    cmd = [executable]
    if _option_bool(profile.options, "fullscreen"):
        cmd.append("-FullScreen")
    if _option_bool(profile.options, "view_only", "viewonly"):
        cmd.append("-ViewOnly")
    if _option_bool(profile.options, "shared"):
        cmd.append("-Shared")
    geometry = _option(profile.options, "geometry", "resolution")
    if geometry:
        cmd.extend(["-geometry", _geometry(geometry, "vnc geometry")])
    password_file = _option(profile.options, "password_file", "passwd_file")
    if password_file:
        cmd.extend(["-passwd", safe.path_arg(password_file, "vnc password_file")])
    encoding = _option(profile.options, "encoding")
    if encoding:
        cmd.extend(["-PreferredEncoding", _option_token(encoding, "vnc encoding")])
    quality = _option_bounded_int(profile.options, "quality", minimum=0, maximum=9)
    if quality is not None:
        cmd.extend(["-QualityLevel", str(quality)])
    compression = _option_bounded_int(profile.options, "compression", minimum=0, maximum=9)
    if compression is not None:
        cmd.extend(["-CompressLevel", str(compression)])
    cmd.append(f"{host}:{port}")
    return LaunchPlan("vnc", cmd, [])


def _build_spice(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    port = _port(profile, "spice")
    executable = _first_available(["remote-viewer", "virt-viewer"]) or "remote-viewer"
    cmd = [executable]
    if _option_bool(profile.options, "fullscreen"):
        cmd.append("--full-screen")
    title = _option(profile.options, "title")
    if title:
        cmd.extend(["--title", safe.clean_text(title, "spice title")])
    zoom = _option_bounded_int(profile.options, "zoom", minimum=10, maximum=400)
    if zoom is not None:
        cmd.append(f"--zoom={zoom}")
    audio = _option(profile.options, "audio")
    if audio is not None and not _bool_value(audio, "audio"):
        cmd.append("--spice-disable-audio")
    cmd.append(f"spice://{host}:{port}")
    return LaunchPlan("spice", cmd, ["Install virt-viewer for SPICE sessions."])


def _build_x2go(profile: Profile) -> LaunchPlan:
    cmd = ["x2goclient"]
    if profile.host:
        cmd.extend(["--server", _host(profile)])
    if profile.username:
        cmd.extend(["--user", safe.clean_text(profile.username, "username")])
    if profile.port:
        cmd.extend(["--ssh-port", str(_port(profile, "x2go"))])
    session = _option(profile.options, "session", "session_name")
    if session:
        cmd.extend(["--session", safe.clean_text(session, "x2go session")])
    session_type = _option(profile.options, "session_type")
    if session_type:
        cmd.extend(["--session-type", _option_token(session_type, "x2go session_type")])
    remote_command = _option(profile.options, "command", "remote_command")
    if remote_command:
        cmd.extend(["--command", safe.clean_text(remote_command, "x2go command")])
    geometry = _option(profile.options, "geometry", "resolution")
    if geometry:
        cmd.extend(["--geometry", _geometry(geometry, "x2go geometry")])
    if _option_bool(profile.options, "fullscreen"):
        cmd.append("--fullscreen")
    link = _option_enum(profile.options, "link", allowed={"adsl", "isdn", "lan", "modem", "wan"})
    if link:
        cmd.extend(["--link", link])
    pack = _option(profile.options, "pack")
    if pack:
        cmd.extend(["--pack", _option_token(pack, "x2go pack")])
    return LaunchPlan("x2go", cmd, ["Install x2goclient for X2Go sessions."])


def _build_xdmcp(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    executable = _first_available(["xnest", "Xorg", "Xquartz"]) or "xnest"
    return LaunchPlan("xdmcp", [executable, "-query", host], ["XDMCP requires a local X server and a remote XDMCP service."])


def _build_ica(profile: Profile) -> LaunchPlan:
    target = profile.path or profile.url or _host(profile)
    return LaunchPlan("ica", ["wfica", safe.path_arg(target, "ica target")], ["Requires Citrix Workspace/Receiver command-line client."])


def _build_url(profile: Profile, protocol: str) -> LaunchPlan:
    url = profile.url
    if not url:
        host = _host(profile)
        scheme = "http" if protocol in {"http", "www"} else "https"
        port = _port(profile, scheme)
        url = f"{scheme}://{host}:{port}"
    url = safe.url(url)
    if _is_windows():
        return LaunchPlan(protocol, ["rundll32.exe", "url.dll,FileProtocolHandler", url], ["Opens default browser."])
    if sys.platform == "darwin":
        return LaunchPlan(protocol, ["open", url], ["Opens default browser."])
    return LaunchPlan(protocol, ["xdg-open", url], ["Opens default browser."])


def _build_serial(profile: Profile) -> LaunchPlan:
    path = profile.path or profile.options.get("device")
    if not path:
        raise LauncherError("serial profile requires --path or option device=...")
    path = safe.path_arg(path, "serial device")
    baud, data_bits, parity_putty, parity_picocom, stop_bits, flow_putty, flow_picocom = _serial_config(profile.options)
    if _is_windows():
        sercfg = f"{baud},{data_bits},{parity_putty},{stop_bits},{flow_putty}"
        return LaunchPlan("serial", ["putty", "-serial", path, "-sercfg", sercfg], ["Install PuTTY for serial sessions on Windows."])
    executable = _first_available(["picocom", "screen", "cu"]) or "screen"
    if executable == "picocom":
        return LaunchPlan(
            "serial",
            [
                "picocom",
                "--baud",
                baud,
                "--databits",
                data_bits,
                "--parity",
                parity_picocom,
                "--stopbits",
                stop_bits,
                "--flow",
                flow_picocom,
                path,
            ],
            [],
        )
    notes = []
    if (data_bits, parity_putty, stop_bits, flow_putty) != ("8", "n", "1", "N"):
        notes.append("screen/cu launchers ignore advanced serial data/parity/stop/flow settings; install picocom for full option mapping.")
    if executable == "cu":
        return LaunchPlan("serial", ["cu", "-l", path, "-s", baud], notes)
    return LaunchPlan("serial", ["screen", path, baud], notes)


def _host(profile: Profile) -> str:
    if not profile.host:
        raise LauncherError(f"{profile.protocol} profile requires host")
    return safe.host(profile.host, f"{profile.protocol} host")


def _target(profile: Profile, host: str) -> str:
    if not profile.username:
        return host
    username = safe.option_value(profile.username, "username")
    return f"{username}@{host}"


def _port(profile: Profile, protocol: str, *, required: bool = False) -> int:
    value = profile.port
    if value is None and not required:
        value = DEFAULT_PORTS[protocol]
    return safe.port(value, f"{protocol} port")


def _validate_proxy_jump(value: str) -> str:
    proxy_jump = safe.option_value(value, "proxy_jump")
    for hop in proxy_jump.split(","):
        safe.option_value(hop, "proxy_jump hop")
        if any(char.isspace() for char in hop):
            raise LauncherError("proxy_jump hops must not contain whitespace")
    return proxy_jump


def _baud(value: str) -> str:
    baud = safe.clean_text(value, "serial baud")
    if not baud.isdigit() or int(baud) <= 0:
        raise LauncherError("serial baud must be a positive integer")
    return baud


def _option(options: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = options.get(name)
        if value is not None and str(value) != "":
            return str(value)
    return None


def _bool_value(value: str, label: str) -> bool:
    normalized = safe.clean_text(value, label).strip().lower()
    if normalized in {"1", "enabled", "on", "true", "yes"}:
        return True
    if normalized in {"0", "disabled", "false", "no", "off"}:
        return False
    raise LauncherError(f"{label} must be true or false")


def _option_bool(options: Mapping[str, str], *names: str, default: bool = False) -> bool:
    value = _option(options, *names)
    if value is None:
        return default
    return _bool_value(value, names[0])


def _option_positive_int(options: Mapping[str, str], *names: str) -> int | None:
    value = _option(options, *names)
    if value is None:
        return None
    return _positive_int_value(value, names[0])


def _option_bounded_int(options: Mapping[str, str], *names: str, minimum: int, maximum: int) -> int | None:
    value = _option(options, *names)
    if value is None:
        return None
    number = _positive_int_value(value, names[0])
    if number < minimum or number > maximum:
        raise LauncherError(f"{names[0]} must be between {minimum} and {maximum}")
    return number


def _positive_int_value(value: str, label: str) -> int:
    text = safe.clean_text(value, label)
    if not text.isdigit() or int(text) <= 0:
        raise LauncherError(f"{label} must be a positive integer")
    return int(text)


def _option_enum(options: Mapping[str, str], *names: str, allowed: set[str]) -> str | None:
    value = _option(options, *names)
    if value is None:
        return None
    normalized = safe.clean_text(value, names[0]).strip().lower()
    if normalized not in allowed:
        raise LauncherError(f"{names[0]} must be one of: {', '.join(sorted(allowed))}")
    return normalized


def _validate_ssh_algorithm_override(options: Mapping[str, str], option_name: str, value: str) -> None:
    weak_algorithms = WEAK_SSH_ALGORITHMS_BY_OPTION.get(option_name, frozenset())
    requested_weak = sorted(
        token for token in _ssh_algorithm_tokens(value) if token.lower() in weak_algorithms
    )
    if requested_weak and not _legacy_crypto_enabled(options):
        algorithms = ", ".join(requested_weak)
        raise LauncherError(
            f"{option_name} contains legacy SSH algorithm(s): {algorithms}. "
            "Use modern SSH algorithms by default, or set legacy_target=windows-xp-32 "
            "or windows-xp-64 plus allow_legacy_crypto=true for an isolated legacy profile."
        )


def _ssh_algorithm_tokens(value: str) -> list[str]:
    text = safe.option_value(value, "ssh algorithm list")
    tokens: list[str] = []
    for item in text.split(","):
        token = item.strip().lstrip("+-^")
        if token:
            tokens.append(token)
    return tokens


def _legacy_crypto_enabled(options: Mapping[str, str]) -> bool:
    return _is_windows_xp_legacy_target(options) and _option_bool(options, *LEGACY_CRYPTO_OPT_IN_OPTIONS)


def _require_legacy_rdp_security_opt_in(options: Mapping[str, str]) -> None:
    if _is_windows_xp_legacy_target(options) and _option_bool(options, *LEGACY_RDP_SECURITY_OPT_IN_OPTIONS):
        return
    raise LauncherError(
        "RDP security=rdp is disabled by default. Use security=nla or security=tls, "
        "or set legacy_target=windows-xp-32/windows-xp-64 and "
        "allow_legacy_rdp_security=true for an isolated XP remote target."
    )


def _is_windows_xp_legacy_target(options: Mapping[str, str]) -> bool:
    target = _option(options, *LEGACY_TARGET_OPTIONS)
    if target is None:
        return False
    return safe.clean_text(target, "legacy_target").strip().lower() in WINDOWS_XP_LEGACY_TARGETS


def _option_token(value: str, label: str) -> str:
    text = safe.option_value(value, label)
    if any(char.isspace() for char in text):
        raise LauncherError(f"{label} must not contain whitespace")
    return text


def _geometry(value: str, label: str) -> str:
    text = safe.clean_text(value, label).lower()
    if "x" not in text:
        raise LauncherError(f"{label} must use WIDTHxHEIGHT")
    width_text, height_text = text.split("x", 1)
    width = _positive_int_value(width_text, f"{label} width")
    height = _positive_int_value(height_text, f"{label} height")
    if width > 16384 or height > 16384:
        raise LauncherError(f"{label} dimensions must be 16384 or smaller")
    return f"{width}x{height}"


def _rdp_dimension_args(options: Mapping[str, str]) -> list[str]:
    geometry = _option(options, "geometry", "resolution")
    width = _option_bounded_int(options, "width", minimum=1, maximum=16384)
    height = _option_bounded_int(options, "height", minimum=1, maximum=16384)
    if geometry and (width is not None or height is not None):
        raise LauncherError("rdp geometry cannot be combined with width/height")
    if geometry:
        width_text, height_text = _geometry(geometry, "rdp geometry").split("x", 1)
        return [f"/w:{width_text}", f"/h:{height_text}"]
    if width is None and height is None:
        return []
    if width is None or height is None:
        raise LauncherError("rdp width and height must be set together")
    return [f"/w:{width}", f"/h:{height}"]


def _rdp_drive(value: str) -> str:
    name, separator, path = safe.clean_text(value, "rdp drive").partition(",")
    if not separator:
        raise LauncherError("rdp drive must use name,path")
    name = _option_token(name, "rdp drive name")
    return f"{name},{safe.path_arg(path, 'rdp drive path')}"


def _mosh_port(value: str) -> str:
    text = safe.clean_text(value, "mosh_port")
    parts = text.split(":", 1)
    start = _positive_int_value(parts[0], "mosh_port start")
    if start > 65535:
        raise LauncherError("mosh_port start must be between 1 and 65535")
    if len(parts) == 1:
        return str(start)
    end = _positive_int_value(parts[1], "mosh_port end")
    if end > 65535 or end < start:
        raise LauncherError("mosh_port range must be between 1 and 65535 and in ascending order")
    return f"{start}:{end}"


def _serial_config(options: Mapping[str, str]) -> tuple[str, str, str, str, str, str, str]:
    baud = _baud(_option(options, "baud") or "115200")
    data_bits = str(_option_bounded_int(options, "data_bits", "databits", minimum=5, maximum=8) or 8)
    parity_putty, parity_picocom = _serial_parity(_option(options, "parity") or "none")
    stop_bits = _serial_stop_bits(_option(options, "stop_bits", "stopbits") or "1")
    flow_putty, flow_picocom = _serial_flow(_option(options, "flow", "flow_control") or "none")
    return baud, data_bits, parity_putty, parity_picocom, stop_bits, flow_putty, flow_picocom


def _serial_parity(value: str) -> tuple[str, str]:
    normalized = safe.clean_text(value, "serial parity").strip().lower()
    mapping = {
        "even": ("e", "e"),
        "e": ("e", "e"),
        "mark": ("m", "m"),
        "m": ("m", "m"),
        "none": ("n", "n"),
        "n": ("n", "n"),
        "odd": ("o", "o"),
        "o": ("o", "o"),
        "space": ("s", "s"),
        "s": ("s", "s"),
    }
    if normalized not in mapping:
        raise LauncherError("serial parity must be one of: none, even, odd, mark, space")
    return mapping[normalized]


def _serial_stop_bits(value: str) -> str:
    normalized = safe.clean_text(value, "serial stop_bits").strip()
    if normalized not in {"1", "2"}:
        raise LauncherError("serial stop_bits must be 1 or 2")
    return normalized


def _serial_flow(value: str) -> tuple[str, str]:
    normalized = safe.clean_text(value, "serial flow").strip().lower()
    mapping = {
        "dsrdtr": ("D", "h"),
        "dtr": ("D", "h"),
        "hardware": ("R", "h"),
        "none": ("N", "n"),
        "n": ("N", "n"),
        "rtscts": ("R", "h"),
        "xonxoff": ("X", "x"),
        "x": ("X", "x"),
    }
    if normalized not in mapping:
        raise LauncherError("serial flow must be one of: none, xonxoff, rtscts, dsrdtr")
    return mapping[normalized]


def _first_available(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return None


def _is_windows() -> bool:
    return platform.system().lower() == "windows"

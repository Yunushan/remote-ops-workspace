# Protocol Adapters

| Protocol | Default adapter | External client examples |
|---|---|---|
| SSH | OpenSSH | `ssh` |
| SFTP | OpenSSH + file browser commands | `sftp`, `row files` |
| SCP | OpenSSH | `scp` |
| Mosh | Mosh | `mosh` |
| RDP | MSTSC/FreeRDP | `mstsc`, `xfreerdp`, `wlfreerdp` |
| VNC | VNC viewer | `vncviewer`, TigerVNC, RealVNC |
| SPICE | virt-viewer | `remote-viewer` |
| X2Go | x2goclient | `x2goclient` |
| XDMCP | X server tooling | `xnest`, `Xorg`, XQuartz, VcXsrv |
| ICA | Citrix Workspace | `wfica` |
| Telnet | telnet | `telnet`, PuTTY fallback |
| rlogin | rlogin | `rlogin` |
| rsh | rsh | `rsh` |
| HTTP/HTTPS | Default browser | `xdg-open`, `open`, `rundll32.exe url.dll,FileProtocolHandler` |
| Raw socket | Netcat | `nc`, `ncat`, `netcat` |
| Serial | screen/cu/PuTTY | `screen`, `cu`, `putty` |

Always verify generated commands with:

```bash
row connect PROFILE --dry-run
```

## Protocol options

Profiles accept repeatable `--option key=value` entries. The launcher maps supported
keys into validated argv entries for the native client; secrets such as passwords are
intentionally not emitted on the command line.

| Protocol | Supported options |
|---|---|
| SSH/SFTP/SCP | `compression=true`, `connect_timeout=10`, `keepalive_interval=30`, `keepalive_count=3`, `strict_host_key_checking=accept-new`, `user_known_hosts_file=/path/known_hosts`, `log_level=ERROR`, `ciphers=...`, `host_key_algorithms=...`, `kex_algorithms=...`, `macs=...`, `proxy_jump=bastion`, `proxy_command=...` with `allow_unsafe_proxy_command=true`, `agent_forward=true` or `forward_agent=true` for SSH |
| Mosh | SSH handoff options above, plus `mosh_port=60000:61000`, `mosh_server=mosh-server`, `predict=adaptive|always|never|experimental`, `bind_server=ssh|any|IP` |
| RDP | `geometry=1600x900` or `width=1600` and `height=900`, `fullscreen=true`, `admin=true`, `multimon=true`, `span=true`, `prompt=true`, `domain=LAB`, `dynamic_resolution=false`, `cert_ignore=true`, `cert=ignore|deny|tofu|name`, `security=rdp|tls|nla|ext`, `clipboard=false`, `drive=name,path`, `scale=140`, `audio=true`, `microphone=true`, `fonts=true`, `themes=true`, `gfx=true` |
| VNC | `fullscreen=true`, `view_only=true`, `shared=true`, `geometry=1280x720`, `password_file=/path/passwd`, `encoding=tight`, `quality=0..9`, `compression=0..9` |
| SPICE | `fullscreen=true`, `title=Lab VM`, `zoom=125`, `audio=false` |
| X2Go | `session=name`, `session_type=XFCE`, `command=XFCE`, `geometry=1440x900`, `fullscreen=true`, `link=modem|isdn|adsl|wan|lan`, `pack=16m-jpeg` |
| Serial | `baud=9600`, `data_bits=7`, `parity=none|even|odd|mark|space`, `stop_bits=1|2`, `flow=none|xonxoff|rtscts|dsrdtr`; Windows maps these to PuTTY `-sercfg`, Unix maps them fully through `picocom` when available |

Examples:

```bash
row profile add --name edge --protocol ssh --host 192.0.2.10 --username admin \
  --option compression=true --option keepalive_interval=30 \
  --option strict_host_key_checking=accept-new --option proxy_jump=bastion

row profile add --name desktop --protocol rdp --host 192.0.2.20 \
  --option geometry=1600x900 --option cert_ignore=true --option clipboard=false

row profile add --name console --protocol serial --path COM3 \
  --option baud=9600 --option data_bits=7 --option parity=even \
  --option stop_bits=2 --option flow=rtscts
```

SFTP profiles also support file-browser actions:

```bash
row files open PROFILE --dry-run
row files ls PROFILE /var/log --dry-run
row files get PROFILE /etc/hosts --local ./hosts.copy --dry-run
row files put PROFILE ./build.tar.gz --remote /tmp/build.tar.gz --dry-run
row files queue PROFILE --op "get /etc/hosts ./hosts.copy" --op "put ./build.tar.gz /tmp/build.tar.gz" --dry-run
row files preview-local ./README.md --json
row files preview-remote PROFILE /var/log --dry-run
```

See [`FILE_TRANSFER.md`](FILE_TRANSFER.md) for queued transfer syntax and preview behavior.

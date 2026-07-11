# Protocol Adapters

| Protocol | Default adapter | External client examples |
|---|---|---|
| SSH | OpenSSH | `ssh` |
| SSHv1 legacy | OpenSSH-compatible legacy mode | `ssh -1` only when the profile also sets `allow_insecure_sshv1=true`, `legacy_target=windows-xp-32` or `windows-xp-64`, and `allow_legacy_crypto=true`; the installed client must still support protocol v1 |
| SFTP | OpenSSH + file browser commands | `sftp`, `row files` |
| SCP | OpenSSH | `scp` |
| Mosh | Mosh | `mosh` |
| Kubernetes exec | kubectl | `kubectl exec --stdin --tty` |
| WinRM | PowerShell remoting | `pwsh`, `powershell.exe` |
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

Imported SSHv1 profiles are preserved as `ssh1`, but they are not launchable
until an operator edits the profile and adds `allow_insecure_sshv1=true`,
`legacy_target=windows-xp-32` or `windows-xp-64`, and
`allow_legacy_crypto=true`.

Generic XP labels such as `xp`, `winxp` and `windows-xp` are intentionally
rejected for legacy SSH/RDP opt-ins, and `legacy_platform` is not a supported
alias. Use the architecture-specific `legacy_target=windows-xp-32` or
`legacy_target=windows-xp-64` value so the insecure exception stays tied to a
known XP remote-target boundary.

`row doctor` reports `ssh1` and `sshv1` as `legacy-insecure-opt-in` rather
than normally available. A present `ssh` executable only means the external
client exists; it does not prove that protocol v1 negotiation still works.

Managed X server runtime status is available with:

```bash
row x11 status --display :0
row x11 status --display :0 --json
row x11 package-status --json
row x11 bundle-runtime --out dist/xserver --runtime xvfb --source vendor/xserver/linux/bin/Xvfb --system linux --json
row x11 start --display :1 --dry-run
row x11 smoke --display :1 --out artifacts/x11-smoke.json --json
row x11 evidence-verify --evidence artifacts/moba-xserver-release.json --assets-dir artifacts --json
row x11 stop --json
```

The status workflow discovers VcXsrv, XLaunch, Xming, XQuartz, Xorg, Xvfb,
Xephyr and Xnest candidates, reports whether the requested display appears to
be in use, exposes the planned `DISPLAY` value and lists expected X extension
families such as GLX/OpenGL, RANDR, RENDER, Composite, XFixes, XInput,
XKeyboard and XDMCP. `row x11 start` refuses to start on a display that appears
occupied; choose another display such as `:1` for a second local runtime. A
real start records PID, display, runtime and command state in the ROW data
directory so `row x11 status` and `row x11 stop` can report and control the
managed process. `row x11 smoke` runs `xdpyinfo`, `xset`, `xprop` or a custom
`--probe-command` against the selected display and can write evidence JSON with
a SHA-256 digest. A missing runtime or missing probe command is reported as a
failed/unavailable smoke result instead of being treated as success.

`row x11 package-status` scans packaged runtime roots before host `PATH`
adapters. `row x11 bundle-runtime` copies a supplied release X server binary
into the packaged layout and writes a SHA-256-bound `xserver-runtime.json`
manifest. A release can point `ROW_XSERVER_RUNTIME_DIR` at that shipped runtime
tree, or pass `--root`, and ROW will prefer packaged VcXsrv/Xming/XQuartz/Xorg
family binaries when present. `row x11 evidence-verify` checks the stricter
MobaXterm-style release evidence schema `row.moba-xserver.release-evidence.v1`:
the runtime must be bundled or packaged, runtime/smoke/screenshot artifacts
must stay inside the assets directory, SHA-256 hashes must match, the smoke
probe must pass, and a real X11-forwarded GUI app must report `status=passed`
with `window_observed=true`.

## Protocol options

Profiles accept repeatable `--option key=value` entries. The launcher maps supported
keys into validated argv entries for the native client; secrets such as passwords are
intentionally not emitted on the command line.

| Protocol | Supported options |
|---|---|
| SSH/SFTP/SCP | `compression=true`, `connect_timeout=10`, `keepalive_interval=30`, `keepalive_count=3`, `strict_host_key_checking=accept-new`, `user_known_hosts_file=/path/known_hosts`, `log_level=ERROR`, `certificate_file=/path/id-cert.pub`, `pkcs11_provider=/path/opensc-pkcs11.so`, `smartcard_provider=microsoft-capi`, `identity_agent=/path/agent.sock`, `security_key_provider=internal`, `ciphers=...`, `host_key_algorithms=...`, `kex_algorithms=...`, `macs=...`, `proxy_jump=bastion`, `proxy_command=...` with `allow_unsafe_proxy_command=true`, `agent_forward=true` or `forward_agent=true` for SSH. Known legacy algorithms such as `ssh-rsa`, `ssh-dss`, `diffie-hellman-group1-sha1`, CBC/3DES/RC4 ciphers and SHA-1 MACs require `legacy_target=windows-xp-32` or `windows-xp-64` plus `allow_legacy_crypto=true`. |
| SSHv1 legacy | Requires `--protocol ssh1` or `--protocol sshv1`, `--option allow_insecure_sshv1=true`, `--option legacy_target=windows-xp-32` or `windows-xp-64`, and `--option allow_legacy_crypto=true` before the launcher will add `-1`. This is insecure, obsolete, and only works with clients that still include SSH protocol v1 support. |
| Mosh | SSH handoff options above, plus `mosh_port=60000:61000`, `mosh_server=mosh-server`, `predict=adaptive|always|never|experimental`, `bind_server=ssh|any|IP` |
| Kubernetes exec | Profile host is the pod; `namespace=default`, `container=api`, `context=prod`, `kubeconfig=/path/config`, `shell=/bin/bash`. The profile `command` field, when present, is used as the post-`--` command. |
| WinRM | `transport=https` is the default and uses port 5986. An optional profile username is passed only to PowerShell's interactive `Get-Credential` prompt; `credential_ref` is never put in argv. `transport=http` is rejected unless `legacy_target=windows-xp-32` or `windows-xp-64` and `allow_insecure_winrm_http=true` are both set for an isolated legacy target. |
| RDP | `geometry=1600x900` or `width=1600` and `height=900`, `fullscreen=true`, `admin=true`, `multimon=true`, `span=true`, `prompt=true`, `domain=LAB`, `dynamic_resolution=false`, `cert_ignore=true`, `cert=ignore|deny|tofu|name`, `security=tls|nla|ext`, `security=rdp` only with `legacy_target=windows-xp-32` or `windows-xp-64` plus `allow_legacy_rdp_security=true`, `clipboard=false`, `drive=name,path`, `scale=140`, `audio=true`, `microphone=true`, `fonts=true`, `themes=true`, `gfx=true` |
| VNC | `fullscreen=true`, `view_only=true`, `shared=true`, `geometry=1280x720`, `password_file=/path/passwd`, `encoding=tight`, `quality=0..9`, `compression=0..9` |
| SPICE | `fullscreen=true`, `title=Lab VM`, `zoom=125`, `audio=false` |
| X2Go | `session=name`, `session_type=XFCE`, `command=XFCE`, `geometry=1440x900`, `fullscreen=true`, `link=modem|isdn|adsl|wan|lan`, `pack=16m-jpeg` |
| Serial | `baud=9600`, `data_bits=7`, `parity=none|even|odd|mark|space`, `stop_bits=1|2`, `flow=none|xonxoff|rtscts|dsrdtr`; Windows maps these to PuTTY `-sercfg`, Unix maps them fully through `picocom` when available |

Examples:

```bash
row profile add --name edge --protocol ssh --host ssh.example.invalid --username admin \
  --option compression=true --option keepalive_interval=30 \
  --option strict_host_key_checking=accept-new --option proxy_jump=bastion

row profile add --name smartcard-edge --protocol ssh --host ssh.example.invalid --username admin \
  --option smartcard_auth=true --option smartcard_provider=microsoft-capi \
  --option pkcs11_provider=/usr/lib/opensc-pkcs11.so \
  --option certificate_file=/home/admin/.ssh/id_ed25519-cert.pub

row profile add --name legacy-router --protocol ssh1 --host legacy-router.example.invalid --username admin \
  --option allow_insecure_sshv1=true --option legacy_target=windows-xp-32 \
  --option allow_legacy_crypto=true

row profile add --name desktop --protocol rdp --host rdp.example.invalid \
  --option geometry=1600x900 --option cert_ignore=true --option clipboard=false

row profile add --name console --protocol serial --path COM3 \
  --option baud=9600 --option data_bits=7 --option parity=even \
  --option stop_bits=2 --option flow=rtscts

row profile add --name api-pod --protocol kubernetes --host api-0 \
  --option namespace=operations --option container=api --option context=production

row profile add --name windows-admin --protocol winrm --host winrm.example.invalid --username Administrator
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

# Protocol Adapters

| Protocol | Default adapter | External client examples |
|---|---|---|
| SSH | OpenSSH | `ssh` |
| SFTP | OpenSSH | `sftp` |
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
| HTTP/HTTPS | Default browser | `xdg-open`, `open`, `cmd /c start` |
| Raw socket | Netcat | `nc`, `ncat`, `netcat` |
| Serial | screen/cu/PuTTY | `screen`, `cu`, `putty` |

Always verify generated commands with:

```bash
row connect PROFILE --dry-run
```

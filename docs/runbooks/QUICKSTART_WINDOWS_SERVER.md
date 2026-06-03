# Quickstart: Windows Server

```powershell
git clone https://github.com/Yunushan/remote-ops-workspace.git
cd remote-ops-workspace
Set-ExecutionPolicy -Scope Process Bypass -Force
.\installers\install.ps1
row welcome
row doctor
row profile add --name localhost-rdp --protocol rdp --host 127.0.0.1 --username Administrator
row connect localhost-rdp --dry-run
```

Recommended optional tools:

- OpenSSH Client.
- PuTTY.
- VcXsrv.
- TigerVNC.

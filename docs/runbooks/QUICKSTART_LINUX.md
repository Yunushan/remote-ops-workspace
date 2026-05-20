# Quickstart: Linux

```bash
git clone https://github.com/YOUR-ORG/remote-ops-workspace.git
cd remote-ops-workspace
./installers/install.sh
row init
row doctor
row profile add --name lab --protocol ssh --host 192.0.2.10 --username admin
row connect lab --dry-run
```

Install optional clients with your package manager: `openssh-client`, `freerdp2-x11` or `freerdp`, `tigervnc-viewer`, `virt-viewer`, `x2goclient`, `mosh`, `screen`.

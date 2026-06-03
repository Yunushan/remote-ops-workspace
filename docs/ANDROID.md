# Android

Remote Ops Workspace supports Android through two practical routes:

1. **Web/PWA**: run the Web/PWA from any browser.
2. **Termux CLI**: use the Python CLI and OpenSSH adapters inside Termux.

## Termux setup

```bash
pkg update
pkg install python git openssh
python -m venv .venv
. .venv/bin/activate
pip install -e .
row init
row welcome
row profile add --name phone-ssh --protocol ssh --host ssh.example.invalid --username admin
row connect phone-ssh --dry-run
```

Native Android packaging can be added later through a mobile wrapper around the Web/PWA or a dedicated plugin layer.

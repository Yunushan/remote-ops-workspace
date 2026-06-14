# Android

Remote Ops Workspace supports Android through two practical routes:

1. **Web/PWA**: run the Web/PWA from any browser.
2. **Termux CLI**: use the Python CLI and OpenSSH adapters inside Termux.

## Supported and tested versions

The verified Android contract covers Android 12 through Android 16 (API 31-36)
for the Web/PWA path. CI runs the `android-emulator-web` job across API levels
31, 32, 33, 34, 35 and 36, opens the Web/PWA in the emulator, and uploads a
screenshot artifact.

The release target remains ARMv7 and ARM64 for Termux/Web packaging. The
emulator smoke uses x86_64 system images because that is the practical Android
emulator architecture on GitHub-hosted Ubuntu runners; architecture coverage is
verified by the Termux/Web release target metadata and package contract.

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

Native Android packaging can be added later through a mobile wrapper around the Web/PWA or a dedicated plugin layer. No APK is published.

CI validates the shared Android/iOS browser PWA contract through the `mobile-web` job and `tests/test_web_hardening.py`. It does not run a real Android device or publish an APK.

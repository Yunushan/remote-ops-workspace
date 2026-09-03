# v1.0.22

**Channel: unsigned preview.** Signing/notarization material was unavailable. Native installers are for testing only and must not be treated as trusted production artifacts. Use a signed release for production deployment.

## Included release families

- Source/Python: remote-ops-workspace-v1.0.22-source.zip, remote-ops-workspace-v1.0.22-windows.zip, remote-ops-workspace-v1.0.22-linux.tar.gz, remote-ops-workspace-v1.0.22-macos.tar.gz, remote-ops-workspace-v1.0.22-bsd.tar.gz, remote-ops-workspace-v1.0.22-solaris.tar.gz, remote-ops-workspace-v1.0.22-android-termux.tar.gz, remote-ops-workspace-v1.0.22-web-pwa.zip.
- Native jobs: windows-native, macos-native, linux-native.
- Every published file is validated against the release matrix and accompanied by SHA-256 checksums; the source/Python environment also includes an SBOM.

## Support boundaries

- The default release does not claim verified native-host readiness for Linux i386, Linux armhf, or Windows XP x86/x64.
- Protected platform evidence accepted for this source is 0/4 targets; missing: linux-i386, linux-armhf, windows-xp-native-x86, windows-xp-native-x64.
- Legacy XP compatibility remains isolated and opt-in; modern platform security defaults are not weakened.
- Strict MobaXterm parity evidence accepted for this source is 0/8 tracked articles.

## Verification

- Release page: https://github.com/Yunushan/remote-ops-workspace/releases/tag/v1.0.22
- Verify the source and release matrix with `python scripts/verify.py --quick --no-cli-smoke --release-tag v1.0.22`.
- For protected-platform promotion, run the evidence source-ref, accepted-record, release-asset, and remote byte-provenance gates documented in `docs/PLATFORM_SUPPORT.md`; do not substitute candidate builds for accepted host evidence.

This release note is generated from the checked-in release and evidence registries. It intentionally reports missing evidence instead of inferring support from a successful candidate build.

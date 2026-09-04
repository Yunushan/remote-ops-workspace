# iOS and iPadOS

Remote Ops Workspace supports iPhone and iPad through the static Web/PWA shell.

## Supported and tested versions

The verified iOS/iPadOS Web/PWA contract covers iOS/iPadOS 15 through 27.x.
CI validates the static PWA contract in the `mobile-web` job and runs the
`ios-simulator-web` job on the current GitHub macOS/Xcode runner. The simulator
job boots the available iOS runtime, opens the Web/PWA URL, and uploads a
screenshot artifact.

The `apple-27-validation` job runs on the GitHub-hosted `xcode-27` preview image.
It verifies Xcode 27 plus the macOS 27, iOS 27, and iOS simulator 27 SDKs, then
requires an exact iOS 27 simulator runtime for the live Web/PWA smoke. The
image uses a macOS 26 host with Xcode 27, so this is SDK and simulator-runtime
validation rather than a claim that GitHub provides a `macos-27` host label.

GitHub-hosted macOS runners do not provide every historical iOS simulator
runtime at once. Older iOS/iPadOS versions are covered by the compatibility
contract and static Web/PWA checks, while the live simulator smoke follows the
current Xcode runtime on the runner.

## Supported path

1. Build or download `remote-ops-workspace-v1.0.24-web-pwa.zip`.
2. Serve the extracted `apps/web` files from a trusted HTTPS origin or an internal portal.
3. Open the site from Safari or another trusted browser.
4. Use the browser's Add to Home Screen flow when an installed PWA-style launch icon is needed.

The Web/PWA shell is static. It does not require Python on the iOS device.

## Boundaries

- No native `.ipa` artifact is published.
- No App Store package is published.
- The Python CLI and PyQt6 desktop GUI are not supported as local iOS apps.
- Protocol rendering still depends on backend/API integration or external infrastructure exposed to the Web/PWA.

CI validates this as a mobile browser/PWA contract through the `mobile-web` job and `tests/test_web_hardening.py`.
The current-runtime simulator smoke is in the `ios-simulator-web` job, and the
exact iOS 27 smoke is in `apple-27-validation`.

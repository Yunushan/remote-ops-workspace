# Production Deployment

Remote Ops Workspace is an operator workstation application with an optional
static Web/PWA container. It is not a multi-tenant remote-desktop gateway or a
central credential service. Keep the browser API loopback-only; it is not
available when the web server binds to a public interface.

## Container Web/PWA

The checked-in Compose file is a localhost-only deployment for a reverse proxy
on the same host:

```sh
docker compose -f docker/compose.yaml up -d --build
```

The image is built from an explicit Docker allowlist. Do not replace the
`.dockerignore` with a broad build context: `ROW_HOME`, vaults, profiles,
private keys and support bundles must never enter an image layer.

Terminate TLS and enforce authentication at a managed reverse proxy before
exposing the service beyond localhost. Proxy only the static application and
`/healthz`; do not publish `row serve-web --api-token` because that API is
intentionally loopback-only. Configure uptime checks against `/healthz`, retain
proxy access logs according to your policy, and back up the named `/data`
volume with encryption at rest.

## Operational Go/No-Go

Before exposing the Web/PWA beyond localhost, record the managed reverse
proxy's TLS and authentication policy, an uptime check against `/healthz`, and
the encrypted backup location for the `remote-ops-data` volume. Perform and
record a restore drill in an isolated environment: restore a recent encrypted
volume backup, start the Compose stack, confirm `/healthz` responds through the
proxy, and confirm the restored data is the expected backup revision. A backup
job without a successful restore drill is not production recovery evidence.

Keep public Web/PWA exposure separate from the loopback browser API. The API
token must not be forwarded by a public proxy, and the static Web/PWA should
not be represented as a central credential, authorization, or session-control
service. Establish monitoring and incident ownership in the reverse-proxy or
endpoint-management platform that actually operates the public endpoint; this
repository does not provide a hosted operations control plane.

## Native Releases

Production tags run in the protected GitHub `release` environment. Configure
these environment secrets before creating a release:

- `ROW_WINDOWS_CERTIFICATE_BASE64`, `ROW_WINDOWS_CERTIFICATE_PASSWORD`, and
  `ROW_WINDOWS_TIMESTAMP_URL` for Authenticode signing and timestamping.
- `ROW_MACOS_CERTIFICATE_BASE64`, `ROW_MACOS_CERTIFICATE_PASSWORD`,
  `ROW_MACOS_SIGN_IDENTITY`, and `ROW_MACOS_INSTALLER_SIGN_IDENTITY` for
  Developer ID signing.
- `ROW_MACOS_NOTARY_KEY_BASE64`, `ROW_MACOS_NOTARY_KEY_ID`, and
  `ROW_MACOS_NOTARY_ISSUER` for Apple notarization and stapling.

The environment accepts only protected `main` dispatches and `v*` tags. Keep
that policy in place: `main` is required for the controlled evidence-promotion
dispatch, while version tags are required for automatic production publishing.

Every GitHub Action used by release, CI, and protected-evidence workflows is
commit-pinned and checked locally. The Web/PWA Python base image is also
pinned to an immutable multi-architecture OCI digest. Its Docker build pins
the Python build tooling from `requirements-release.txt` and disables isolated
build-backend resolution. Review and pin any new action, container base image,
or image-build dependency before adding it to production automation.

Before uploading a GitHub Release, the workflow creates a pinned
Sigstore/SLSA provenance attestation for every validated `release-assets` file.
The core and protected-promotion publish jobs receive only the attestation,
artifact-metadata, OIDC, release-write, and Actions-read permissions needed for
that operation. Consumers should verify a promoted release's GitHub
attestation as well as its installer signatures and SHA-256 checksums.

After downloading a release asset, verify its build provenance against the
specific release workflow before deployment:

```sh
gh attestation verify ./remote-ops-workspace-v<version>-linux-x86_64.AppImage \
  --repo Yunushan/remote-ops-workspace \
  --signer-workflow Yunushan/remote-ops-workspace/.github/workflows/release.yml
```

Use the matching local filename for any Windows, macOS, Linux, source, or
protected-platform asset. The command verifies the artifact digest, GitHub
repository identity, OIDC issuer, and SLSA provenance predicate; it does not
replace native installer signature verification or the SHA-256 sidecar check.

The source/Python release also includes
`remote-ops-workspace-v<version>-sbom.cdx.json`, a deterministic CycloneDX 1.5
inventory of the pinned environment that built the source and Python assets.
It is covered by the release manifest, SHA-256 sidecar, and GitHub attestation.
Its scope is deliberately limited to that source/Python environment; inspect
each native artifact's manifest, signature state, checksums, and provenance
attestation separately before deployment.

The repository-policy CI job also runs `pip-audit --strict` against the exact
release dependency pins. It uses the system trust store, so inspection remains
reliable on managed networks that add a trusted TLS interception certificate.
Dependabot tracks `pip`, GitHub Actions, and Docker updates weekly through
`.github/dependabot.yml`. Review dependency update pull requests through the
normal protected-branch policy; automated update tooling does not replace
release validation or platform signing.

The modern and legacy-wheel release profiles use the same pinned `build`,
`wheel`, and PyInstaller versions. Only cryptography is intentionally lower in
the legacy profile, because its x86 Windows and Intel macOS wheel availability
is independently constrained and guarded by the release-toolchain contract.

Tag-triggered releases fail before building any partial asset set unless both
the Windows signing and macOS signing/notarization secret sets are available in
the protected `release` environment. This prevents a successful-looking tag
run that silently omits signed desktop installers or a GitHub Release.

Each Windows and macOS native manifest records whether its artifacts are a
`production-signed` release or an `unsigned-preview`. The publish gate checks
that metadata against the preflight release channel before upload. A
production-signed Windows manifest must report verified, timestamped
Authenticode; a production-signed macOS manifest must report verified Developer
ID signing, notarization, and stapling. Preview metadata is deliberately not
promotion evidence.

`.github/workflows/codeql.yml` scans the Python application and
JavaScript/TypeScript Web/PWA sources on main-branch changes, pull requests,
and a weekly schedule. Its CodeQL revision is immutable-pinned and checked by
the normal workflow-pin verifier. Triage every resulting alert before release;
CodeQL complements, but does not replace, dependency auditing or runtime
security testing.

Manual evidence-only dispatches can report missing signing material and skip
release publication; they never publish unsigned native assets. Check the
Authenticode signatures, macOS Gatekeeper assessment, release checksums, and
the generated manifests before promoting a release. Checksums prove file
integrity only; they are not a substitute for platform signing.

An `UNSIGNED PREVIEW` is suitable only for controlled evaluation. It is not a
production release, even when checksums, SBOMs, installer smoke tests and
provenance attestations are present. Promote a desktop release only after the
protected signing environment is populated and its installer signatures and
notarization evidence have been verified.

## Updates and Dependencies

Enterprise update manifests use Ed25519 public keys only. Generate and protect
the private key outside deployed clients; distribute only the base64-encoded
32-byte public key as `ed25519:<public-key>`. The current command validates a
staged manifest and assets. It does not fetch, install, or roll back updates,
so use your existing endpoint-management system for staged deployment and
rollback until a managed updater is introduced.

RDP, VNC, X2Go, SPICE, serial, and other protocol sessions delegate to native
system clients. Treat `row doctor` as a post-install preflight, then deploy the
approved clients, versions, certificates, and host-key policy through your OS
package-management or endpoint-management platform. A green package install is
not evidence that every protocol client is installed or usable.

## Team Data

The directory team-sync backend is a file-backed metadata exchange intended
for a single trusted shared filesystem. It does not provide identity,
authorization, audit retention, high availability, distributed stale-lock
recovery, or a credential store. Do not use it as an enterprise source of
truth; use a managed configuration service for concurrent teams.

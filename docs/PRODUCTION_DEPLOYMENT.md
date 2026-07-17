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

Every GitHub Action used by release, CI, and protected-evidence workflows is
commit-pinned and checked locally. The Web/PWA Python base image is also
pinned to an immutable multi-architecture OCI digest. Its Docker build pins
the Python build tooling from `requirements-release.txt` and disables isolated
build-backend resolution. Review and pin any new action, container base image,
or image-build dependency before adding it to production automation.

The release jobs fail before upload if the required material is absent. Check
the Authenticode signatures, macOS Gatekeeper assessment, release checksums,
and the generated manifests before promoting a release. Checksums prove file
integrity only; they are not a substitute for platform signing.

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

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
volume with encryption at rest. The checked-in Compose service uses Docker's
local log driver with bounded rotation; forward or retain proxy and container
logs in your operating environment according to its incident and compliance
requirements.

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

### Automated Application-Volume Recovery Evidence

CI runs a destructive recovery drill against an isolated Compose project. The
drill writes a source-bound revision marker through the non-root application
container, stops the service, creates and validates a backup archive, writes a
post-backup sentinel, removes the original named volume, creates a fresh
Compose-labeled volume, restores the archive, and proves that the expected
revision survived while the sentinel did not. It then restarts the hardened
container and requires `/healthz` to return HTTP 200 before and after recovery.

The runner retains only a sanitized JSON record; it never uploads the backup
payload or `/data` contents. The record binds the repository, source SHA,
workflow run URL and run attempt, backup digest, immutable image ID, health
responses, container hardening, destructive replacement and cleanup result.
Download a `web-recovery-evidence-<sha>-<attempt>` CI artifact and validate it
with:

```sh
python scripts/check_web_recovery_evidence.py \
  --evidence web-recovery-evidence.json \
  --repository <owner>/<repo> \
  --source-sha <40-character-git-sha> \
  --workflow-run-url <github-actions-run-url> \
  --run-attempt <positive-run-attempt>
```

This automated check proves the checked-in application's named-volume recovery
mechanics. It does not prove an operator's encrypted backup location, managed
reverse proxy, TLS/authentication policy, monitoring route, retention policy,
recovery time objective, or incident ownership. Production go/no-go still
requires a recorded site-specific restore through those operated controls.

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
  --signer-workflow Yunushan/remote-ops-workspace/.github/workflows/release-promotion.yml
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

All vault-capable release profiles require maintained `cryptography==50.0.1`,
and encrypted OpenSSH key generation additionally requires `bcrypt==5.0.0`.
Intel macOS builds cryptography from source. The Windows x86 compatibility
profile uses the same pinned `build`, `wheel`, and PyInstaller versions but
excludes bcrypt, cryptography, and truststore because no reviewed maintained
source-build chain exists for that architecture. Its release smoke requires
affected security commands to fail closed; no known-vulnerable fallback is
packaged.

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

Modern release builds install complete, target-specific dependency locks with
`pip --require-hashes`. Where a reviewed source build is required, its build
backends come from a separately hashed subset of the final lock, and automatic
build isolation is disabled. Validate the input receipt and workflow wiring with
`python scripts/check_release_dependency_locks.py`. To regenerate the locks, use
the exact resolver version in `configs/release_dependency_locks.json`:

```sh
python scripts/lock_release_dependencies.py --uv /path/to/pinned/uv --system-certs
```

Review regenerated dependency/hash changes and verify installation on each native
builder before publishing. The resolver receipt proves dependency inputs; the
production approval separately binds components actually present in every package.

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

## Offline Workstation Recovery

`row export` exports profiles. To retain the complete workstation state, use
the encrypted offline workspace backup with the security extra installed. Close
all other ROW GUI, Web and CLI processes and stop managed server/X11 helpers
before acknowledging `--offline`; the backup does not suspend active writers.
It acquires all five known store locks and the locks of managed runtime records
that already exist, then rejects detected inventory changes. This does not
provide an online snapshot guarantee.

```sh
row workspace backup --out /secure-backups/workstation.rowbak --offline
row workspace restore --backup /secure-backups/workstation.rowbak --destination /private/workstation-restored --offline
```

Both commands use the current `ROW_HOME`; the restore destination must be a new
direct sibling of that home. Prompts keep the backup passphrase out of command
arguments. For automated recovery drills, `--passphrase-env ENVIRONMENT_NAME`
reads a separately provisioned secret variable. Retain that passphrase securely;
the encrypted archive cannot be recovered without it.

The versioned authenticated archive preserves raw profiles and group defaults,
vault ciphertext, layouts and splitter sizes, snippets, macros, browser settings,
unknown regular plugin state and empty directories. Known advisory lock files and recognized
ordinary write staging files are omitted. Verified predecessor recovery copies
are retained. Archives are bounded to 64 MiB of file data and 10,000 entries and
reject linked, reparse, special, hard-linked and nonportable paths. POSIX restore
permissions are owner-only, preserving the owner executable bit. Windows privacy
requires an operator-secured destination parent DACL so the new staging and
restored directories inherit private access; `chmod` does not verify that ACL.
The result explicitly reports `windows_acl_verified: false`.
External identity keys, served roots, machine policy and host runtimes remain
separate recovery dependencies.

Restore validates the entire authenticated manifest before staging a new home,
then verifies the restored bytes before installing that directory. The original
home is retained. Inspect the restored stores and decrypt a known vault item in
an isolated drill before selecting the restored `ROW_HOME` for normal use. Keep
the archive private and encrypted at rest; CI retains only sanitized recovery
results, never archive payloads or passphrases.

For a rollback to an older release, restore the snapshot taken before the
upgrade. Current vault writes migrate earlier vaults to format v3; v1.0.24 cannot
read that newer format. Reinstalling an older executable over a newly written
vault is insufficient. Native installer upgrade and rollback must additionally
be verified on the actual operated host; released-wheel compatibility evidence
does not prove native installer lifecycle or platform trust.

Managed shutdown binds a saved process to its native creation identity. Windows
uses the same verified process handle for termination and exit confirmation;
Linux uses a verified process descriptor. Stale or unverifiable legacy records
are refused. Start and stop serialize changes to each lifecycle record; a repeat
start refuses an active or ambiguous record before changing authorization files
or launching another child. A `started` record confirms child ownership;
listener readiness requires the separate service or X11 probe. Other POSIX hosts can stop retained, unreaped children in the
running GUI; separate-process shutdown requires a supported native mechanism
or the host's process manager. A failed shutdown retains the lifecycle record
and prevents an offline snapshot of that active or ambiguous helper.
Owned POSIX child management requires default `SIGCHLD` handling and reaping
through the retained `Popen` object. Cleanup uses a bounded shutdown deadline
and refuses uncertain ownership.

## Team Data

Private-state writes retain a secured predecessor while committing a replacement.
If permissions cannot be verified after replacement, the writer restores the
previous bytes and reports failure. If the OS prevents recovery, the error names
the verified `.<name>.rollback.*.tmp` copy to retain for operator recovery. Stop
writers before investigating, preserve that copy, and verify its permissions and
contents before restoring it. A recovery error never indicates a successful save.

The directory team-sync backend is a file-backed metadata exchange intended
for a single trusted shared filesystem. It does not provide identity,
authorization, audit retention, high availability, distributed stale-lock
recovery, or a credential store. Do not use it as an enterprise source of
truth; use a managed configuration service for concurrent teams.
On POSIX, pre-provision the root and its parents, with the root configured as a
non-world-accessible, user/group-rwx setgid directory owned by the intended
team group. The application creates no POSIX path components, will not select a
GID, and rejects records or locks that do not inherit that group.

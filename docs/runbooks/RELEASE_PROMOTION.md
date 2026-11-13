# Runbook: Release promotion and artifact verification

Authoritative promotion mechanics live in
[`../PLATFORM_PROMOTION_RUNBOOK.md`](../PLATFORM_PROMOTION_RUNBOOK.md) and the
gate definition in [`../PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md).
This runbook is the operator summary; it does not replace those documents.

## States

- `release.yml` builds and seals a **release candidate**. It never publishes.
- `release-promotion.yml` performs the independent, tag-and-SHA-bound audit and
  is the only path that creates a GitHub Release.

An unsigned preview build is explicitly labeled and is not a production
promotion target.

## Promotion checks

1. Confirm the exact source digest, not just the tag:

   ```bash
   git rev-parse HEAD
   python scripts/check_python315_ci_evidence.py --repository <owner/repo> --branch main --sha <release-sha>
   ```

2. Confirm maturity, provenance and repository governance:

   ```bash
   python scripts/check_release_maturity.py --release-tag <tag>
   python scripts/check_repository_governance.py --repository <owner/repo> --branch main --sha <release-sha> --release-tag <tag>
   ```

3. Verify the protected-platform registry from the signed compliance bundle.

   ```bash
   python scripts/check_platform_verified_evidence.py --registry "<signed-registry.json>" --require-goal-targets --require-review-bundles --release-tag "<tag>"
   ```

4. After publication, finalize the MobaXterm records using the downloaded
   release assets and merge the reviewed registry into protected `main`.
   Run the [aggregate gate with the required release inputs](../PRODUCTION_READINESS.md#final-promotion-sequence)
   from the tagged checkout and require `production readiness: 100/100 gates passed`.

## Capture the signed tag ruleset proof

The independent governance auditor runs this command on their own system.
Their Ed25519 public key must already be enrolled in the tagged release
policy. Set `GH_TOKEN` in the auditor's environment to a GitHub credential
that can read the repository and see the bypass actors on its tag rulesets.
Install the verifier dependencies from
`requirements-locks/release-verifier-linux-x86_64.txt` on the matching Linux
x64 Python environment.

```bash
python scripts/capture_release_tag_governance.py \
  --repository "<owner/repo>" --tag "<tag>" --sha "<release-sha>" \
  --auditor-identity "<auditor identity>" --key-id "<enrolled key ID>" \
  --private-key "<auditor-local Ed25519 PEM>" --out-dir "<new output directory>" \
  --run-id "<promotion run ID>" --run-attempt "<attempt>" --operation create-draft
```

The command reads the exact tag and its policy from GitHub, checks active tag
rulesets for update and deletion protection with no bypass actors, and checks
the tag again before signing. Keep the private key on the auditor's system.
Wait for the promotion job to print the proof ref. From a separate auditor
checkout, put `tag-governance-attestation.json` and its detached
`tag-governance-attestation.sig.json` at the root of one data-only commit.
Push that commit to the exact ref printed by the command and the workflow.
The workflow reads both files from the same commit. It waits up to 15 minutes
for the ref to appear and then checks the signature and the short validity
window. The workflow also revalidates the signed redistribution approval and
its expiry immediately before creating the draft and before publishing it.

After upload and draft verification, capture a second proof with
`--operation publish --draft-id "<numeric draft ID>"` and a new output
directory. Push its two files together to the new printed ref. Keep the exact
publication proof and signature for the aggregate audit. The workflow also
retains a copy as `production-tag-governance-<run ID>-<attempt>`.

## Verify a published artifact

Keep the file's published name. Set `release_tag` and `release_sha` to the
approved promotion tag and its full source commit SHA before verifying the
download.

```sh
release_tag=REPLACE_WITH_RELEASE_TAG
release_sha=REPLACE_WITH_RELEASE_COMMIT_SHA
python scripts/check_release_provenance.py \
  --asset "./remote-ops-workspace-${release_tag}-linux-x86_64.AppImage" \
  --repository Yunushan/remote-ops-workspace \
  --tag "$release_tag" \
  --sha "$release_sha"
```

The verifier compares the file's SHA-256 with the immutable GitHub Release
and checks the attestation against the completed promotion run. Use the
matching published filename on Windows, macOS, and Linux. Verify the platform
installer signature before installation. See
[`../PRODUCTION_DEPLOYMENT.md`](../PRODUCTION_DEPLOYMENT.md).

## Installer trust boundary (O3)

`installers/install.sh`, `installers/install.bat`, `installers/install.ps1` and
`installers/install-termux.sh` are **source installers**: they install from a
checked-out source tree and perform no artifact integrity check. They must not be
used to fetch an opaque binary over the network.

For a promoted binary, run the verification command above on the downloaded
file before opening the installer.

## Recover a failed publication

The completed-release audit checks whether the signed redistribution approval
was valid at the publication time authenticated by GitHub and the successful
promotion run. The live promotion workflow checks that the approval is still
valid immediately before each release mutation.

Retain the signed approval, its detached signature and the exact review
bundle, including the two original XP evidence ZIPs per architecture.
Promotion verifies their live Actions artifact identities and attests the
approval and signature. Later certification checks those attestations
against the same successful promotion attempt as the release assets. The
retained XP files are checked against the signed digests and published
package bytes after the Actions archives expire.

Both versioned publication workflows report the numeric release ID if an error
occurs after draft creation. Once the failed run ends, inspect that release and
match its tag and transaction marker to the failed run. If it is still a draft,
remove that draft and dispatch a new run for the same tag. Use the workflow to
publish so it can verify the complete inventory and provenance before promotion.
If GitHub already shows a published release, retain it and investigate the
failed check before using the release or claiming certification.

## Rollback

If a promoted release is withdrawn after publication, follow
[`UPGRADE_AND_ROLLBACK.md`](UPGRADE_AND_ROLLBACK.md) on the receiving hosts and
record the incident per
[`SECRET_ROTATION_AND_INCIDENT.md`](SECRET_ROTATION_AND_INCIDENT.md).

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

## Stage the candidate for review

Use the **Report promotion coordinates** summary from the successful
`release.yml` run on the production tag. Set `release_repository`,
`release_tag`, `release_sha`, `build_run_id`,
`candidate_inventory_artifact_id`, and `candidate_inventory_archive_digest`
from that run and its repository. Authenticate GitHub CLI and set `GH_TOKEN`
or `GITHUB_TOKEN` with Actions, attestations, and contents read access.

From the tagged checkout, download the sealed inventory to `$approval_dir/bundle`
and materialize the standard release assets into a new directory outside the
checkout. The materializer verifies the original inventory ZIP digest, exact
tag and build attempt, the inventory's attestation, and all candidate bytes.

```bash
gh run download "$build_run_id" --repo "$release_repository" \
  --name release-candidate-inventory --dir "$approval_dir/bundle"
python scripts/release_candidate_inventory.py promote \
  --repository "$release_repository" --release-tag "$release_tag" \
  --release-sha "$release_sha" --build-run-id "$build_run_id" --build-run-attempt 1 \
  --inventory-artifact-id "$candidate_inventory_artifact_id" \
  --inventory-archive-digest "$candidate_inventory_archive_digest" \
  --approved-inventory "$approval_dir/bundle/release-candidate-inventory.json" \
  --assets-root "$release_assets_dir"
```

After the platform host runs are finalized, place the reviewed registry at
`$approval_dir/bundle/platform_verified_evidence.json`. Import the native
packages and their review files from the exact Actions runs into the same
staging directory.

```bash
python scripts/import_platform_evidence_artifacts.py \
  --registry "$approval_dir/bundle/platform_verified_evidence.json" \
  --release-tag "$release_tag" --release-head-sha "$release_sha" \
  --require-goal-targets --out-dir "$release_assets_dir" \
  --verify-source-run --repository "$release_repository"
```

Retain the raw `candidate-pip-inspect.json` from each standard native
target's `release-runtime-*` artifact. The sealed inventory's
`runtime_reports` entries bind each report's artifact ID, archive digest,
payload size and payload SHA-256. Use those exact report bytes in the review
bundle. See the [protected source evidence capture](../PRODUCTION_READINESS.md#external-prerequisites)
for the registry's original Actions archives.

## Prepare the policy before tagging

Enroll the independent redistribution reviewer's public key
in `trusted_ed25519_keys` and the governance auditor's public key in
`tag_governance_attestation.trusted_ed25519_keys` in
`configs/release_compliance_policy.json`. Each entry needs a unique `key_id`
within its list and a `public_key` containing the base64-encoded raw 32-byte
Ed25519 public key. The reviewer and auditor keep their private keys on their
own systems. The independent reviewer must approve the closed-world
redistribution policy and inventory inputs before the policy can declare
`policy_status: approved` and `closed_world_inventory_approved: true`.
Set the tag-governance policy to `enforced` with the enrolled auditor key.
The policy must map every production target to the tracked lock its workflow
consumes.

On the protected source commit, install the hash-locked verifier dependencies
and run the policy check from a Linux x64 Python environment.

```bash
python -m pip install --require-hashes --requirement requirements-locks/release-verifier-linux-x86_64.txt
python scripts/check_release_license_compliance.py --check-policy-only
```

Cut the tag after the policy check and the required CI checks pass. The
artifact-specific approval uses the resulting tag, commit, and signed
installer bytes.

## Prepare the signed redistribution approval

Once the reviewer has approved the exact tagged candidate and bundle, save
the approved JSON as `release-evidence.json`. In the tagged checkout, use a
Linux x64 Python environment with
`python -m pip install --require-hashes --requirement requirements-locks/release-verifier-linux-x86_64.txt`.
The example signs the existing bytes and verifies the signature against the
enrolled public key. Set the three shell variables to the reviewed JSON, the
enrolled key ID and the path to the reviewer's local Ed25519 PEM.

```bash
python - "$approval_json" "$review_key_id" "$review_private_key" <<'PY'
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from scripts.check_release_license_compliance import verify_evidence_signature

approval, key_id, private_key = sys.argv[1:]
approval_path = Path(approval)
if approval_path.name != "release-evidence.json":
    raise SystemExit("expected release-evidence.json")
payload = approval_path.read_bytes()
key = load_pem_private_key(Path(private_key).read_bytes(), password=None)
if not isinstance(key, Ed25519PrivateKey):
    raise SystemExit("the review key must be Ed25519")
signature = {
    "schema_version": 1,
    "algorithm": "ed25519",
    "key_id": key_id,
    "signature": base64.b64encode(key.sign(payload)).decode("ascii"),
}
policy = json.loads(Path("configs/release_compliance_policy.json").read_bytes())
verify_evidence_signature(payload, signature, policy)
with approval_path.with_name("release-evidence.sig.json").open("x", encoding="utf-8") as output:
    json.dump(signature, output, indent=2)
    output.write("\n")
PY
```

Run the exact-byte audit from the tagged checkout with the same sealed
inventory and signed platform registry the promotion job will consume. Set
`approval_dir` to the directory containing the two approval files and its
`bundle/` subdirectory. Set `release_assets_dir` to the complete staged asset
inventory and authenticate GitHub CLI for the live source checks.

```bash
python scripts/check_release_license_compliance.py \
  --policy configs/release_compliance_policy.json --policy-root . \
  --assets-dir "$release_assets_dir" --repository "$release_repository" \
  --tag "$release_tag" --sha "$release_sha" \
  --evidence "$approval_dir/release-evidence.json" \
  --signature "$approval_dir/release-evidence.sig.json" \
  --evidence-root "$approval_dir/bundle" \
  --candidate-inventory "$approval_dir/bundle/release-candidate-inventory.json" \
  --protected-platform-registry "$approval_dir/bundle/platform_verified_evidence.json" \
  --audit-redistribution-only
```

After the audit passes, place the two approval files and `bundle/` at
`releases/<tag>/<sha>/` on the data-only `release-compliance-evidence` branch.
Preserve the exact signed bytes and record the full commit SHA for dispatch.

## Dispatch production promotion

Copy the tag, build run ID, numeric inventory artifact ID and
`sha256:` archive digest from the successful candidate run's **Report promotion
coordinates** step. Use the full commit SHA containing the independent approval
and evidence bundle on `release-compliance-evidence`. Set the shell variables
below to those values before dispatching:

```bash
gh workflow run release-promotion.yml \
  --repo "$release_repository" --ref "$release_tag" \
  -f release_tag="$release_tag" \
  -f build_run_id="$build_run_id" \
  -f build_run_attempt=1 \
  -f candidate_inventory_artifact_id="$candidate_inventory_artifact_id" \
  -f candidate_inventory_archive_digest="$candidate_inventory_archive_digest" \
  -f evidence_commit_sha="$evidence_commit_sha"
```

The workflow checks that the dispatch ref and the release tag resolve to the
same source commit. Promotion accepts only attempt 1 of the candidate run.
If the candidate must be rebuilt, dispatch a new candidate run from the same
tag and obtain fresh approval for its sealed inventory. Use the new run ID,
artifact ID and digest.

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
retains a copy as `production-tag-governance-<run ID>-<attempt>`. After a
successful promotion, the certification workflow retrieves that copy and
verifies that the proof, the signed redistribution approval, and all
immutable release assets share the triggering run and attempt. It verifies
both independent signatures and checks their validity at publication.

## Download the publication evidence

Use the tag, run ID and attempt of the completed, successful promotion.
Choose a new download directory for the release assets and a separate
evidence directory outside the tagged checkout.

```bash
gh release download "$release_tag" --repo "$release_repository" --dir "$release_assets_dir"
gh run download "$promotion_run_id" --repo "$release_repository" \
  --name "production-tag-governance-${promotion_run_id}-${promotion_run_attempt}" \
  --dir "$publication_evidence_dir/governance"
gh run download "$promotion_run_id" --repo "$release_repository" \
  --name "production-redistribution-approval-${promotion_run_id}-${promotion_run_attempt}" \
  --dir "$publication_evidence_dir/redistribution"
```

Use the downloaded governance JSON and signature for the aggregate audit.
The redistribution artifact contains the approval and signature. The
aggregate also needs the matching signed evidence bundle and sealed candidate
inventory from the pinned evidence commit, and the original protected-platform
Actions ZIPs retained during [source evidence capture](../PRODUCTION_READINESS.md#external-prerequisites).

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

The publication workflows report the numeric release ID if an error occurs
after draft creation. Production promotion can recover the ID by matching the
tag and full transaction marker when the creation response was lost. The marker
contains the tag, source SHA, run ID, and run attempt. If interruption stopped
the report step, compare those four values in the draft's raw release notes
with the failed Actions attempt. Inspect the numeric release after that run
ends. If it is still a draft, remove that draft and dispatch a new run for the
same tag. Use the workflow to publish so it can verify the complete inventory
and provenance before promotion.
If GitHub already shows a published release, retain it and investigate the
failed check before using the release or claiming certification.

## Rollback

If a promoted release is withdrawn after publication, follow
[`UPGRADE_AND_ROLLBACK.md`](UPGRADE_AND_ROLLBACK.md) on the receiving hosts and
record the incident per
[`SECRET_ROTATION_AND_INCIDENT.md`](SECRET_ROTATION_AND_INCIDENT.md).

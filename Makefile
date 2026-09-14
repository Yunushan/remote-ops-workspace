.PHONY: install test verify verify-quick lint compile gui-interactions production-readiness run-web

RELEASE_TAG ?=
RELEASE_REPOSITORY ?=
RELEASE_ASSETS_DIR ?= release-assets
RELEASE_SHA ?=
RELEASE_LICENSE_EVIDENCE ?=
RELEASE_LICENSE_SIGNATURE ?=
RELEASE_LICENSE_EVIDENCE_ROOT ?=
RELEASE_CANDIDATE_INVENTORY ?=
RELEASE_PLATFORM_EVIDENCE_REGISTRY ?=
RELEASE_TAG_GOVERNANCE_ATTESTATION ?=
RELEASE_TAG_GOVERNANCE_SIGNATURE ?=

install:
	python -m pip install -e ".[desktop,security,dev]"

test:
	python scripts/verify.py

verify:
	python scripts/verify.py

verify-quick:
	python scripts/verify.py --quick

compile:
	python -m compileall src tests scripts

lint:
	python scripts/verify.py --quick --lint --no-cli-smoke

gui-interactions:
	python scripts/check_gui_interactions.py --require-pyqt6 --out-dir artifacts/gui-interactions-local

production-readiness:
	@test -n "$(RELEASE_TAG)" || (echo "RELEASE_TAG=vX.Y.Z is required" >&2; exit 2)
	@test -n "$(RELEASE_REPOSITORY)" || (echo "RELEASE_REPOSITORY=owner/repo is required" >&2; exit 2)
	@test -n "$(RELEASE_SHA)" || (echo "RELEASE_SHA=<40-character tag commit SHA> is required" >&2; exit 2)
	@test -n "$(RELEASE_LICENSE_EVIDENCE)" || (echo "RELEASE_LICENSE_EVIDENCE=<signed approval JSON> is required" >&2; exit 2)
	@test -n "$(RELEASE_LICENSE_SIGNATURE)" || (echo "RELEASE_LICENSE_SIGNATURE=<detached Ed25519 signature JSON> is required" >&2; exit 2)
	@test -n "$(RELEASE_LICENSE_EVIDENCE_ROOT)" || (echo "RELEASE_LICENSE_EVIDENCE_ROOT=<closed-world evidence bundle directory> is required" >&2; exit 2)
	@test -n "$(RELEASE_CANDIDATE_INVENTORY)" || (echo "RELEASE_CANDIDATE_INVENTORY=<signed exact build-candidate inventory JSON> is required" >&2; exit 2)
	@test -n "$(RELEASE_PLATFORM_EVIDENCE_REGISTRY)" || (echo "RELEASE_PLATFORM_EVIDENCE_REGISTRY=<signed protected-platform registry JSON> is required" >&2; exit 2)
	@test -n "$(RELEASE_TAG_GOVERNANCE_ATTESTATION)" || (echo "RELEASE_TAG_GOVERNANCE_ATTESTATION=<short-lived signed tag ruleset snapshot JSON> is required" >&2; exit 2)
	@test -n "$(RELEASE_TAG_GOVERNANCE_SIGNATURE)" || (echo "RELEASE_TAG_GOVERNANCE_SIGNATURE=<detached tag-governance Ed25519 signature JSON> is required" >&2; exit 2)
	@tag_sha="$$(git rev-parse --verify "$(RELEASE_TAG)^{commit}" 2>/dev/null)" && release_sha="$$(git rev-parse --verify "$(RELEASE_SHA)^{commit}" 2>/dev/null)" && test "$$tag_sha" = "$$release_sha" || (echo "RELEASE_SHA must resolve to the commit tagged by RELEASE_TAG" >&2; exit 2)
	@head_sha="$$(git rev-parse --verify "HEAD^{commit}" 2>/dev/null)" && release_sha="$$(git rev-parse --verify "$(RELEASE_SHA)^{commit}" 2>/dev/null)" && test "$$head_sha" = "$$release_sha" || (echo "the current checkout HEAD must equal RELEASE_SHA" >&2; exit 2)
	python scripts/check_repository_cleanup.py --require-clean
	python scripts/check_release_maturity.py --release-tag "$(RELEASE_TAG)"
	python scripts/verify.py --production-quality
	python scripts/check_python315_ci_evidence.py --repository "$(RELEASE_REPOSITORY)" --branch main --sha "$(RELEASE_SHA)"
	python scripts/check_platform_verified_evidence.py --registry "$(RELEASE_PLATFORM_EVIDENCE_REGISTRY)" --require-goal-targets --require-review-bundles --release-tag "$(RELEASE_TAG)"
	python scripts/check_mobaxterm_parity_evidence.py --require-complete
	python scripts/check_release_publish_assets.py --assets-dir "$(RELEASE_ASSETS_DIR)" --tag "$(RELEASE_TAG)" --repository "$(RELEASE_REPOSITORY)" --evidence-registry "$(RELEASE_PLATFORM_EVIDENCE_REGISTRY)" --require-platform-goal-targets --require-mobaxterm-parity-complete --native-release-channel production-signed
	python scripts/check_release_license_compliance.py --assets-dir "$(RELEASE_ASSETS_DIR)" --tag "$(RELEASE_TAG)" --repository "$(RELEASE_REPOSITORY)" --sha "$(RELEASE_SHA)" --evidence "$(RELEASE_LICENSE_EVIDENCE)" --signature "$(RELEASE_LICENSE_SIGNATURE)" --evidence-root "$(RELEASE_LICENSE_EVIDENCE_ROOT)" --candidate-inventory "$(RELEASE_CANDIDATE_INVENTORY)" --protected-platform-registry "$(RELEASE_PLATFORM_EVIDENCE_REGISTRY)" --tag-governance-attestation "$(RELEASE_TAG_GOVERNANCE_ATTESTATION)" --tag-governance-signature "$(RELEASE_TAG_GOVERNANCE_SIGNATURE)"
	python scripts/check_release_provenance.py --assets-dir "$(RELEASE_ASSETS_DIR)" --tag "$(RELEASE_TAG)" --repository "$(RELEASE_REPOSITORY)" --sha "$(RELEASE_SHA)"
	python scripts/check_repository_governance.py --repository "$(RELEASE_REPOSITORY)" --branch main --sha "$(RELEASE_SHA)" --release-tag "$(RELEASE_TAG)"
	python scripts/check_platform_release_evidence_remote.py --repository "$(RELEASE_REPOSITORY)" --release-tag "$(RELEASE_TAG)" --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head
	@head_sha="$$(git rev-parse --verify "HEAD^{commit}" 2>/dev/null)" && release_sha="$$(git rev-parse --verify "$(RELEASE_SHA)^{commit}" 2>/dev/null)" && test "$$head_sha" = "$$release_sha" || (echo "the current checkout HEAD changed during the production-readiness audit" >&2; exit 2)
	python scripts/check_repository_cleanup.py --require-clean
	@echo "production readiness: 100/100 gates passed"

run-web:
	row serve-web --host 127.0.0.1 --port 8765

.PHONY: install test verify verify-quick lint compile gui-interactions production-readiness run-web

RELEASE_TAG ?=
RELEASE_REPOSITORY ?=
RELEASE_ASSETS_DIR ?= release-assets

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
	python scripts/verify.py --quick --no-cli-smoke
	python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag "$(RELEASE_TAG)"
	python scripts/check_mobaxterm_parity_evidence.py --require-complete
	python scripts/check_release_publish_assets.py --assets-dir "$(RELEASE_ASSETS_DIR)" --tag "$(RELEASE_TAG)" --repository "$(RELEASE_REPOSITORY)" --require-platform-goal-targets --require-mobaxterm-parity-complete --native-release-channel production-signed
	python scripts/check_repository_governance.py --repository "$(RELEASE_REPOSITORY)"
	python scripts/check_platform_release_evidence_remote.py --repository "$(RELEASE_REPOSITORY)" --release-tag "$(RELEASE_TAG)" --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head
	@echo "production readiness: 100/100 gates passed"

run-web:
	row serve-web --host 127.0.0.1 --port 8765

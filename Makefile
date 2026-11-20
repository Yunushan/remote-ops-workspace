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
RELEASE_PLATFORM_SOURCE_ARCHIVES ?=
RELEASE_MOBAXTERM_REGISTRY_COMMIT ?=
RELEASE_MOBAXTERM_EVIDENCE_ROOT ?=
export RELEASE_PROFESSIONAL_UPDATE_ORIGINS ?=
RELEASE_TAG_GOVERNANCE_ATTESTATION ?=
RELEASE_TAG_GOVERNANCE_SIGNATURE ?=

export RELEASE_TAG RELEASE_REPOSITORY RELEASE_SHA RELEASE_ASSETS_DIR
export RELEASE_LICENSE_EVIDENCE RELEASE_LICENSE_SIGNATURE RELEASE_LICENSE_EVIDENCE_ROOT
export RELEASE_CANDIDATE_INVENTORY RELEASE_PLATFORM_EVIDENCE_REGISTRY RELEASE_PLATFORM_SOURCE_ARCHIVES
export RELEASE_MOBAXTERM_REGISTRY_COMMIT RELEASE_MOBAXTERM_EVIDENCE_ROOT
export RELEASE_TAG_GOVERNANCE_ATTESTATION RELEASE_TAG_GOVERNANCE_SIGNATURE

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
	python scripts/check_production_readiness.py

run-web:
	row serve-web --host 127.0.0.1 --port 8765

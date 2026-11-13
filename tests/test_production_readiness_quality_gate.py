from pathlib import Path


def test_make_production_readiness_is_fail_closed_for_quality_and_exact_sha() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    target = makefile.split("production-readiness:\n", 1)[1].split("\nrun-web:", 1)[0]

    assert 'test -n "$(RELEASE_SHA)"' in target
    assert 'test -n "$(RELEASE_MOBAXTERM_REGISTRY_COMMIT)"' in target
    assert 'test -n "$(RELEASE_LICENSE_EVIDENCE)"' in target
    assert 'test -n "$(RELEASE_LICENSE_SIGNATURE)"' in target
    assert 'test -n "$(RELEASE_LICENSE_EVIDENCE_ROOT)"' in target
    assert 'test -n "$(RELEASE_PLATFORM_SOURCE_ARCHIVES)"' in target
    assert 'git rev-parse --verify "$(RELEASE_TAG)^{commit}"' in target
    assert 'git rev-parse --verify "$(RELEASE_SHA)^{commit}"' in target
    assert 'git rev-parse --verify "HEAD^{commit}"' in target
    assert 'test "$$head_sha" = "$$release_sha"' in target
    assert target.count("python scripts/check_repository_cleanup.py --require-clean") == 2
    assert 'python scripts/check_release_maturity.py --release-tag "$(RELEASE_TAG)"' in target
    assert "python scripts/verify.py --production-quality" in target
    assert "--quick" not in target
    assert "--no-cli-smoke" not in target
    assert (
        'python scripts/check_python315_ci_evidence.py --repository "$(RELEASE_REPOSITORY)" '
        '--branch main --sha "$(RELEASE_SHA)"'
    ) in target
    assert (
        'python scripts/check_repository_governance.py --repository "$(RELEASE_REPOSITORY)" '
        '--branch main --sha "$(RELEASE_SHA)" --release-tag "$(RELEASE_TAG)"'
    ) in target
    assert (
        'python scripts/check_release_license_compliance.py '
        '--assets-dir "$(RELEASE_ASSETS_DIR)" --tag "$(RELEASE_TAG)" '
        '--repository "$(RELEASE_REPOSITORY)" --sha "$(RELEASE_SHA)" '
        '--evidence "$(RELEASE_LICENSE_EVIDENCE)" '
        '--signature "$(RELEASE_LICENSE_SIGNATURE)" '
        '--evidence-root "$(RELEASE_LICENSE_EVIDENCE_ROOT)"'
    ) in target
    assert (
        '--tag-governance-attestation "$(RELEASE_TAG_GOVERNANCE_ATTESTATION)" '
        '--tag-governance-signature "$(RELEASE_TAG_GOVERNANCE_SIGNATURE)" '
        '--verify-published-release'
    ) in target
    assert '--platform-source-archives "$(RELEASE_PLATFORM_SOURCE_ARCHIVES)"' in target
    assert (
        'python scripts/check_release_mobaxterm_parity.py --repository "$(RELEASE_REPOSITORY)" '
        '--tag "$(RELEASE_TAG)" --sha "$(RELEASE_SHA)" '
        '--registry-commit "$(RELEASE_MOBAXTERM_REGISTRY_COMMIT)" --assets-dir "$(RELEASE_ASSETS_DIR)"'
    ) in target
    assert target.index("scripts/check_release_license_compliance.py") < target.index(
        "scripts/check_release_mobaxterm_parity.py"
    ) < target.index('echo "production readiness: 100/100 gates passed"')
    assert target.index("scripts/check_repository_cleanup.py --require-clean") < target.index(
        "scripts/verify.py --production-quality"
    )
    assert target.index("scripts/check_release_maturity.py") < target.index(
        "scripts/verify.py --production-quality"
    )
    assert target.rindex("scripts/check_repository_cleanup.py --require-clean") > target.index(
        "--verify-published-release"
    )
    assert target.index("scripts/check_python315_ci_evidence.py") < target.index(
        'echo "production readiness: 100/100 gates passed"'
    )
    assert target.index("scripts/check_repository_governance.py") < target.index(
        'echo "production readiness: 100/100 gates passed"'
    )
    assert target.index("--verify-published-release") < target.index(
        'echo "production readiness: 100/100 gates passed"'
    )

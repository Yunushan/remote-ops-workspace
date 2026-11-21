from __future__ import annotations

import re
import struct
from base64 import b64encode
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts import check_release_remote_preconditions as preconditions
from scripts import check_release_signing_inputs as signing

API_ROOT = "https://api.github.com"
REPOSITORY = "owner/repo"
REPOSITORY_URL = f"{API_ROOT}/repos/{REPOSITORY}"
RELEASES_PATH = "/repositories/123/releases"
FIRST_PAGE = f"{REPOSITORY_URL}/releases?per_page=100"
SECOND_PAGE = f"{API_ROOT}{RELEASES_PATH}?per_page=100&page=2"
RELEASE_TAG = "v1.2.3"
RELEASE_SHA = "a" * 40
BUNDLE_SHA = "b" * 64
PROFESSIONAL_DEPLOYMENT_ID = "d36b9320-836e-42fe-82f3-e3868beebf43"
PROFESSIONAL_ICON_TABLE = struct.pack("<HHHBBBBHHII", 0, 1, 1, 16, 16, 0, 0, 1, 32, 4, 22)
PROFESSIONAL_ICON = b64encode(PROFESSIONAL_ICON_TABLE + b"icon").decode("ascii")
PROFESSIONAL_VALUES = {
    "ROW_PROFESSIONAL_BRAND": "fixture-value-not-for-output",
    "ROW_PROFESSIONAL_ORGANIZATION": "Example organization",
    "ROW_PROFESSIONAL_LOGO_BASE64": PROFESSIONAL_ICON[:12] + "\r\n" + PROFESSIONAL_ICON[12:],
    "ROW_PROFESSIONAL_DEPLOYMENT_ID": f" {PROFESSIONAL_DEPLOYMENT_ID.upper()} ",
    "RELEASE_PROFESSIONAL_UPDATE_URL": "https://updates.example.test:8443/releases/manifest.json",
    "RELEASE_PROFESSIONAL_UPDATE_ORIGINS": "https://updates.example.test:8443 \n https://downloads.example.test",
    "RELEASE_PROFESSIONAL_UPDATE_PUBLIC_KEY": "ed25519:" + b64encode(b"k" * 32).decode("ascii"),
}


def test_signing_inventory_matches_the_production_workflow() -> None:
    workflow = (preconditions.ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    preflight = workflow.split("  release-preflight:\n", 1)[1].split("      - name: Detect release signing readiness\n", 1)
    assert "    environment: release\n" in preflight[0]
    step = preflight[1].split("      - name:", 1)[0]
    configured = set(re.findall(r"\$\{\{ secrets\.(ROW_[A-Z0-9_]+) \}\}", step))
    checked = {name for names in signing.SIGNING_INPUTS.values() for name in names}
    assert configured == checked == preconditions.RELEASE_SIGNING_SECRETS


def test_parity_configuration_matches_the_qualification_workflows() -> None:
    workflows = preconditions.ROOT / ".github/workflows"
    for environment, name in zip(preconditions.NATIVE_PARITY_ENVIRONMENTS, (
        "smartcard-browser-evidence.yml", "transport-terminal-evidence.yml",
    ), strict=True):
        workflow = (workflows / name).read_text(encoding="utf-8")
        assert f"    environment: {environment}\n" in workflow
    professional = (workflows / "professional-deployment-evidence.yml").read_text(encoding="utf-8")
    build, review = professional.split("  qualify-review:\n", 1)
    for environment, job in zip(preconditions.PROFESSIONAL_ENVIRONMENT_VARIABLES, (build, review), strict=True):
        assert f"    environment: {environment}\n" in job
        assert set(re.findall(r"\$\{\{ vars\.([A-Z0-9_]+) \}\}", job)) == set(
            preconditions.PROFESSIONAL_ENVIRONMENT_VARIABLES[environment]
        )


@pytest.mark.parametrize(("change", "error"), [
    (None, None),
    ("exact-tag", None),
    ("no-reviewer-rule", "professional-update-review environment must require deployment reviewers"),
    ("empty-reviewers", "smartcard-evidence environment must require deployment reviewers"),
    ("bad-reviewer", "malformed required reviewer metadata for transport-evidence"),
    ("unrestricted", "transport-evidence environment must use selected deployment branches and tags"),
    ("branch-policy", "smartcard-evidence environment must allow v1.2.3 through a tag-only deployment policy"),
    ("different-tag", "smartcard-evidence environment must allow v1.2.3 through a tag-only deployment policy"),
    ("wrong-variable", "ROW_PROFESSIONAL_BRAND in the release environment must have a nonempty value"),
    ("blank-variable", "RELEASE_PROFESSIONAL_UPDATE_PUBLIC_KEY in the professional-update-review environment must have a nonempty value"),
    ("brand-control", "ROW_PROFESSIONAL_BRAND contains control characters"),
    ("invalid-base64", "ROW_PROFESSIONAL_LOGO_BASE64 must encode an ICO"),
    ("invalid-ico", "ROW_PROFESSIONAL_LOGO_BASE64 must encode an ICO"),
    ("no-ico-image", "ROW_PROFESSIONAL_LOGO_BASE64 must encode an ICO"),
    ("malformed-deployment", "ROW_PROFESSIONAL_DEPLOYMENT_ID must be a hyphenated GUID"),
    ("noncanonical-deployment", "ROW_PROFESSIONAL_DEPLOYMENT_ID must be a hyphenated GUID"),
    ("stock-deployment", "ROW_PROFESSIONAL_DEPLOYMENT_ID must differ from the stock installer IDs"),
    ("invalid-origin", "RELEASE_PROFESSIONAL_UPDATE_ORIGINS: approved professional update origin"),
    ("local-origin", "RELEASE_PROFESSIONAL_UPDATE_ORIGINS: published professional update channel"),
    ("unapproved-url", "RELEASE_PROFESSIONAL_UPDATE_URL must be an HTTPS URL on an approved origin"),
    ("invalid-key", "RELEASE_PROFESSIONAL_UPDATE_PUBLIC_KEY must encode a 32-byte ed25519 public key"),
])
def test_parity_preflight_checks_review_holds_tag_rules_and_professional_variables(monkeypatch, capsys, change, error):
    monkeypatch.setenv("GITHUB_API_URL", API_ROOT)
    monkeypatch.setenv("ROW_RELEASE_SIGNING_INVENTORY_TOKEN", "environment-reader")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    calls = []
    prefix = f"{REPOSITORY_URL}/environments/"
    changes = {
        "blank-variable": ("RELEASE_PROFESSIONAL_UPDATE_PUBLIC_KEY", " \t"),
        "brand-control": ("ROW_PROFESSIONAL_BRAND", "fixture-value-not-for-output\x01"),
        "invalid-base64": ("ROW_PROFESSIONAL_LOGO_BASE64", "fixture-value-not-for-output"),
        "invalid-ico": ("ROW_PROFESSIONAL_LOGO_BASE64", "bm90LWFuLWljbw=="),
        "no-ico-image": ("ROW_PROFESSIONAL_LOGO_BASE64", b64encode(PROFESSIONAL_ICON_TABLE).decode("ascii")),
        "malformed-deployment": ("ROW_PROFESSIONAL_DEPLOYMENT_ID", "fixture-value-not-for-output"),
        "noncanonical-deployment": ("ROW_PROFESSIONAL_DEPLOYMENT_ID", f"{{{PROFESSIONAL_DEPLOYMENT_ID}}}"),
        "stock-deployment": ("ROW_PROFESSIONAL_DEPLOYMENT_ID", "5C887096-F4E5-4AB8-8D6F-65052D08D284"),
        "invalid-origin": ("RELEASE_PROFESSIONAL_UPDATE_ORIGINS", "https://updates.example.test/path"),
        "local-origin": ("RELEASE_PROFESSIONAL_UPDATE_ORIGINS", "https://127.0.0.1"),
        "unapproved-url": ("RELEASE_PROFESSIONAL_UPDATE_URL", "https://fixture-value-not-for-output.test/manifest.json"),
        "invalid-key": ("RELEASE_PROFESSIONAL_UPDATE_PUBLIC_KEY", "ed25519:aw=="),
    }
    variables = dict(PROFESSIONAL_VALUES)
    if change in changes:
        name, value = changes[change]
        variables[name] = value

    def get_json(url, token, *, api_version):
        assert url.startswith(prefix) and api_version == "2026-03-10"
        environment, _, resource = url.removeprefix(prefix).partition("/")
        calls.append((environment, resource))
        assert token == ("environment-reader" if resource.startswith("variables/") else None)
        if resource == "deployment-branch-policies?per_page=100&page=1":
            ref = "v1.2.2" if change == "different-tag" else RELEASE_TAG if change == "exact-tag" else "v*"
            policies = [{"name": ref, "type": "tag"}]
            if change == "branch-policy":
                policies.append({"name": "main", "type": "branch"})
            return {"total_count": len(policies), "branch_policies": policies}, {}
        if resource.startswith("variables/"):
            name = resource.removeprefix("variables/")
            assert name in preconditions.PROFESSIONAL_ENVIRONMENT_VARIABLES[environment]
            value = variables[name]
            if change == "wrong-variable" and name == "ROW_PROFESSIONAL_BRAND":
                name = "OTHER_VAR"
            return {"name": name, "value": value}, {}

        assert resource == ""
        reviewers = [{"type": "Team", "reviewer": {"id": 11}}, {"type": "User", "reviewer": {"id": 12}}]
        if change == "empty-reviewers" and environment == "smartcard-evidence":
            reviewers = []
        if change == "bad-reviewer" and environment == "transport-evidence":
            reviewers[0]["reviewer"]["id"] = True
        rules = [{"type": "required_reviewers", "reviewers": reviewers}]
        if change == "no-reviewer-rule" and environment == "professional-update-review":
            rules = [{"type": "wait_timer", "wait_timer": 5}]
        policy = {"custom_branch_policies": True, "protected_branches": False}
        if change == "unrestricted" and environment == "transport-evidence":
            policy = None
        return {"name": environment, "deployment_branch_policy": policy, "protection_rules": rules}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    result = preconditions.main(["parity", "--repository", REPOSITORY, "--tag", RELEASE_TAG])
    output = capsys.readouterr()
    assert "fixture-value-not-for-output" not in output.out + output.err
    if error:
        assert result == 1 and error in output.err and output.out == ""
    else:
        assert result == 0 and f"parity passed for {REPOSITORY} and {RELEASE_TAG}" in output.out
        assert calls == [
            *((environment, endpoint) for environment in preconditions.NATIVE_PARITY_ENVIRONMENTS
              for endpoint in ("", "deployment-branch-policies?per_page=100&page=1")),
            (preconditions.PROFESSIONAL_REVIEW_ENVIRONMENT, ""),
            *((environment, f"variables/{name}")
              for environment, names in preconditions.PROFESSIONAL_ENVIRONMENT_VARIABLES.items() for name in names),
        ]


@pytest.mark.parametrize("available", [True, False])
def test_parity_deployment_check_reports_all_environments_without_a_variable_token(
    monkeypatch, capsys, available,
) -> None:
    monkeypatch.setenv("GITHUB_API_URL", API_ROOT)
    monkeypatch.delenv("ROW_RELEASE_SIGNING_INVENTORY_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    environments = (*preconditions.NATIVE_PARITY_ENVIRONMENTS, preconditions.PROFESSIONAL_REVIEW_ENVIRONMENT)
    checked = []

    def get_json(url, token, *, api_version):
        assert token is None and api_version == "2026-03-10"
        environment, _, resource = url.removeprefix(f"{REPOSITORY_URL}/environments/").partition("/")
        assert environment in environments
        if resource:
            assert available and resource == "deployment-branch-policies?per_page=100&page=1"
            return {"total_count": 1, "branch_policies": [{"name": RELEASE_TAG, "type": "tag"}]}, {}
        checked.append(environment)
        if not available:
            raise RuntimeError("GitHub API returned HTTP 404")
        return {
            "name": environment,
            "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User", "reviewer": {"id": 1}}]}],
            "deployment_branch_policy": {"custom_branch_policies": True, "protected_branches": False},
        }, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    result = preconditions.main(["parity", "--repository", REPOSITORY, "--tag", RELEASE_TAG, "--deployment-only"])
    output = capsys.readouterr()
    assert checked == list(environments)
    if available:
        assert result == 0 and "parity deployment policies passed" in output.out and not output.err
    else:
        assert result == 1 and not output.out
        assert all(f"{environment}: GitHub API returned HTTP 404" in output.err for environment in environments)


@pytest.mark.parametrize("missing", [set(), {"ROW_WINDOWS_TIMESTAMP_URL", "ROW_MACOS_NOTARY_KEY_ID"}])
def test_signing_uses_the_protected_environment_and_reports_missing_names(monkeypatch, missing) -> None:
    names = (preconditions.RELEASE_SIGNING_SECRETS - missing) | {"UNRELATED_ENTRY"}

    def get_json(url, token, *, api_version):
        assert url == f"{REPOSITORY_URL}/environments/release/secrets?per_page=100"
        assert token == "fixture" and api_version == "2026-03-10"
        return {"total_count": len(names), "secrets": [{"name": name} for name in names]}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    if missing:
        with pytest.raises(RuntimeError, match="missing signing secrets") as exc:
            preconditions.require_signing_secret_inventory(API_ROOT, REPOSITORY, "fixture")
        assert all(name in str(exc.value) for name in missing)
        assert "UNRELATED_ENTRY" not in str(exc.value)
    else:
        preconditions.require_signing_secret_inventory(API_ROOT, REPOSITORY, "fixture")


@pytest.mark.parametrize(("payload", "error"), [
    ({"total_count": 101, "secrets": [{"name": "KEY"}]}, "incomplete"),
    ({"total_count": 2, "secrets": [{"name": "KEY"}]}, "incomplete"),
    ({"total_count": True, "secrets": [{"name": "KEY"}]}, "incomplete"),
    ({"total_count": 1, "secrets": [{"name": "private value"}]}, "malformed"),
    ({"total_count": 2, "secrets": [{"name": "KEY"}, {"name": "KEY"}]}, "duplicate"),
])
def test_signing_rejects_unverified_inventory(monkeypatch, payload, error) -> None:
    monkeypatch.setattr(preconditions, "get_json", lambda *args, **kwargs: (payload, {}))
    with pytest.raises(RuntimeError, match=error):
        preconditions.require_signing_secret_inventory(API_ROOT, REPOSITORY, "fixture")


@pytest.mark.parametrize("dedicated_token", [False, True])
def test_signing_command_can_run_before_other_pre_tag_checks(monkeypatch, capsys, dedicated_token) -> None:
    monkeypatch.setenv("GITHUB_API_URL", API_ROOT)
    monkeypatch.setenv("GITHUB_TOKEN", "default-fixture")
    monkeypatch.delenv("ROW_RELEASE_SIGNING_INVENTORY_TOKEN", raising=False)
    if dedicated_token:
        monkeypatch.setenv("ROW_RELEASE_SIGNING_INVENTORY_TOKEN", "signing-fixture")
    calls = []
    monkeypatch.setattr(preconditions, "require_signing_secret_inventory", lambda *args: calls.append(args))
    assert preconditions.main(["signing", "--repository", REPOSITORY]) == 0
    assert calls == [(API_ROOT, REPOSITORY, "signing-fixture" if dedicated_token else "default-fixture")]
    assert "signing passed" in capsys.readouterr().out


def test_signing_access_failure_reports_the_required_permission(monkeypatch) -> None:
    def denied(*args, **kwargs):
        raise RuntimeError("remote response body")

    monkeypatch.setattr(preconditions, "get_json", denied)
    with pytest.raises(RuntimeError, match="Environments read access") as exc:
        preconditions.require_signing_secret_inventory(API_ROOT, REPOSITORY, "fixture")
    assert "remote response body" not in str(exc.value)


@pytest.mark.parametrize("value", [
    f"{RELEASE_TAG} 42 {BUNDLE_SHA}",
    "",
    None,
    f"v1.2.2 42 {BUNDLE_SHA}",
    f"{RELEASE_TAG} 0 {BUNDLE_SHA}",
    f"{RELEASE_TAG} 42 {BUNDLE_SHA.upper()}",
    f"{RELEASE_TAG} 42 {BUNDLE_SHA}\n",
])
def test_debian_bundle_selection_is_bound_to_the_release_environment_and_tag(monkeypatch, value) -> None:
    name = preconditions.DEBIAN_SERVER_BUNDLE_VARIABLE

    def get_json(url, token, *, api_version):
        assert url == f"{REPOSITORY_URL}/environments/release/variables/{name}"
        assert token == "environments-token" and api_version == "2026-03-10"
        return {"name": name, "value": value}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    if value == f"{RELEASE_TAG} 42 {BUNDLE_SHA}":
        assert preconditions.read_debian_server_bundle_selection(
            API_ROOT, REPOSITORY, RELEASE_TAG, "environments-token",
        ) == ("42", BUNDLE_SHA)
    else:
        with pytest.raises(RuntimeError, match="must contain v1.2.3, a positive artifact ID and the reviewed SHA-256"):
            preconditions.read_debian_server_bundle_selection(API_ROOT, REPOSITORY, RELEASE_TAG, "environments-token")


def test_debian_bundle_selection_is_required_when_the_environment_variable_is_unavailable(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise RuntimeError("remote response body")

    monkeypatch.setattr(preconditions, "get_json", unavailable)
    with pytest.raises(RuntimeError, match="could not read ROW_DEBIAN_AMD64_SERVER_BUNDLE") as exc:
        preconditions.read_debian_server_bundle_selection(API_ROOT, REPOSITORY, RELEASE_TAG, "environments-token")
    assert "remote response body" not in str(exc.value)


@pytest.mark.parametrize(("change", "error"), [
    (None, None),
    ("unrestricted", "release environment must use selected"),
    ("platform-branch", "platform-evidence environment must allow only"),
    ("promotion-branch", "release-compliance-review environment is missing the v\\* deployment tag policy"),
    ("missing-type", "did not identify a deployment policy's ref type"),
])
def test_deployment_environments_audit_the_typed_tag_rules_without_credentials(monkeypatch, capsys, change, error):
    monkeypatch.setenv("GITHUB_API_URL", API_ROOT)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    if change is None:
        monkeypatch.setenv("GITHUB_TOKEN", "")
    calls = []
    environments = {
        "release": [{"name": "main", "type": "branch"}, {"name": "v*", "type": "tag"}],
        "release-compliance-review": [{"name": "v*", "type": "tag"}],
        "platform-evidence": [{"name": "v*", "type": "tag"}],
    }
    if change == "platform-branch":
        environments["platform-evidence"].append({"name": "main", "type": "branch"})
    if change == "promotion-branch":
        environments["release-compliance-review"][0]["type"] = "branch"
    if change == "missing-type":
        del environments["release"][1]["type"]

    def get_json(url, token, *, api_version):
        assert token is None and api_version == "2026-03-10"
        environment, _, endpoint = url.removeprefix(f"{REPOSITORY_URL}/environments/").partition("/")
        calls.append((environment, endpoint))
        if endpoint:
            assert endpoint == "deployment-branch-policies?per_page=100&page=1"
            rules = environments[environment]
            return {"total_count": len(rules), "branch_policies": rules}, {}
        policy = {"protected_branches": False, "custom_branch_policies": True}
        return {"name": environment, "deployment_branch_policy": None if change == "unrestricted" else policy}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    result = preconditions.main(["environments", "--repository", REPOSITORY, "--tag", RELEASE_TAG])
    output = capsys.readouterr()
    if error:
        assert result == 1 and re.search(error, output.err)
        assert output.out == ""
    else:
        assert result == 0 and f"environments passed for {REPOSITORY} and {RELEASE_TAG}" in output.out
        assert calls == [(name, endpoint) for name in environments
                         for endpoint in ("", "deployment-branch-policies?per_page=100&page=1")]


@pytest.mark.parametrize(("last_page", "error"), [
    ([{"name": "v*", "type": "tag"}], None),
    ([{"name": "branch-0", "type": "branch"}], "duplicate"),
    ([], "incomplete"),
])
def test_deployment_policy_inventory_proves_all_pages(monkeypatch, last_page, error):
    base = f"{REPOSITORY_URL}/environments/release"
    items = iter([[{"name": f"branch-{i}", "type": "branch"} for i in range(100)], last_page])
    urls = []

    def get_json(url, token, *, api_version):
        urls.append(url)
        return {"total_count": 101, "branch_policies": next(items)}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    if error:
        with pytest.raises(RuntimeError, match=error):
            preconditions.read_deployment_policies(base, None)
    else:
        rules = preconditions.read_deployment_policies(base, None)
        assert len(rules) == 101 and ("tag", "v*") in rules
    assert urls == [f"{base}/deployment-branch-policies?per_page=100&page={page}" for page in (1, 2)]


@pytest.mark.parametrize(("environment", "secret"), [
    ("release-compliance-review", "ROW_RELEASE_IMMUTABILITY_TOKEN"),
    ("platform-evidence", "ROW_PLATFORM_RUNNER_INVENTORY_TOKEN"),
])
def test_environment_tokens_are_required_in_their_own_environment(monkeypatch, environment, secret):
    def get_json(url, token, *, api_version):
        assert url == f"{REPOSITORY_URL}/environments/{environment}/secrets?per_page=100"
        return {"total_count": 0, "secrets": []}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    with pytest.raises(RuntimeError, match=f"missing required secrets in the {environment} environment: {secret}"):
        preconditions.require_environment_secret_inventory(API_ROOT, REPOSITORY, environment, {secret}, "auth")


@pytest.mark.parametrize("collision", [False, True])
@pytest.mark.parametrize("require_push", [False, True])
def test_namespace_checks_numeric_pages_and_accepts_terminal_link(monkeypatch, collision, require_push) -> None:
    previous_page = f"{API_ROOT}{RELEASES_PATH}?per_page=100&page=1"
    responses = {
        REPOSITORY_URL: ({"id": 123, "full_name": "Owner/Repo", "permissions": {"push": True}}, {}),
        FIRST_PAGE: ([], {"Link": f'<{SECOND_PAGE}>; rel="next", <{SECOND_PAGE}>; rel="last"'}),
        SECOND_PAGE: (
            [{"tag_name": "v1.2.3" if collision else "v1.2.2", "draft": True}],
            {"Link": f'<{previous_page}>; rel="prev", <{previous_page}>; rel="first"'},
        ),
    }
    visited = []

    def get_json(url, token, *, api_version):
        assert token == "fixture"
        assert api_version == "2022-11-28"
        visited.append(url)
        return responses[url]

    monkeypatch.setattr(preconditions, "get_json", get_json)
    if collision:
        with pytest.raises(RuntimeError, match="already uses tag/name"):
            preconditions.require_unused_namespace(API_ROOT, REPOSITORY, "v1.2.3", "fixture", require_push=require_push)
    else:
        preconditions.require_unused_namespace(API_ROOT, REPOSITORY, "v1.2.3", "fixture", require_push=require_push)
    assert visited == list(responses)


@pytest.mark.parametrize(
    "next_url",
    [
        SECOND_PAGE.replace("api.github.com", "elsewhere.example"),
        SECOND_PAGE.replace("/123/", "/999/"),
        SECOND_PAGE.replace("page=2", "page=3"),
        SECOND_PAGE.replace("per_page=100", "per_page=1"),
    ],
)
def test_next_release_page_must_stay_in_the_exact_repository_and_sequence(next_url) -> None:
    with pytest.raises(RuntimeError, match="expected HTTPS endpoint or page"):
        preconditions.next_page_url(
            f'<{next_url}>; rel="next"',
            current=FIRST_PAGE,
            allowed_paths={"/repos/owner/repo/releases", RELEASES_PATH},
            expected_page=2,
        )


@pytest.mark.parametrize("permissions", [None, {"push": False}, {"push": 1}, {"pull": True}])
def test_pre_tag_namespace_requires_draft_visibility_before_listing(monkeypatch, permissions) -> None:
    def get_json(url, _token, *, api_version):
        assert url == REPOSITORY_URL
        assert api_version == "2022-11-28"
        return {"id": 123, "full_name": REPOSITORY, "permissions": permissions}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    with pytest.raises(RuntimeError, match="repository push access so draft releases are visible"):
        preconditions.require_unused_namespace(API_ROOT, REPOSITORY, RELEASE_TAG, "fixture", require_push=True)


@pytest.mark.parametrize(("exact_status", "symbolic_status", "inventory", "error"), [
    (0, None, None, "already exists"),
    (1, None, None, "could not establish"),
    (2, None, (0, "", ""), None),
    (2, None, (0, f"refs/tags/{RELEASE_TAG}/preview\n", ""), f"namespace for {RELEASE_TAG} is occupied"),
    (2, None, (128, "", ""), "could not establish"),
    (2, None, (0, "", "warning: ignoring broken ref"), "could not establish"),
    (2, None, (0, "refs/tags/other\n", ""), "could not establish"),
    (129, 1, (0, "", ""), None),
    (129, 1, (0, f"refs/tags/{RELEASE_TAG}\n", ""), "already exists"),
    (129, 0, None, "already exists"),
    (129, 128, None, "could not establish"),
])
def test_local_pre_tag_requires_matching_head_and_definite_tag_absence(
    monkeypatch, exact_status, symbolic_status, inventory, error,
) -> None:
    tag_ref = f"refs/tags/{RELEASE_TAG}"
    responses = [
        (("rev-parse", "--verify", "HEAD^{commit}"), CompletedProcess([], 0, RELEASE_SHA + "\n")),
        (("show-ref", "--exists", tag_ref), CompletedProcess([], exact_status, "")),
    ]
    if symbolic_status is not None:
        responses.append((("symbolic-ref", "--quiet", "--no-recurse", tag_ref),
                          CompletedProcess([], symbolic_status, "")))
    if inventory is not None:
        responses.append((("for-each-ref", "--format=%(refname)", "--", tag_ref), CompletedProcess([], *inventory)))

    def run_git(*args):
        expected, response = responses.pop(0)
        assert args == expected
        return response

    monkeypatch.setattr(preconditions, "run_git", run_git)
    if error is None:
        preconditions.check_local_pre_tag_refs(RELEASE_TAG, RELEASE_SHA)
    else:
        with pytest.raises(RuntimeError, match=error):
            preconditions.check_local_pre_tag_refs(RELEASE_TAG, RELEASE_SHA)
    assert not responses


@pytest.mark.parametrize("head_status", [0, 128])
def test_local_pre_tag_rejects_other_head_or_unreadable_checkout(monkeypatch, head_status) -> None:
    def run_git(*args):
        assert args == ("rev-parse", "--verify", "HEAD^{commit}")
        return CompletedProcess([], head_status, "b" * 40 + "\n")

    monkeypatch.setattr(preconditions, "run_git", run_git)
    with pytest.raises(RuntimeError, match="HEAD must match the selected SHA"):
        preconditions.check_local_pre_tag_refs(RELEASE_TAG, RELEASE_SHA)


@pytest.mark.parametrize("outcome", ["tip", "ancestor", "unrelated", "unknown", "existing-tag", "nested-tag", "unreachable", "bad-ref"])
def test_remote_pre_tag_binds_qualified_history_without_accepting_an_existing_tag(monkeypatch, outcome) -> None:
    branch = "refs/heads/main"
    tag_ref = f"refs/tags/{RELEASE_TAG}"
    live_tip = RELEASE_SHA if outcome == "tip" else "b" * 40
    stdout = f"{live_tip}\t{branch}\n"
    if outcome == "existing-tag":
        stdout += f"{RELEASE_SHA}\t{tag_ref}\n"
    if outcome == "nested-tag":
        stdout += f"{RELEASE_SHA}\t{tag_ref}/preview\n"
    if outcome == "bad-ref":
        stdout = "wrong format\n"
    errors = {
        "unrelated": "must be on remote main",
        "unknown": "could not verify remote main ancestry",
        "existing-tag": "remote tag .* already exists",
        "nested-tag": "remote tag namespace .* is occupied",
        "unreachable": "could not verify the remote branch",
        "bad-ref": "could not identify the live main commit",
    }

    def run_git(*args):
        if args[0] == "ls-remote":
            assert args == (
                "ls-remote", "--exit-code", "--refs", "--", f"https://github.com/{REPOSITORY}.git",
                branch, tag_ref, f"{tag_ref}/*",
            )
            return CompletedProcess([], 128 if outcome == "unreachable" else 0, stdout)
        assert args == ("merge-base", "--is-ancestor", RELEASE_SHA, live_tip)
        assert outcome in {"ancestor", "unrelated", "unknown"}
        return CompletedProcess([], {"ancestor": 0, "unrelated": 1, "unknown": 128}[outcome], "")

    monkeypatch.setattr(preconditions, "run_git", run_git)
    if outcome in errors:
        with pytest.raises(RuntimeError, match=errors[outcome]):
            preconditions.check_remote_pre_tag_refs(REPOSITORY, RELEASE_TAG, RELEASE_SHA)
    else:
        preconditions.check_remote_pre_tag_refs(REPOSITORY, RELEASE_TAG, RELEASE_SHA)


@pytest.mark.parametrize(("tag_created_during_audit", "signing_ready", "bundle_changed"), [
    (False, True, False), (True, True, False), (False, False, False), (False, True, True),
])
def test_pre_tag_cli_keeps_checks_source_bound_and_rechecks_refs(
    monkeypatch, capsys, tag_created_during_audit, signing_ready, bundle_changed,
) -> None:
    calls = []
    staging_dirs = []
    coordinates = ("--repository", REPOSITORY, "--branch", "main")
    monkeypatch.setenv("GITHUB_API_URL", API_ROOT)
    monkeypatch.setenv("GITHUB_TOKEN", "namespace-token")
    monkeypatch.setenv("GH_TOKEN", "governance-token")
    monkeypatch.setenv("ROW_RELEASE_SIGNING_INVENTORY_TOKEN", "signing-token")
    monkeypatch.setenv("ROW_RELEASE_IMMUTABILITY_TOKEN", "immutability-token")
    monkeypatch.setenv("ROW_PLATFORM_RUNNER_INVENTORY_TOKEN", "runner-token")
    monkeypatch.setattr(preconditions, "check_local_pre_tag_refs", lambda *args: calls.append(("local", *args)))

    def check_remote(*args):
        event = ("remote", *args)
        if event in calls and tag_created_during_audit:
            raise RuntimeError("remote tag created during audit")
        calls.append(event)

    def check_script(script, *args, env=None):
        if script == "stage_debian_server_bundle.py":
            output = Path(args[-1])
            assert output.name == "verified" and output.parent.is_dir() and not output.exists()
            staging_dirs.append(output.parent)
            calls.append((script, *args[:-1]))
        else:
            calls.append((script, *args))
        if script == "check_platform_evidence_runner_readiness.py":
            assert env["GH_TOKEN"] == "runner-token"
        else:
            assert env is None

    def check_signing(*args):
        calls.append(("signing", *args))
        if not signing_ready:
            raise RuntimeError("missing signing secrets in the release environment")

    def read_bundle(*args):
        event = ("read-bundle", *args)
        changed = event in calls and bundle_changed
        calls.append(event)
        return ("43" if changed else "42"), BUNDLE_SHA

    monkeypatch.setattr(preconditions, "check_remote_pre_tag_refs", check_remote)
    monkeypatch.setattr(preconditions, "run_release_check", check_script)
    monkeypatch.setattr(preconditions, "require_immutable_enabled", lambda *args: calls.append(("immutable", *args)))
    monkeypatch.setattr(preconditions, "require_deployment_environment_policies", lambda *args: calls.append(("environments", *args)))
    monkeypatch.setattr(preconditions, "require_signing_secret_inventory", check_signing)
    monkeypatch.setattr(preconditions, "require_parity_environment_readiness",
                        lambda *args, variable_token: calls.append(("parity", *args, variable_token)))
    monkeypatch.setattr(preconditions, "read_debian_server_bundle_selection", read_bundle)
    monkeypatch.setattr(preconditions, "require_environment_secret_inventory", lambda *args: calls.append(("environment-secrets", *args)))
    monkeypatch.setattr(preconditions, "require_unused_namespace", lambda *args, require_push: calls.append(("namespace", *args, require_push)))

    result = preconditions.main(["pre-tag", "--repository", REPOSITORY, "--tag", RELEASE_TAG, "--sha", RELEASE_SHA])

    expected = [
        ("local", RELEASE_TAG, RELEASE_SHA),
        ("check_repository_cleanup.py", "--require-clean"),
        ("check_release_version.py", "--release-tag", RELEASE_TAG),
        ("check_release_maturity.py", "--release-tag", RELEASE_TAG),
        ("check_release_license_compliance.py", "--check-policy-only"),
        ("remote", REPOSITORY, RELEASE_TAG, RELEASE_SHA),
        ("immutable", API_ROOT, REPOSITORY, "immutability-token"),
        ("environments", API_ROOT, REPOSITORY, "namespace-token"),
        ("signing", API_ROOT, REPOSITORY, "signing-token"),
    ]
    captured = capsys.readouterr()
    if not signing_ready:
        assert result == 1
        assert "missing signing secrets in the release environment" in captured.err
        assert captured.out == ""
        assert calls == expected
        return

    expected += [
        ("environment-secrets", API_ROOT, REPOSITORY, "release-compliance-review", {"ROW_RELEASE_IMMUTABILITY_TOKEN"}, "signing-token"),
        ("environment-secrets", API_ROOT, REPOSITORY, "platform-evidence", {"ROW_PLATFORM_RUNNER_INVENTORY_TOKEN"}, "signing-token"),
        ("parity", API_ROOT, REPOSITORY, RELEASE_TAG, "namespace-token", "signing-token"),
        ("read-bundle", API_ROOT, REPOSITORY, RELEASE_TAG, "signing-token"),
        ("stage_debian_server_bundle.py", "--repository", REPOSITORY, "--artifact-id", "42",
         "--sha256", BUNDLE_SHA, "--target", "linux-x86_64", "--out"),
        ("check_python315_ci_evidence.py", *coordinates, "--sha", RELEASE_SHA),
        ("check_repository_governance.py", *coordinates, "--sha", RELEASE_SHA),
        ("check_repository_governance.py", *coordinates, "--release-tag", RELEASE_TAG),
        ("check_platform_evidence_runner_readiness.py", "--repository", REPOSITORY, "--require-goal-targets", "--require-idle"),
        ("namespace", API_ROOT, REPOSITORY, RELEASE_TAG, "namespace-token", True),
    ]
    assert len(staging_dirs) == 1 and not staging_dirs[0].exists()
    if tag_created_during_audit:
        assert result == 1
        assert "remote tag created during audit" in captured.err
        assert captured.out == ""
    else:
        expected.extend([
            ("remote", REPOSITORY, RELEASE_TAG, RELEASE_SHA),
            ("read-bundle", API_ROOT, REPOSITORY, RELEASE_TAG, "signing-token"),
        ])
        if bundle_changed:
            assert result == 1 and "changed during the pre-tag check" in captured.err
            assert captured.out == ""
        else:
            expected.extend([
                ("check_repository_cleanup.py", "--require-clean"),
                ("local", RELEASE_TAG, RELEASE_SHA),
            ])
            assert result == 0
            assert f"{REPOSITORY}@{RELEASE_SHA} and {RELEASE_TAG}" in captured.out
    assert calls == expected

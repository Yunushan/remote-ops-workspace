"""Hosted toolchain qualification. No product/Chrome/Playwright launch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import socket
import stat
import sys
import time
import urllib.request
from pathlib import Path

import hosted_controller as H
import observe_public_stack as O

HERE = Path(__file__).resolve().parent
WORKFLOW = ".github/workflows/android-toolchain-qualification.yml"
REPORT = "build/mobile-browser/android-toolchain-qualification.json"
BOOTSTRAP = ".tmp/android-sdk-bootstrap-observation.json"
FIXED_SOURCE_SDK = Path("/usr/local/lib/android/sdk")


def event_guard(root):
    # Qualification accepts head checkout distinct from the PR merge event.
    # Actual browser H.host_guard stays dispatch-only and is not weakened.
    expected = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64",
                "GITHUB_REPOSITORY": "Yunushan/remote-ops-workspace", "ROW_EXPECTED_HEAD": H.SOURCE,
                "GITHUB_SERVER_URL": "https://github.com", "GITHUB_API_URL": "https://api.github.com"}
    ref = os.environ.get("GITHUB_REF", "")
    if (any(os.environ.get(key) != value for key, value in expected.items()) or platform.system() != "Linux" or platform.machine() != "x86_64"
            or root.is_symlink() or root.resolve() != root or Path(os.environ.get("GITHUB_WORKSPACE", "")).resolve() != root
            or any(re.fullmatch(r"[0-9a-f]{40}", value or "") is None for value in (H.SOURCE, os.environ.get("GITHUB_SHA"), os.environ.get("GITHUB_WORKFLOW_SHA")))
            or any(re.fullmatch(r"[1-9][0-9]{0,19}", os.environ.get(key, "")) is None for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
            or platform.python_version() != "3.14.7" or platform.python_implementation() != "CPython"):
        raise H.Refusal("actual-public-current-qualification-workflow-required")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise H.Refusal("qualification-duplicate-event-field")
            value[key] = item
        return value
    event = json.loads(H.read_plain(Path(os.environ.get("GITHUB_EVENT_PATH", "")), 2 * 1024 * 1024), object_pairs_hook=unique)
    repository = event.get("repository") if isinstance(event, dict) else None
    if not isinstance(repository, dict) or repository.get("full_name") != "Yunushan/remote-ops-workspace" or repository.get("private") is not False:
        raise H.Refusal("public-same-repository-qualification-required")
    kind = os.environ.get("GITHUB_EVENT_NAME")
    if kind == "pull_request":
        pr, number = event.get("pull_request"), event.get("number")
        if not isinstance(pr, dict) or type(number) is not int or not 0 < number <= 2147483647:
            raise H.Refusal("qualification-same-repository-pr-required")
        head, base = pr.get("head"), pr.get("base")
        if (event.get("action") not in {"opened", "synchronize", "reopened"} or not isinstance(head, dict) or not isinstance(base, dict)
                or any(not isinstance(row.get("repo"), dict) or row["repo"].get("full_name") != "Yunushan/remote-ops-workspace" or row["repo"].get("private") is not False for row in (head, base))
                or head.get("sha") != H.SOURCE or base.get("ref") != "main" or re.fullmatch(r"[0-9a-f]{40}", base.get("sha", "")) is None
                or ref != f"refs/pull/{number}/merge"):
            raise H.Refusal("qualification-same-repository-pr-required")
    elif kind == "workflow_dispatch":
        if (os.environ["GITHUB_SHA"] != H.SOURCE or os.environ["GITHUB_WORKFLOW_SHA"] != H.SOURCE
                or re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9_./-]{0,199}", ref) is None
                or ".." in ref or "//" in ref or ref.endswith(("/", "."))):
            raise H.Refusal("qualification-current-branch-dispatch-required")
    else:
        raise H.Refusal("qualification-event-refused")
    if os.environ.get("GITHUB_WORKFLOW_REF") != "Yunushan/remote-ops-workspace/" + WORKFLOW + "@" + ref:
        raise H.Refusal("qualification-actual-workflow-ref-required")
    return {"repository": "Yunushan/remote-ops-workspace", "event": kind, "source_sha": H.SOURCE, "event_sha": os.environ["GITHUB_SHA"],
            "workflow_sha": os.environ["GITHUB_WORKFLOW_SHA"], "workflow_path": WORKFLOW, "ref_sha256": H.sha(ref.encode()),
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]}


def commands(root, leaders):
    started = time.monotonic()
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}

    def short(argv, stdin=None, timeout=30):
        deadline = min(started + 1500, time.monotonic() + timeout)
        if time.monotonic() >= deadline:
            raise H.Refusal("qualification-command-original-budget")
        leader = H.Managed(argv, env, root)
        leaders.append(leader)
        if stdin is not None:
            leader.child.stdin.write(stdin)
            leader.child.stdin.flush()
        leader.child.stdin.close()
        leader.zero(deadline)
        if leader.buffers[1]:
            raise H.Refusal("qualification-command-stderr")
        return bytes(leader.buffers[0])
    short.remaining = lambda: 1500 - (time.monotonic() - started)
    return short, started


def source_binding(root, short):
    execution = event_guard(root)
    if short(["git", "rev-parse", "HEAD"]).strip().decode("ascii") != H.SOURCE or short(["git", "status", "--porcelain", "--untracked-files=no"]):
        raise H.Refusal("qualification-clean-exact-source-required")
    tree = short(["git", "rev-parse", "HEAD^{tree}"]).strip().decode("ascii")
    if re.fullmatch(r"[0-9a-f]{40}", tree) is None:
        raise H.Refusal("qualification-current-tree-required")
    relative = HERE.relative_to(root).as_posix()
    hashes = {}
    for name in ("qualify_android_stack.py", "hosted_controller.py", "observe_public_stack.py", "archive_readers_frozen.py"):
        raw = H.read_plain(HERE / name, 262144)
        if short(["git", "show", H.SOURCE + ":" + relative + "/" + name]) != raw:
            raise H.Refusal("qualification-tracked-helper-bytes-required")
        hashes[name] = H.sha(raw)
    workflow = H.read_plain(root / WORKFLOW, 131072)
    if short(["git", "show", H.SOURCE + ":" + WORKFLOW]) != workflow:
        raise H.Refusal("qualification-executed-workflow-bytes-required")
    executed = executed_workflow(execution, workflow, getattr(short, "remaining", lambda: 0))
    return {"source_sha": H.SOURCE, "source_tree": tree, "helpers": hashes, "workflow_sha256": H.sha(workflow),
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"], "execution": execution,
            "executed_workflow": executed}


def executed_workflow(execution, expected_raw, remaining, clock=time.monotonic):
    # Fixed immutable public URL only; no ambient authentication/proxy/redirect.
    if (re.fullmatch(r"[0-9a-f]{40}", execution.get("workflow_sha", "")) is None or execution.get("workflow_path") != WORKFLOW
            or not isinstance(expected_raw, bytes) or not 0 < len(expected_raw) <= 131072):
        raise H.Refusal("qualification-workflow-input-required")
    started = clock()
    deadline = started + min(60, remaining())
    if deadline <= started:
        raise H.Refusal("qualification-workflow-original-budget")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            raise H.Refusal("qualification-workflow-redirect-refused")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    url = "https://raw.githubusercontent.com/Yunushan/remote-ops-workspace/" + execution["workflow_sha"] + "/" + WORKFLOW
    request = urllib.request.Request(url, headers={"Accept": "text/plain", "User-Agent": "ROW-public-qualification"})
    with opener.open(request, timeout=min(20, deadline - started)) as response:
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            raise H.Refusal("qualification-workflow-response-layout")
        length = response.headers.get("Content-Length")
        if length is not None and (re.fullmatch(r"[1-9][0-9]{0,9}", length) is None or int(length) > 131072):
            raise H.Refusal("qualification-workflow-content-bound")
        raw = bytearray()
        while True:
            if clock() >= deadline or remaining() <= 0:
                raise H.Refusal("qualification-workflow-byte-or-time-bound")
            chunk = response.read(min(65536, 131073 - len(raw)))
            if clock() >= deadline or remaining() <= 0:
                raise H.Refusal("qualification-workflow-byte-or-time-bound")
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > 131072:
                raise H.Refusal("qualification-workflow-byte-or-time-bound")
        if clock() >= deadline or remaining() <= 0 or (length is not None and len(raw) != int(length)) or bytes(raw) != expected_raw:
            raise H.Refusal("qualification-actual-executed-workflow-mismatch-or-late")
    return {"workflow_sha": execution["workflow_sha"], "size_bytes": len(raw), "sha256": H.sha(raw), "source_contract_matches": True, "redirects": 0}


def observe_public(root):
    event_guard(root)  # Before any public acquisition; supports exact PR head checkout.
    leaders = []
    try:
        short, _started = commands(root, leaders)
        binding = source_binding(root, short)  # Actual executed workflow bytes first.
        return O._observe_bound_source(root, binding, source_check=lambda: source_binding(root, short), remaining=short.remaining)
    finally:
        initial = sys.exc_info()[1]
        if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
            raise H.Refusal("qualification-owned-cleanup-unproved")


def owned_sdk():
    temp = Path(os.environ.get("RUNNER_TEMP", ""))
    if not temp.is_absolute() or temp.resolve() != temp or temp.is_symlink() or temp == Path("/"):
        raise H.Refusal("qualified-owned-runner-temp-required")
    sdk = temp / "row-browser-api36-sdk"
    if sdk.resolve() != sdk or sdk.is_symlink():
        raise H.Refusal("qualified-owned-sdk-path-required")
    return sdk


def owned_bootstrap():
    # The immutable copied executable SDK is distinct from its install target.
    bootstrap_sdk = owned_sdk().parent / "row-browser-api36-bootstrap"
    if bootstrap_sdk.resolve() != bootstrap_sdk or bootstrap_sdk.is_symlink():
        raise H.Refusal("qualified-owned-bootstrap-path-required")
    return bootstrap_sdk


def bootstrap(root):
    event_guard(root)
    leaders = []
    try:
        short, _started = commands(root, leaders)
        binding = source_binding(root, short)
        if os.environ.get("ANDROID_HOME") != str(FIXED_SOURCE_SDK) or FIXED_SOURCE_SDK.resolve() != FIXED_SOURCE_SDK:
            raise H.Refusal("actual-hosted-source-sdk-layout-required")
        if owned_sdk().exists():
            raise H.Refusal("fresh-isolated-sdk-required")
        if owned_bootstrap().exists():
            raise H.Refusal("fresh-isolated-bootstrap-required")
        value = {"schema": "row.android-sdk-bootstrap-observation.v1", "binding": binding,
                 "cmdline_tree_sha256": H.tree_digest(FIXED_SOURCE_SDK / "cmdline-tools/latest", maximum_bytes=512 * 1024 * 1024),
                 "already_present_license_tree_sha256": H.tree_digest(FIXED_SOURCE_SDK / "licenses", maximum_files=128, maximum_bytes=2 * 1024 * 1024),
                 "signing_or_license_approval": False, "readiness_credit": 0}
        O.save(root / BOOTSTRAP, (json.dumps(value, indent=2) + "\n").encode())
        return {"status": "public-hosted-tool-inputs-observed", "bootstrap_sha256": H.sha(H.read_plain(root / BOOTSTRAP, 65536)), "readiness_credit": 0}
    finally:
        initial = sys.exc_info()[1]
        if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
            raise H.Refusal("qualification-owned-cleanup-unproved")


def clone_guard(root, short, binding=None):
    if binding is None:
        binding = source_binding(root, short)
    observation = json.loads(H.read_plain(root / BOOTSTRAP, 65536))
    if (set(observation) != {"schema", "binding", "cmdline_tree_sha256", "already_present_license_tree_sha256", "signing_or_license_approval", "readiness_credit"}
            or observation["schema"] != "row.android-sdk-bootstrap-observation.v1" or observation["binding"] != binding
            or observation["signing_or_license_approval"] is not False or observation["readiness_credit"] != 0):
        raise H.Refusal("exact-current-bootstrap-observation-required")
    sdk = owned_sdk()
    if (H.tree_digest(owned_bootstrap() / "cmdline-tools/latest", maximum_bytes=512 * 1024 * 1024) != H.digest(observation["cmdline_tree_sha256"])
            or H.tree_digest(sdk / "licenses", maximum_files=128, maximum_bytes=2 * 1024 * 1024) != H.digest(observation["already_present_license_tree_sha256"])):
        raise H.Refusal("actual-cloned-tool-bytes-required")
    return binding, observation


SDK_TREE_MAXIMUM_BYTES = 8 * 1024 ** 3  # API36 inventory logical-byte resource budget.
SDK_METADATA_REFUSALS = {
    ('cmdline-tools/latest', 'package.xml'): 'qualification-sdk-metadata-cmdline-package-xml-missing',
    ('cmdline-tools/latest', 'source.properties'): 'qualification-sdk-metadata-cmdline-source-properties-missing',
    ('platform-tools', 'package.xml'): 'qualification-sdk-metadata-platform-tools-package-xml-missing',
    ('platform-tools', 'source.properties'): 'qualification-sdk-metadata-platform-tools-source-properties-missing',
    ('emulator', 'package.xml'): 'qualification-sdk-metadata-emulator-package-xml-missing',
    ('emulator', 'source.properties'): 'qualification-sdk-metadata-emulator-source-properties-missing',
    ('platforms/android-36', 'package.xml'): 'qualification-sdk-metadata-platform-package-xml-missing',
    ('platforms/android-36', 'source.properties'): 'qualification-sdk-metadata-platform-source-properties-missing',
    ('system-images/android-36/google_apis/x86_64', 'package.xml'): 'qualification-sdk-metadata-system-image-package-xml-missing',
    ('system-images/android-36/google_apis/x86_64', 'source.properties'): 'qualification-sdk-metadata-system-image-source-properties-missing',
}

PUBLIC_CAPTURE_REFUSALS = frozenset((
    'actual-api-or-abi-mismatch',
    'actual-apk-digest-layout',
    'actual-apk-path-inventory-unobserved',
    'actual-apk-size-layout',
    'actual-browser-or-library-bytes-changed',
    'actual-cloned-tool-bytes-required',
    'actual-current-tree-unobserved',
    'actual-git-fixture-bytes-mismatch',
    'actual-hosted-source-sdk-layout-required',
    'actual-isolated-sdk-environment-required',
    'actual-official-host-source-run-required',
    'actual-package-version-unobserved',
    'actual-pinned-npm-tree-required',
    'actual-public-current-qualification-workflow-required',
    'actual-qualified-sdk-tree-required',
    'actual-supported-chrome-required',
    'actual-synthetic-screenshot-binding',
    'actual-tracked-controller-byte-mismatch',
    'adb-fixed-service-bound',
    'adb-forward-exact-port-layout',
    'adb-forward-status-required',
    'adb-framed-unaccounted-tail',
    'adb-late-completed-command',
    'adb-original-command-deadline',
    'adb-output-bound',
    'adb-response-bound',
    'adb-service-refused',
    'adb-shell-v2-nonzero-stderr-or-type',
    'adb-shell-v2-packet-layout',
    'adb-shell-v2-payload-bound',
    'adb-shell-v2-total-bound',
    'adb-shell-v2-zero-exit-unproved',
    'adb-truncated-service',
    'apk-path-bound',
    'apk-path-layout',
    'browser-control-sequence-or-nonce',
    'clean-exact-source-required',
    'clean-owned-forward-namespace-required',
    'complete-nonce-source-browser-result-required',
    'control-bound',
    'current-source-binding-changed',
    'exact-current-bootstrap-observation-required',
    'exact-known-asset-row-required',
    'fixture-listener-remains-after-owned-exit',
    'foreign-device-namespace',
    'fresh-isolated-bootstrap-required',
    'fresh-isolated-sdk-required',
    'input-identity-changed',
    'late-device-connect',
    'late-emulator-boot',
    'late-nonzero-or-unbounded-completion',
    'late-owned-adb-listener',
    'original-device-connect-deadline',
    'original-emulator-boot-deadline',
    'original-owned-adb-listener-deadline',
    'owned-cleanup-error',
    'owned-cleanup-unproved',
    'owned-descriptor-bound',
    'owned-event-deadline',
    'owned-event-deadline-or-bound',
    'owned-event-late-or-unbounded',
    'owned-event-missing-before-exit',
    'owned-final-cleanup-unproved',
    'owned-fixture-readiness-mismatch',
    'owned-host-character-kvm-identity-required',
    'owned-host-kvm-stable-identity-required',
    'owned-leader-or-pipe-unavailable',
    'owned-listener-identity-required',
    'owned-loopback-listener-missing',
    'owned-loopback-listener-unproved',
    'owned-pending-release-ack',
    'owned-pipe-lifetime-unproved',
    'owned-private-parent-required',
    'owned-reap-unproved',
    'owned-socket-table-bound',
    'owned-socket-table-layout',
    'owned-zero-exit-timeout',
    'plain-bounded-input-required',
    'public-output-parent-containment',
    'public-result-bound',
    'public-same-repository-qualification-required',
    'qualification-actual-executed-workflow-mismatch-or-late',
    'qualification-actual-workflow-ref-required',
    'qualification-adb-listener-deadline',
    'qualification-api-or-abi-mismatch',
    'qualification-boot-deadline',
    'qualification-clean-exact-source-required',
    'qualification-command-original-budget',
    'qualification-command-stderr',
    'qualification-current-branch-dispatch-required',
    'qualification-current-source-changed',
    'qualification-current-source-tool-or-device-changed',
    'qualification-current-tree-required',
    'qualification-device-deadline',
    'qualification-duplicate-event-field',
    'qualification-event-refused',
    'qualification-executed-workflow-bytes-required',
    'qualification-foreign-device',
    'qualification-late-adb-listener',
    'qualification-late-boot',
    'qualification-late-device',
    'qualification-owned-cleanup-unproved',
    'qualification-private-parent-required',
    'qualification-public-receipt-bound',
    'qualification-runner-output-changed',
    'qualification-runner-output-required',
    'qualification-same-repository-pr-required',
    'qualification-sdk-metadata-cmdline-package-xml-missing',
    'qualification-sdk-metadata-cmdline-source-properties-missing',
    'qualification-sdk-metadata-emulator-package-xml-missing',
    'qualification-sdk-metadata-emulator-source-properties-missing',
    'qualification-sdk-metadata-platform-package-xml-missing',
    'qualification-sdk-metadata-platform-source-properties-missing',
    'qualification-sdk-metadata-platform-tools-package-xml-missing',
    'qualification-sdk-metadata-platform-tools-source-properties-missing',
    'qualification-sdk-metadata-system-image-package-xml-missing',
    'qualification-sdk-metadata-system-image-source-properties-missing',
    'qualification-tracked-helper-bytes-required',
    'qualification-workflow-byte-or-time-bound',
    'qualification-workflow-content-bound',
    'qualification-workflow-input-required',
    'qualification-workflow-original-budget',
    'qualification-workflow-redirect-refused',
    'qualification-workflow-response-layout',
    'qualified-owned-bootstrap-path-required',
    'qualified-owned-runner-temp-required',
    'qualified-owned-sdk-path-required',
    'qualified-tool-bytes-mismatch',
    'qualified-tool-identity-required',
    'qualified-tool-inventory-required',
    'source-manifest-mismatch',
    'source-or-pins-changed-after-browser',
    'stack-source-or-version-mismatch',
    'tree-file-identity-changed',
    'tree-file-size-changed',
    'tree-hardlink',
    'tree-node-bound',
    'tree-node-bound-or-link',
    'tree-root-alias',
    'tree-total-byte-bound',
    'tree-unsupported-type',
    'unexpected-private-command-stderr',
    'unobserved-exact-digest',
    'unowned-package-probe',
    'unqualified-stack-schema',
))
CAPTURE_PHASES = frozenset(('bootstrap-and-cloned-sdk', 'sdk-observation', 'owned-api36-emulator', 'chrome-static-device-inventory'))


def sdk_tree_limit_diagnostic(exc):
    value = exc.__dict__.get("tree_limit_observation")
    keys = ("component", "sampled_stat_bytes", "maximum_bytes", "file_stat_bytes",
            "sampled_nodes", "maximum_nodes", "complete", "file_digest_observed")
    if (type(value) is not dict or len(value) != len(keys)
            or any(type(key) is not str for key in value) or set(value) != set(keys)):
        return None
    component = value["component"]
    if (type(component) is not str or component not in
            ("cmdline-tools", "platform-tools", "emulator", "platform-api36",
             "system-image-api36-x86-64", "licenses", "other")):
        return None
    for key in ("sampled_stat_bytes", "maximum_bytes", "file_stat_bytes", "sampled_nodes", "maximum_nodes"):
        if type(value[key]) is not int or not 0 <= value[key] <= 2 ** 64 - 1:
            return None
    total, maximum, size = value["sampled_stat_bytes"], value["maximum_bytes"], value["file_stat_bytes"]
    if (maximum != SDK_TREE_MAXIMUM_BYTES or value["maximum_nodes"] != 30000
            or not 1 <= value["sampled_nodes"] <= 30000 or not 0 < size <= total
            or total <= maximum or total - size > maximum
            or value["complete"] is not False or value["file_digest_observed"] is not False):
        return None
    return {key: value[key] for key in keys}


OWNED_PROCESS_SUBSTAGES = frozenset((
    "avd-create", "port-reservation", "adb-birth", "adb-listener",
    "emulator-birth", "device-connect", "emulator-boot", "device-identity",
))


def owned_process_diagnostic(exc):
    value = exc.__dict__.get("owned_process_observation")
    keys = ("role", "reason", "pipe_failed", "poll_observed", "exit_status",
            "stdout_retained_bytes", "stderr_retained_bytes", "counts_partial")
    if (type(value) is not dict or len(value) not in (len(keys), len(keys) + 1)
            or any(type(key) is not str for key in value)
            or set(value) not in (set(keys), set(keys) | {"adb_message_bits"})):
        return None
    if (type(value["role"]) is not str or value["role"] not in ("adb", "emulator")
            or type(value["reason"]) is not str or value["reason"] not in ("pipe-failed", "leader-exited")
            or type(value["pipe_failed"]) is not bool or type(value["poll_observed"]) is not bool
            or value["counts_partial"] is not True):
        return None
    for key, maximum in (("stdout_retained_bytes", 4 * 1024 * 1024),
                         ("stderr_retained_bytes", 1024 * 1024)):
        if type(value[key]) is not int or not 0 <= value[key] <= maximum:
            return None
    if value["pipe_failed"]:
        if value["reason"] != "pipe-failed" or value["poll_observed"] or value["exit_status"] is not None:
            return None
    elif (value["reason"] != "leader-exited" or not value["poll_observed"]
          or type(value["exit_status"]) is not int or not -(2 ** 31) <= value["exit_status"] < 2 ** 31):
        return None
    observed = {key: value[key] for key in keys}
    if "adb_message_bits" in value:
        bits = value["adb_message_bits"]
        if (type(bits) is not int or not 0 <= bits <= 31
                or value["role"] != "adb" or value["reason"] != "leader-exited"
                or value["pipe_failed"] or not value["poll_observed"]
                or type(value["exit_status"]) is not int or value["exit_status"] != -6):
            return None
        observed["adb_message_bits"] = bits
    return observed


INVENTORY_QUERY_TAGS = (
    "chrome-package-dump", "chrome-package-paths", "chrome-apk-sha256",
    "chrome-apk-stat", "device-unix-sockets",
)


def inventory_query_tag_diagnostic(exc):
    """Independent closed optional tag; never a raw query, path or output."""
    try:
        if (type(exc) is H.Refusal and type(exc.args) is tuple
                and exc.args == ("adb-output-bound",)):
            value = exc.__dict__.get("adb_query_tag")
            if type(value) is str and len(value) <= 32 and value in INVENTORY_QUERY_TAGS:
                return value
    except BaseException:
        pass
    return None


def chrome_version_shape_diagnostic(exc):
    """Independent closed lexical buckets; no values, messages or raw dump."""
    try:
        if (type(exc) is not H.Refusal or type(exc.args) is not tuple
                or exc.args != ("actual-package-version-unobserved",)):
            return None
        state = exc.__dict__
        if type(state) is not dict:
            return None
        value = state.get("chrome_version_shape")
        keys = ("name_matches", "code_matches", "name_labels", "code_labels")
        if (type(value) is not dict or len(value) != len(keys)
                or any(type(key) is not str for key in value) or set(value) != set(keys)):
            return None
        if any(type(value[key]) is not int or not 0 <= value[key] <= 2 for key in keys):
            return None
        if (value["name_matches"] > value["name_labels"]
                or value["code_matches"] > value["code_labels"]
                or (value["name_matches"] == 1 and value["code_matches"] == 1)):
            return None
        return {key: value[key] for key in keys}
    except BaseException:
        pass
    return None


CHROME_PARSER_CHECKS = ("input-shape", "ascii-controls", "block-fields", "block-unique", "section-title",
    "active-order", "hidden-order", "renamed-compat", "package-header", "package-position",
    "version-position", "version-line", "version-name-unique", "version-code-unique",
    "field-position", "active-final", "hidden-final")
CHROME_PARSER_SCOPES = ("active", "hidden", "unobserved")
CHROME_HEADER_KINDS = ("target-spacing", "target-identity", "target-suffix", "foreign-header",
    "keyword-title", "keyword-prefix", "embedded-header", "over-bound", "other-candidate")
CHROME_KEYWORD_CONTEXTS = ('before-active-bare', 'before-active-horizontal-bracket', 'before-active-horizontal-word', 'before-active-horizontal-other', 'before-active-colon', 'before-active-equals', 'before-active-bracket', 'before-active-other-punctuation', 'after-active-bare', 'after-active-horizontal-bracket', 'after-active-horizontal-word', 'after-active-horizontal-other', 'after-active-colon', 'after-active-equals', 'after-active-bracket', 'after-active-other-punctuation')


def chrome_parser_check_diagnostic(exc):
    """Closed current-attempt check/scope/category/context; never raw header or cause."""
    try:
        token = H._chrome_parser_current_token
        if (type(token) is not object or type(exc) is not H.Refusal or type(exc.args) is not tuple
                or exc.args != ("actual-package-version-unobserved",)):
            return None
        state = exc.__dict__
        if type(state) is not dict:
            return None
        value = state.get("chrome_parser_check")
        if (type(value) is not dict or len(value) not in (4, 5, 6) or any(type(key) is not str for key in value)
                or set(value) not in ({"attempt_token", "selected_error", "check", "scope"},
                                     {"attempt_token", "selected_error", "check", "scope", "header_kind"},
                                     {"attempt_token", "selected_error", "check", "scope", "header_kind", "keyword_context"})
                or value["attempt_token"] is not token or value["selected_error"] is not exc):
            return None
        check, scope = value["check"], value["scope"]
        if (type(check) is not str or check not in CHROME_PARSER_CHECKS
                or type(scope) is not str or scope not in CHROME_PARSER_SCOPES):
            return None
        result = {"check": check, "scope": scope}
        if "header_kind" in value:
            kind = value["header_kind"]
            if check != "package-header" or type(kind) is not str or kind not in CHROME_HEADER_KINDS:
                return None
            result["header_kind"] = kind
        if "keyword_context" in value:
            context = value["keyword_context"]
            if (check != "package-header" or result.get("header_kind") != "keyword-prefix"
                    or type(context) is not str or context not in CHROME_KEYWORD_CONTEXTS
                    or (scope in ("active", "hidden") and not context.startswith("after-active-"))):
                return None
            result["keyword_context"] = context
        if H._chrome_parser_current_token is not token:
            return None
        return result
    except BaseException:
        pass
    return None


def capture_refusal_diagnostic(exc, phase, owned_substage=None):
    code = "unclassified"
    if type(exc) is H.Refusal and len(exc.args) == 1:
        value = exc.args[0]
        if type(value) is str and len(value) <= 128 and value in PUBLIC_CAPTURE_REFUSALS:
            code = value
    elif type(exc) is FileNotFoundError:
        code = "missing-input"
    elif type(exc) is PermissionError:
        code = "input-access-refused"
    if type(phase) is not str or phase not in CAPTURE_PHASES:
        phase = "unobserved"
    record = {"schema": "row.android-capture-refusal.v1", "status": "refused",
              "phase": phase, "refusal_code": code, "approval": False, "readiness_credit": 0}
    if phase == "owned-api36-emulator":
        if type(owned_substage) is str and owned_substage in OWNED_PROCESS_SUBSTAGES:
            record["owned_substage"] = owned_substage
        if (type(exc) in (H.Refusal, FileNotFoundError, PermissionError)
                and code in ("missing-input", "input-access-refused",
                             "owned-leader-or-pipe-unavailable", "owned-listener-identity-required",
                             "owned-descriptor-bound", "owned-socket-table-bound",
                             "owned-socket-table-layout", "owned-loopback-listener-missing",
                             "owned-loopback-listener-unproved")):
            entered = exc.__dict__.get("owned_listener_stage")
            if type(entered) is str and len(entered) <= 32 and entered in H.OWNED_LISTENER_STAGES:
                record["owned_listener_stage"] = entered
        if code == "owned-leader-or-pipe-unavailable":
            observed = owned_process_diagnostic(exc)
            if observed is not None:
                record["owned_process"] = observed
    if code == "adb-output-bound" and phase == "chrome-static-device-inventory":
        observed = inventory_query_tag_diagnostic(exc)
        if observed is not None:
            record["adb_query_tag"] = observed
    if code == "actual-package-version-unobserved" and phase == "chrome-static-device-inventory":
        observed = chrome_version_shape_diagnostic(exc)
        if observed is not None:
            record["chrome_version_shape"] = observed
        try:
            parser_check = chrome_parser_check_diagnostic(exc)
            if parser_check is not None:
                record["chrome_parser_check"] = parser_check
        except BaseException:
            pass
    if code == "tree-total-byte-bound" and phase == "sdk-observation":
        observed = sdk_tree_limit_diagnostic(exc)
        if observed is not None:
            record["sdk_tree_limit"] = observed
    return record


def sdk_inventory(sdk):
    metadata = []
    prefixes = ("cmdline-tools/latest", "platform-tools", "emulator", "platforms/android-36", "system-images/android-36/google_apis/x86_64")
    for prefix in prefixes:
        for name in ("package.xml", "source.properties"):
            try:
                raw = H.read_plain(sdk / prefix / name, 512 * 1024)
            except FileNotFoundError:
                raise H.Refusal(SDK_METADATA_REFUSALS[(prefix, name)]) from None
            row = {"component": prefix, "file": name, "bytes": len(raw), "sha256": H.sha(raw)}
            if name == "source.properties":
                values = re.findall(rb"^Pkg\.Revision\s*=\s*([0-9]+(?:\.[0-9]+){0,3}(?:[- ](?:beta|rc)[0-9]*)?)\s*$", raw, re.MULTILINE)
                row["revision"] = values[0].decode("ascii") if len(values) == 1 and len(values[0]) <= 64 else "unobserved-format"
            metadata.append(row)
    tools = []
    for name, relative in (("adb", "platform-tools/adb"), ("emulator", "emulator/emulator"), ("avdmanager", "cmdline-tools/latest/bin/avdmanager"), ("sdkmanager", "cmdline-tools/latest/bin/sdkmanager")):
        raw = H.read_plain(sdk / relative, 128 * 1024 * 1024)
        tools.append({"tool": name, "bytes": len(raw), "sha256": H.sha(raw)})
    return {"tree_sha256": H.tree_digest(sdk, maximum_files=30000, maximum_bytes=SDK_TREE_MAXIMUM_BYTES), "metadata": metadata, "tools": tools,
            "catalog_approval": False, "license_approval": False, "whole_image_semantic_closure": "not-established"}


def public_receipt(root, record):
    raw = (json.dumps(record, indent=2) + "\n").encode()
    if len(raw) > 131072:
        raise H.Refusal("qualification-public-receipt-bound")
    O.save(root / REPORT, raw)
    marker = Path(os.environ.get("GITHUB_OUTPUT", ""))
    if not marker.is_absolute() or marker.resolve() != marker or any(parent.is_symlink() for parent in marker.parents):
        raise H.Refusal("qualification-runner-output-required")
    before = marker.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 65536:
        raise H.Refusal("qualification-runner-output-required")
    fd = os.open(marker, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "wb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise H.Refusal("qualification-runner-output-changed")
        stream.write(b"public_receipt=saved\n")
        stream.flush()
        after = os.fstat(stream.fileno())
    after_path = marker.lstat()
    if after.st_size != before.st_size + 21 or (after.st_dev, after.st_ino, after.st_size) != (after_path.st_dev, after_path.st_ino, after_path.st_size):
        raise H.Refusal("qualification-runner-output-changed")


def capture(root):
    event_guard(root)
    leaders, context = [], None
    owned_substage = None
    try:
        short, started = commands(root, leaders)
        binding = source_binding(root, short)
        context = {"binding": binding, "phase": "bootstrap-and-cloned-sdk", "observed": {}}
        binding, bootstrap_record = clone_guard(root, short, binding)
        context["phase"] = "sdk-observation"
        sdk = owned_sdk()
        if Path(os.environ.get("ANDROID_HOME", "")) != sdk:
            raise H.Refusal("actual-isolated-sdk-environment-required")
        observed = sdk_inventory(sdk)
        context["observed"]["sdk_tree_sha256"] = observed["tree_sha256"]
        private = root / ".tmp" / ("android-toolchain-owned-" + secrets.token_hex(16))
        if private.parent.resolve() != private.parent:
            raise H.Refusal("qualification-private-parent-required")
        private.mkdir(mode=0o700)
        for name in ("home", "avd", "android-home"):
            (private / name).mkdir(mode=0o700)
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": str(private / "home"),
               "ANDROID_HOME": str(sdk), "ANDROID_SDK_ROOT": str(sdk), "ANDROID_AVD_HOME": str(private / "avd"),
               "ANDROID_USER_HOME": str(private / "android-home"), "ADB_SERVER_SOCKET": "tcp:127.0.0.1:5039", "ANDROID_ADB_SERVER_PORT": "5039",
               "ADB_MDNS_AUTO_CONNECT": "", "ADB_LOCAL_TRANSPORT_MAX_PORT": "5557", "JAVA_HOME": os.environ.get("JAVA_HOME", "")}

        def native(argv, stdin=None, timeout=30):
            deadline = min(started + 1500, time.monotonic() + timeout)
            if time.monotonic() >= deadline:
                raise H.Refusal("qualification-command-original-budget")
            child = H.Managed(argv, env, root)
            leaders.append(child)
            if stdin is not None:
                child.child.stdin.write(stdin)
                child.child.stdin.flush()
            child.child.stdin.close()
            child.zero(deadline)
            if child.buffers[1]:
                raise H.Refusal("qualification-command-stderr")
            return bytes(child.buffers[0])

        context["phase"] = "owned-api36-emulator"
        owned_substage = "avd-create"
        avd = "row-qualification-36-" + secrets.token_hex(8)
        native([str(sdk / "cmdline-tools/latest/bin/avdmanager"), "create", "avd", "-n", avd, "-k", "system-images;android-36;google_apis;x86_64", "--device", "pixel_6"], stdin=b"no\n", timeout=180)
        owned_substage = "port-reservation"
        for port in (H.ADB_PORT, 5556, 5557):
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", port))
        owned_substage = "adb-birth"
        adb_leader = H.Managed([str(sdk / "platform-tools/adb"), "-L", "tcp:localhost:5039", "nodaemon", "server"], env, root)
        leaders.append(adb_leader)
        adb_leader._public_caller_role = "adb"
        owned_substage = "adb-listener"
        ready = time.monotonic() + 10
        while time.monotonic() < ready:
            try:
                H.owned_listener(adb_leader, H.ADB_PORT)
                if time.monotonic() >= ready:
                    raise H.Refusal("qualification-late-adb-listener")
                break
            except H.Refusal as exc:
                if str(exc) != "owned-loopback-listener-missing":
                    raise
            time.sleep(0.1)
        else:
            raise H.Refusal("qualification-adb-listener-deadline")
        owned_substage = "emulator-birth"
        emulator = H.Managed([str(sdk / "emulator/emulator"), "-avd", avd, "-port", "5556", "-no-window", "-gpu", "swiftshader_indirect", "-no-snapshot", "-no-snapshot-load", "-no-snapshot-save", "-noaudio", "-no-boot-anim", "-camera-back", "none", "-no-metrics"], env, root)
        leaders.append(emulator)
        emulator._public_caller_role = "emulator"
        adb = H.AdbSocket(adb_leader)
        owned_substage = "device-connect"
        connected = time.monotonic() + 180
        while time.monotonic() < connected:
            emulator.live()
            rows = adb.command("host:devices", framed=True, timeout=min(30, connected - time.monotonic())).decode("ascii").splitlines()
            if time.monotonic() >= connected:
                raise H.Refusal("qualification-late-device")
            if rows == [H.SERIAL + "\tdevice"]:
                break
            if any(row and row.split("\t")[0] != H.SERIAL for row in rows):
                raise H.Refusal("qualification-foreign-device")
            time.sleep(0.1)
        else:
            raise H.Refusal("qualification-device-deadline")
        owned_substage = "emulator-boot"
        boot = time.monotonic() + 180
        while time.monotonic() < boot:
            emulator.live()
            value = H.shell_v2(adb.command("shell,v2,raw:getprop sys.boot_completed", transport=True, timeout=min(30, boot - time.monotonic()))).strip()
            if time.monotonic() >= boot:
                raise H.Refusal("qualification-late-boot")
            if value == b"1":
                break
            time.sleep(0.1)
        else:
            raise H.Refusal("qualification-boot-deadline")
        owned_substage = "device-identity"
        if adb.shell("getprop ro.build.version.sdk").strip() != b"36" or adb.shell("getprop ro.product.cpu.abi").strip() != b"x86_64":
            raise H.Refusal("qualification-api-or-abi-mismatch")
        context["phase"] = "chrome-static-device-inventory"
        chrome = H.package_inventory(adb, "com.android.chrome")
        sockets = H.inventory_shell(adb, "cat /proc/net/unix", "device-unix-sockets")
        socket_rows = sockets.decode("ascii").splitlines()
        # No am start, UI command, Playwright require or DevTools connection.
        socket_seen = any(row.split()[-1:] == ["@chrome_devtools_remote"] for row in socket_rows)
        context["observed"]["chrome_apk_count"] = len(chrome["apks"])
        if (source_binding(root, short) != binding or sdk_inventory(sdk) != observed
                or H.package_inventory(adb, "com.android.chrome") != chrome or time.monotonic() >= started + 1500):
            raise H.Refusal("qualification-current-source-tool-or-device-changed")
        cleanup = H.cleanup_all(leaders)
        if any(not row["complete"] for row in cleanup):
            raise H.Refusal("qualification-owned-cleanup-unproved")
        record = {"schema": "row.android-toolchain-qualification.v1", "status": "observations-with-unresolved-browser",
                  "binding": binding, "bootstrap": bootstrap_record, "sdk": observed, "android_api": 36, "serial": H.SERIAL,
                  "chrome": chrome, "devtools_socket_seen_before_launch": socket_seen, "devtools_socket_inventory_sha256": hashlib.sha256(sockets).hexdigest(),
                  "CDP_availability": "not-probed-without-browser-launch", "native_product_or_browser_launch": False,
                  "Playwright_or_NPM_code_execution": False, "Android_helper_APKs": False, "owned_leader_cleanup": cleanup,
                  "process_descendants": "disposable-host-destruction-required", "approval": False, "readiness_credit": 0}
        public_receipt(root, record)
        return {"status": record["status"], "output_sha256": H.sha(H.read_plain(root / REPORT, 131072)), "readiness_credit": 0}
    except Exception as exc:
        try:
            diagnostic = capture_refusal_diagnostic(exc, context["phase"] if context is not None else None, owned_substage)
            line = json.dumps(diagnostic, ensure_ascii=True, separators=(",", ":"))
            if len(line) <= 512:
                print(line, file=sys.stderr)
        except BaseException:
            pass
        if context is not None:
            record = {"schema": "row.android-toolchain-qualification.v1", "status": "refused", **context,
                      "native_product_or_browser_launch": False, "CDP_availability": "unproved", "source_unchanged": "not-established", "approval": False, "readiness_credit": 0}
            try:
                public_receipt(root, record)
            except BaseException:
                pass
        raise
    finally:
        initial = sys.exc_info()[1]
        if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
            raise H.Refusal("qualification-owned-cleanup-unproved")


DEVICE = "/dev/kvm"
MAX_ID = (1 << 63) - 1


class KvmContractRefusal(ValueError):
    pass



def _bounded_integer(value, minimum=0, maximum=MAX_ID):
    if type(value) is not int or not minimum <= value <= maximum:
        raise KvmContractRefusal("kvm-observation-layout")
    return value



def kvm_projection(snapshot):
    """Classify only a fixed path's bounded stat/access facts, never an error string."""
    if type(snapshot) is not dict or snapshot.get("path") != DEVICE:
        raise KvmContractRefusal("fixed-kvm-observation-required")
    if type(snapshot.get("present")) is not bool:
        raise KvmContractRefusal("kvm-observation-layout")
    if snapshot["present"] is False:
        if set(snapshot) != {"path", "present", "errno"}:
            raise KvmContractRefusal("kvm-observation-layout")
        number = _bounded_integer(snapshot["errno"], 1, 4095)
        return {"path": DEVICE, "present": False, "errno": number,
                "classification": "device-missing" if number == 2 else "device-stat-refused",
                "qualified_device_identity": False, "permission_change": False,
                "approval": False, "readiness_credit": 0}
    keys = {"path", "present", "mode", "uid", "gid", "dev", "ino", "nlink", "rdev_major", "rdev_minor", "readable", "writable"}
    if set(snapshot) != keys or any(type(snapshot[k]) is not bool for k in ("readable", "writable")):
        raise KvmContractRefusal("kvm-observation-layout")
    mode = _bounded_integer(snapshot["mode"], 0, 0o177777)
    for key in ("uid", "gid", "dev", "rdev_major", "rdev_minor"):
        _bounded_integer(snapshot[key])
    for key in ("ino", "nlink"):
        _bounded_integer(snapshot[key], 1)
    character = stat.S_ISCHR(mode)
    symlink = stat.S_ISLNK(mode)
    qualified = character and snapshot["uid"] == 0 and snapshot["nlink"] == 1 and (snapshot["rdev_major"], snapshot["rdev_minor"]) == (10, 232)
    kind = "symlink" if symlink else "character-device" if character else "wrong-file-type"
    if not qualified:
        classification = "device-identity-refused"
    elif not snapshot["readable"]:
        classification = "device-read-access-refused"
    elif not snapshot["writable"]:
        classification = "device-write-access-refused"
    else:
        classification = "device-read-write-observed"
    return {"path": DEVICE, "present": True, "kind": kind, "mode": stat.S_IMODE(mode),
            **{k: snapshot[k] for k in ("uid", "gid", "dev", "ino", "nlink", "rdev_major", "rdev_minor", "readable", "writable")},
            "classification": classification, "qualified_device_identity": qualified,
            "permission_change": False, "approval": False, "readiness_credit": 0}



def kvm_preflight(root):
    # Read-only diagnostics on one literal device; no open/ioctl or ACL changes.
    event_guard(root)
    leaders = []
    try:
        short, _started = commands(root, leaders)
        binding = source_binding(root, short)
        context = {"schema": "row.android-kvm-readonly-preflight.v1", "binding": binding,
                   "phase": "owned-host-kvm-lstat-preflight", "approval": False, "readiness_credit": 0}
        try:
            before = os.lstat("/dev/kvm")
        except OSError as exc:
            number = exc.errno if type(exc.errno) is int and 0 < exc.errno <= 4095 else 4095
            snapshot = {"path": "/dev/kvm", "present": False, "errno": number}
        else:
            snapshot = {"path": "/dev/kvm", "present": True, "mode": before.st_mode,
                        "uid": before.st_uid, "gid": before.st_gid, "dev": before.st_dev,
                        "ino": before.st_ino, "nlink": before.st_nlink,
                        "rdev_major": os.major(before.st_rdev), "rdev_minor": os.minor(before.st_rdev),
                        "readable": os.access("/dev/kvm", os.R_OK, effective_ids=True, follow_symlinks=False),
                        "writable": os.access("/dev/kvm", os.W_OK, effective_ids=True, follow_symlinks=False)}
            fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_rdev", "st_ctime_ns", "st_mtime_ns")
            try:
                after = os.lstat("/dev/kvm")
                stable = all(getattr(before, name) == getattr(after, name) for name in fields)
            except OSError:
                stable = False
            if not stable:
                if source_binding(root, short) != binding:
                    raise H.Refusal("qualification-current-source-changed")
                context["device"] = {"path": "/dev/kvm", "classification": "device-stat-access-raced-refused",
                                     "permission_change": False, "qualified_device_identity": False}
                print(json.dumps(context))
                raise H.Refusal("owned-host-kvm-stable-identity-required")
        context["device"] = kvm_projection(snapshot)
        if source_binding(root, short) != binding:
            raise H.Refusal("qualification-current-source-changed")
        if not context["device"]["qualified_device_identity"]:
            print(json.dumps(context))
            raise H.Refusal("owned-host-character-kvm-identity-required")
        return context
    finally:
        initial = sys.exc_info()[1]
        if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
            raise H.Refusal("qualification-owned-cleanup-unproved")



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "guard", "observe-public", "bootstrap", "guard-clone", "kvm-preflight", "capture"), default="plan", nargs="?")
    args = parser.parse_args(argv)
    if args.action == "plan":
        print(json.dumps({"status": "qualification-only", "no_browser_or_product_launch": True, "CDP_availability": "requires-separate-actual-browser-proof", "readiness_credit": 0}))
        return 0
    try:
        root = Path.cwd().resolve()
        if args.action == "kvm-preflight":
            value = kvm_preflight(root)
        elif args.action == "bootstrap":
            value = bootstrap(root)
        elif args.action == "observe-public":
            value = observe_public(root)
        elif args.action == "capture":
            value = capture(root)
        else:
            event_guard(root)
            leaders = []
            try:
                short, _started = commands(root, leaders)
                source_binding(root, short) if args.action == "guard" else clone_guard(root, short)
                value = {"status": "exact-current-host-source-guard", "readiness_credit": 0}
            finally:
                initial = sys.exc_info()[1]
                if any(not row["complete"] for row in H.cleanup_all(leaders)) and initial is None:
                    raise H.Refusal("qualification-owned-cleanup-unproved")
        print(json.dumps(value))
        return 0
    except Exception:
        print("android-toolchain-qualification-refused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

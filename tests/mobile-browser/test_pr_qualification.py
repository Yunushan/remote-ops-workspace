"""Focused pure PR/event/workflow/NPM-order fixtures; no native/download activity."""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import shlex
import stat
import sys
import tarfile
import tempfile
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hosted_controller as H  # noqa: E402
import observe_public_stack as O  # noqa: E402
import qualify_android_stack as Q  # noqa: E402

SOURCE, EVENT, WORKFLOW = "e" * 40, "a" * 40, "b" * 40


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(dir=HERE, prefix="focused-fixture-") as value:
        root = Path(value)
        assert root.resolve().parent == HERE and not root.is_symlink()
        try:
            yield root
        finally:
            assert root.resolve().parent == HERE and not root.is_symlink()


def event_data():
    repo = {"full_name": "Yunushan/remote-ops-workspace", "private": False}
    return {"repository": repo.copy(), "action": "synchronize", "number": 125,
            "pull_request": {"head": {"repo": repo.copy(), "sha": SOURCE}, "base": {"repo": repo.copy(), "sha": "c" * 40, "ref": "main"}}}


def env_data(root, path, kind="pull_request"):
    ref = "refs/pull/125/merge" if kind == "pull_request" else "refs/heads/codex/current"
    return {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64",
            "GITHUB_REPOSITORY": "Yunushan/remote-ops-workspace", "ROW_EXPECTED_HEAD": SOURCE, "GITHUB_SHA": EVENT if kind == "pull_request" else SOURCE,
            "GITHUB_WORKFLOW_SHA": WORKFLOW if kind == "pull_request" else SOURCE, "GITHUB_SERVER_URL": "https://github.com", "GITHUB_API_URL": "https://api.github.com",
            "GITHUB_REF": ref, "GITHUB_WORKFLOW_REF": "Yunushan/remote-ops-workspace/" + Q.WORKFLOW + "@" + ref,
            "GITHUB_WORKSPACE": str(root), "GITHUB_EVENT_PATH": str(path), "GITHUB_EVENT_NAME": kind, "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "2"}


@contextmanager
def hosted_fixture(kind="pull_request", payload=None):
    with fixture() as root:
        event = root / "event.json"
        event.write_text(json.dumps(payload if payload is not None else event_data()))
        with mock.patch.object(H, "SOURCE", SOURCE), mock.patch.object(Q.platform, "system", return_value="Linux"), mock.patch.object(Q.platform, "machine", return_value="x86_64"), mock.patch.object(Q.platform, "python_version", return_value="3.14.7"), mock.patch.dict(os.environ, env_data(root, event, kind), clear=True):
            yield root, event


def network_fixture(raw, headers=None, status=200):
    response = mock.MagicMock(status=status, headers=headers or {})
    response.__enter__.return_value = response
    stream = io.BytesIO(raw)
    response.read.side_effect = stream.read
    opener = mock.Mock()
    opener.open.return_value = response
    return opener, response


def qualified_proof(root):
    event = Q.event_guard(root)
    workflow_sha = "f" * 64
    return {"source_sha": SOURCE, "source_tree": "c" * 40,
            "helpers": {name: H.sha(H.read_plain(HERE / name, 262144)) for name in ("qualify_android_stack.py", "hosted_controller.py", "observe_public_stack.py", "archive_readers_frozen.py")},
            "workflow_sha256": workflow_sha, "run_id": event["run_id"], "run_attempt": event["run_attempt"], "execution": event,
            "executed_workflow": {"workflow_sha": WORKFLOW, "size_bytes": 20, "sha256": workflow_sha, "source_contract_matches": True, "redirects": 0}}


class FocusedTests(unittest.TestCase):
    def test_local_guard_refuses_before_git_or_network(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(Q, "commands", side_effect=AssertionError("child")), mock.patch.object(O, "fetch", side_effect=AssertionError("NPM")), self.assertRaises(H.Refusal):
            Q.observe_public(HERE)

    def test_pr_head_event_and_workflow_are_distinct_and_environment_unchanged(self):
        with hosted_fixture() as (root, _event):
            before = dict(os.environ)
            value = Q.event_guard(root)
            self.assertEqual((value["source_sha"], value["event_sha"], value["workflow_sha"]), (SOURCE, EVENT, WORKFLOW))
            self.assertEqual(dict(os.environ), before)
            self.assertNotIn("refs/pull/125/merge", json.dumps(value))

    def test_exact_dispatch_is_still_supported(self):
        with hosted_fixture("workflow_dispatch") as (root, _event):
            value = Q.event_guard(root)
            self.assertEqual((value["source_sha"], value["event_sha"], value["workflow_sha"]), (SOURCE,) * 3)

    def test_dispatch_cannot_relabel_foreign_workflow_or_event_sha(self):
        with hosted_fixture("workflow_dispatch") as (root, _event):
            for key in ("GITHUB_SHA", "GITHUB_WORKFLOW_SHA"):
                with self.subTest(key=key), mock.patch.dict(os.environ, {key: EVENT}), self.assertRaises(H.Refusal):
                    Q.event_guard(root)

    def test_pr_repo_private_fork_base_head_action_and_number_refuse(self):
        edits = [lambda x: x["repository"].update(private=True), lambda x: x["pull_request"]["head"]["repo"].update(full_name="foreign/fork"),
                 lambda x: x["pull_request"]["base"]["repo"].update(private=True), lambda x: x["pull_request"]["base"].update(ref="foreign"),
                 lambda x: x["pull_request"]["head"].update(sha=EVENT), lambda x: x.update(action="closed"), lambda x: x.update(number=True),
                 lambda x: x["pull_request"]["base"].update(sha="wrong")]
        for edit in edits:
            payload = event_data()
            edit(payload)
            with self.subTest(payload=payload), hosted_fixture(payload=payload) as (root, _event), self.assertRaises(H.Refusal):
                Q.event_guard(root)

    def test_pr_ref_and_workflow_identity_refuse(self):
        with hosted_fixture() as (root, _event):
            for key, value in (("GITHUB_REF", "refs/pull/126/merge"), ("GITHUB_WORKFLOW_REF", "foreign/workflow@merge"), ("GITHUB_WORKFLOW_SHA", "latest"), ("GITHUB_RUN_ID", "0"), ("GITHUB_EVENT_NAME", "pull_request_target")):
                with self.subTest(key=key), mock.patch.dict(os.environ, {key: value}), self.assertRaises(H.Refusal):
                    Q.event_guard(root)

    def test_duplicate_event_fields_refuse(self):
        with hosted_fixture() as (root, event):
            event.write_bytes(b'{"repository":{},"repository":{"full_name":"Yunushan/remote-ops-workspace","private":false}}')
            with self.assertRaises(H.Refusal):
                Q.event_guard(root)

    def test_browser_dispatch_guard_has_not_been_weakened_for_pr(self):
        with hosted_fixture() as (root, _event), self.assertRaises(H.Refusal):
            H.host_guard(root)

    def test_exact_immutable_workflow_bound_before_source_acceptance(self):
        raw = b"fixed public workflow\n"
        opener, _response = network_fixture(raw, {"Content-Length": str(len(raw))})
        with mock.patch.object(Q.urllib.request, "build_opener", return_value=opener):
            value = Q.executed_workflow({"workflow_sha": WORKFLOW, "workflow_path": Q.WORKFLOW}, raw, lambda: 120, clock=lambda: 1)
        self.assertEqual(value["sha256"], H.sha(raw))
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://raw.githubusercontent.com/Yunushan/remote-ops-workspace/" + WORKFLOW + "/" + Q.WORKFLOW)
        self.assertNotIn("Authorization", request.headers)

    def test_immutable_workflow_wrong_bytes_status_encoding_size_refuse(self):
        for raw, headers, status in ((b"wrong", {}, 200), (b"expected", {}, 404), (b"expected", {"Content-Encoding": "gzip"}, 200), (b"expected", {"Content-Length": "131073"}, 200), (b"expected", {"Content-Length": "3"}, 200)):
            opener, _response = network_fixture(raw, headers, status)
            with self.subTest(headers=headers, status=status), mock.patch.object(Q.urllib.request, "build_opener", return_value=opener), self.assertRaises(H.Refusal):
                Q.executed_workflow({"workflow_sha": WORKFLOW, "workflow_path": Q.WORKFLOW}, b"expected", lambda: 120, clock=lambda: 1)

    def test_workflow_late_eof_and_original_shared_budget_refuse(self):
        opener, _response = network_fixture(b"expected")
        clock = iter((0, 1, 2, 3, 61))
        with mock.patch.object(Q.urllib.request, "build_opener", return_value=opener), self.assertRaises(H.Refusal):
            Q.executed_workflow({"workflow_sha": WORKFLOW, "workflow_path": Q.WORKFLOW}, b"expected", lambda: 120, clock=lambda: next(clock))
        with mock.patch.object(Q.urllib.request, "build_opener", side_effect=AssertionError("network")), self.assertRaises(H.Refusal):
            Q.executed_workflow({"workflow_sha": WORKFLOW, "workflow_path": Q.WORKFLOW}, b"expected", lambda: 0, clock=lambda: 1)

    def test_workflow_redirect_and_proxy_are_explicitly_refused(self):
        opener, _response = network_fixture(b"expected")
        with mock.patch.object(Q.urllib.request, "build_opener", return_value=opener) as factory:
            Q.executed_workflow({"workflow_sha": WORKFLOW, "workflow_path": Q.WORKFLOW}, b"expected", lambda: 120, clock=lambda: 1)
        handlers = factory.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        with self.assertRaises(H.Refusal):
            handlers[1].redirect_request(None, None, 302, None, {}, "https://foreign.example/secret")

    def test_workflow_unknown_commit_or_path_refuses_before_network(self):
        for record in ({"workflow_sha": "latest", "workflow_path": Q.WORKFLOW}, {"workflow_sha": WORKFLOW, "workflow_path": "../foreign"}):
            with self.subTest(record=record), mock.patch.object(Q.urllib.request, "build_opener", side_effect=AssertionError("network")), self.assertRaises(H.Refusal):
                Q.executed_workflow(record, b"expected", lambda: 120)

    def test_source_head_helpers_and_executed_workflow_order(self):
        root = HERE.parents[1]
        expected_workflow = b"controlled workflow fixture"
        run = {"workflow_sha": WORKFLOW, "workflow_path": Q.WORKFLOW}
        actual_read = H.read_plain
        def read(path, maximum):
            return expected_workflow if path == root / Q.WORKFLOW else actual_read(path, maximum)
        def git(args):
            if args[1] == "status":
                return b""
            if args[1] == "rev-parse":
                return (SOURCE if args[2] == "HEAD" else "f" * 40).encode()
            return expected_workflow if args[2].endswith(Q.WORKFLOW) else actual_read(HERE / args[2].rsplit("/", 1)[1], 262144)
        git.remaining = lambda: 120
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "2"}), mock.patch.object(H, "SOURCE", SOURCE), mock.patch.object(Q, "event_guard", return_value=run), mock.patch.object(H, "read_plain", side_effect=read), mock.patch.object(Q, "executed_workflow", return_value={"workflow_sha": WORKFLOW}) as fetch:
            value = Q.source_binding(root, git)
        self.assertEqual(value["source_sha"], SOURCE)
        self.assertEqual(value["source_tree"], "f" * 40)
        self.assertEqual(fetch.call_args.args[:2], (run, expected_workflow))

    def test_observer_bound_entrypoint_checks_workflow_before_npm(self):
        order = []
        binding = {"fixture": "opaque-authorized-context"}
        short = mock.Mock(remaining=lambda: 120)
        with mock.patch.object(Q, "event_guard", return_value={}), mock.patch.object(Q, "commands", return_value=(short, 0)), mock.patch.object(Q, "source_binding", side_effect=lambda *_args: (order.append("executed-workflow"), binding)[1]), mock.patch.object(O, "_observe_bound_source", side_effect=lambda _root, proof, **_kwargs: (order.append("NPM"), proof)[1]):
            self.assertEqual(Q.observe_public(HERE), binding)
        self.assertEqual(order, ["executed-workflow", "NPM"])

    def test_expired_owned_command_budget_never_starts_child(self):
        clock = iter((0, 1501, 1501))
        with mock.patch.object(Q.time, "monotonic", side_effect=lambda: next(clock)), mock.patch.object(H, "Managed", side_effect=AssertionError("child")):
            short, _started = Q.commands(HERE, [])
            with self.assertRaises(H.Refusal):
                short(["git", "rev-parse", "HEAD"])

    def test_NPM_qualification_shared_budget_pre_post_chunk_and_eof(self):
        opener, response = network_fixture(b"abc", {"Content-Length": "3"})
        with mock.patch.object(O.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(O.fetch_qualification(O.META_URL, 4, lambda: 120, clock=lambda: 1), b"abc")
        self.assertLessEqual(max(call.args[0] for call in response.read.call_args_list), 65536)
        for ticks in ((0, 61), (0, 1, 61), (0, 1, 2, 3, 61)):
            clock = iter(ticks)
            opener, _response = network_fixture(b"abc")
            with self.subTest(ticks=ticks), mock.patch.object(O.urllib.request, "build_opener", return_value=opener), self.assertRaises(H.Refusal):
                O.fetch_qualification(O.META_URL, 4, lambda: 120, clock=lambda clock=clock: next(clock))
        with mock.patch.object(O.urllib.request, "build_opener", side_effect=AssertionError("network")), self.assertRaises(H.Refusal):
            O.fetch_qualification(O.META_URL, 4, lambda: 0, clock=lambda: 1)

    def test_qualification_NPM_uses_owned_source_checks_not_subprocess_run(self):
        with hosted_fixture() as (root, _event):
            (root / ".tmp").mkdir()
            (root / "build/mobile-browser").mkdir(parents=True)
            proof = qualified_proof(root)
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for name, raw in {"package/package.json": b'{"name":"playwright-core","version":"1.56.1"}', "package/lib/client/browserType.js": b"synthetic never executed", "package/lib/server/chromium/chromium.js": b"synthetic never executed"}.items():
                    item = tarfile.TarInfo(name)
                    item.size = len(raw)
                    archive.addfile(item, io.BytesIO(raw))
            tar = gzip.compress(buffer.getvalue())
            integrity = "sha512-" + base64.b64encode(hashlib.sha512(tar).digest()).decode()
            metadata = json.dumps({"name": "playwright-core", "version": "1.56.1", "dist": {"tarball": O.TAR_URL, "integrity": integrity}}).encode()
            owned_check = mock.Mock(return_value=proof)
            with mock.patch.object(O, "git_source", side_effect=AssertionError("unowned subprocess.run")), mock.patch.object(O, "fetch", side_effect=AssertionError("unbound fetch")), mock.patch.object(O, "fetch_qualification", side_effect=[metadata, tar]) as fetch:
                value = O._observe_bound_source(root, proof, source_check=owned_check, remaining=lambda: 120)
            self.assertEqual(value["status"], "observed-unqualified")
            self.assertEqual(owned_check.call_count, 2)
            self.assertEqual(fetch.call_count, 2)
            retained = json.loads((root / "build/mobile-browser/android-public-stack-observation.json").read_bytes())
            self.assertEqual(retained["qualification_execution"]["execution"]["event_sha"], EVENT)
            self.assertFalse(retained["native_commands"])
            self.assertFalse(retained["approval"])

    def test_qualification_missing_owned_source_callback_never_fetches(self):
        with hosted_fixture() as (root, _event):
            proof = qualified_proof(root)
            with mock.patch.object(O, "fetch_qualification", side_effect=AssertionError("network")), self.assertRaisesRegex(H.Refusal, "current-owned-qualification-source-check-required"):
                O._observe_bound_source(root, proof, remaining=lambda: 120)

    def test_changed_workflow_never_reaches_npm_observer(self):
        with mock.patch.object(Q, "event_guard", return_value={}), mock.patch.object(Q, "commands", return_value=(object(), 0)), mock.patch.object(Q, "source_binding", side_effect=H.Refusal("workflow-mismatch")), mock.patch.object(O, "_observe_bound_source", side_effect=AssertionError("NPM")), self.assertRaises(H.Refusal):
            Q.observe_public(HERE)

    def test_private_npm_helper_local_refusal_before_network(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(O, "fetch", side_effect=AssertionError("NPM")), self.assertRaises(H.Refusal):
            O._observe_bound_source(HERE, {"execution": {}})

    def test_private_npm_helper_wrong_context_before_network(self):
        with mock.patch.object(Q, "event_guard", return_value={"source_sha": SOURCE}), mock.patch.object(O, "fetch", side_effect=AssertionError("NPM")), self.assertRaises(H.Refusal):
            O._observe_bound_source(HERE, {"execution": {}})

    def test_standalone_npm_guard_unchanged_and_no_pr_env_spoof(self):
        with hosted_fixture() as (root, _event), mock.patch.object(O, "fetch", side_effect=AssertionError("NPM")), self.assertRaises(H.Refusal):
            O.observe(root)

    def test_canonical_qualification_keeps_public_guards_and_direct_head(self):
        raw = (HERE.parents[1] / Q.WORKFLOW).read_text(encoding="utf-8")
        for text in ("github.repository == 'Yunushan/remote-ops-workspace'", "github.event.repository.private == false", "github.event.pull_request.head.repo.full_name == github.repository", "github.event.pull_request.base.ref == 'main'", "types: [opened, synchronize, reopened]", "ref: ${{ github.event.pull_request.head.sha || github.sha }}", "ROW_EXPECTED_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}", "contents: read", "persist-credentials: false", "qualify_android_stack.py observe-public", "qualify_android_stack.py bootstrap", "qualify_android_stack.py guard-clone", "qualify_android_stack.py capture"):
            self.assertIn(text, raw)
        for text in ("pull_request_target", "\n      false &&", "android_browser_probe.mjs", "fixture_server.py", "hosted_controller.py run", "am start", "npm ci", "connectOverCDP"):
            self.assertNotIn(text, raw)


class SiblingBootstrapTests(unittest.TestCase):
    def test_fixed_sibling_paths_do_not_create_any_tree(self):
        with fixture() as root, mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root)}, clear=True):
            sdk, bootstrap_sdk = Q.owned_sdk(), Q.owned_bootstrap()
            self.assertEqual(sdk, root / "row-browser-api36-sdk")
            self.assertEqual(bootstrap_sdk, root / "row-browser-api36-bootstrap")
            self.assertEqual(sdk.parent, bootstrap_sdk.parent)
            self.assertNotEqual(sdk, bootstrap_sdk)
            self.assertFalse(sdk.exists())
            self.assertFalse(bootstrap_sdk.exists())

    def test_unqualified_temp_or_bootstrap_alias_refuses(self):
        for temp in ("", "/", "relative"):
            with self.subTest(temp=temp), mock.patch.dict(os.environ, {"RUNNER_TEMP": temp}, clear=True):
                with self.assertRaisesRegex(H.Refusal, "qualified-owned-runner-temp-required"):
                    Q.owned_bootstrap()
        for resolved, linked in ((False, False), (True, True)):
            path = mock.Mock()
            path.resolve.return_value = path if resolved else object()
            path.is_symlink.return_value = linked
            parent = mock.MagicMock()
            parent.__truediv__.return_value = path
            sdk = SimpleNamespace(parent=parent)
            with self.subTest(resolved=resolved, linked=linked), mock.patch.object(Q, "owned_sdk", return_value=sdk):
                with self.assertRaisesRegex(H.Refusal, "qualified-owned-bootstrap-path-required"):
                    Q.owned_bootstrap()

    def test_preexisting_sdk_or_bootstrap_refuses_before_snapshot_or_write(self):
        with fixture() as root:
            source = root / "source-sdk"
            source.mkdir()
            for name, code in (("row-browser-api36-sdk", "fresh-isolated-sdk-required"),
                               ("row-browser-api36-bootstrap", "fresh-isolated-bootstrap-required")):
                existing = root / name
                existing.mkdir()
                with self.subTest(name=name), mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root), "ANDROID_HOME": str(source)}, clear=True), mock.patch.object(Q, "FIXED_SOURCE_SDK", source), mock.patch.object(Q, "event_guard", return_value={}), mock.patch.object(Q, "commands", return_value=(mock.Mock(), 0)), mock.patch.object(Q, "source_binding", return_value={}), mock.patch.object(H, "tree_digest", side_effect=AssertionError("snapshot")) as snapshot, mock.patch.object(O, "save", side_effect=AssertionError("write")) as save, mock.patch.object(H, "cleanup_all", return_value=[]) as cleanup:
                    with self.assertRaises(H.Refusal) as error:
                        Q.bootstrap(root)
                    self.assertEqual(error.exception.args, (code,))
                    snapshot.assert_not_called()
                    save.assert_not_called()
                    cleanup.assert_called_once_with([])
                existing.rmdir()

    def test_clone_guard_checks_bootstrap_and_original_licenses_not_installed_tools(self):
        with fixture() as root, mock.patch.dict(os.environ, {"RUNNER_TEMP": str(root)}, clear=True):
            binding = {"source_sha": SOURCE}
            observation = {"schema": "row.android-sdk-bootstrap-observation.v1", "binding": binding,
                           "cmdline_tree_sha256": "a" * 64, "already_present_license_tree_sha256": "b" * 64,
                           "signing_or_license_approval": False, "readiness_credit": 0}
            raw = json.dumps(observation).encode()
            for hashes, accepted in ((("a" * 64, "b" * 64), True),
                                     (("c" * 64,), False), (("a" * 64, "c" * 64), False)):
                with self.subTest(hashes=hashes), mock.patch.object(H, "read_plain", return_value=raw), mock.patch.object(H, "tree_digest", side_effect=hashes) as trees, mock.patch.object(Q, "source_binding", side_effect=AssertionError("unbound source")), mock.patch.object(H, "Managed", side_effect=AssertionError("native")):
                    if accepted:
                        actual_binding, actual_observation = Q.clone_guard(root, mock.Mock(), binding)
                        self.assertIs(actual_binding, binding)
                        self.assertEqual(actual_observation, observation)
                    else:
                        with self.assertRaisesRegex(H.Refusal, "actual-cloned-tool-bytes-required"):
                            Q.clone_guard(root, mock.Mock(), binding)
                    expected = [root / "row-browser-api36-bootstrap/cmdline-tools/latest",
                                root / "row-browser-api36-sdk/licenses"][:len(hashes)]
                    self.assertEqual([call.args[0] for call in trees.call_args_list], expected)

    def test_unbound_bootstrap_observation_refuses_before_any_tree_access(self):
        binding = {"source_sha": SOURCE}
        observation = {"schema": "row.android-sdk-bootstrap-observation.v1", "binding": binding,
                       "cmdline_tree_sha256": "a" * 64, "already_present_license_tree_sha256": "b" * 64,
                       "signing_or_license_approval": False, "readiness_credit": 0}
        for key, value in (("binding", {"source_sha": EVENT}), ("schema", "unbound"),
                           ("signing_or_license_approval", True), ("readiness_credit", 1)):
            changed = json.loads(json.dumps(observation))
            changed[key] = value
            with self.subTest(key=key), mock.patch.object(H, "read_plain", return_value=json.dumps(changed).encode()), mock.patch.object(H, "tree_digest", side_effect=AssertionError("tree")) as trees, mock.patch.object(Q, "owned_sdk", side_effect=AssertionError("path")):
                with self.assertRaisesRegex(H.Refusal, "exact-current-bootstrap-observation-required"):
                    Q.clone_guard(HERE, mock.Mock(), binding)
                trees.assert_not_called()

    def test_installer_uses_bootstrap_and_target_is_separate_installed_sdk(self):
        raw = (HERE.parents[1] / Q.WORKFLOW).read_text(encoding="utf-8")
        setup = raw.partition("- name: Provision only the fresh isolated official API36 SDK")[2]
        self.assertTrue(setup)
        setup = setup.partition("\n      - name:")[0]
        lines = [line.strip() for line in setup.replace("\\\n", " ").splitlines()]
        commands = [shlex.split(line) for line in lines if line]
        installer = [tokens for tokens in commands if tokens[:2] == ["env", "-i"]]
        self.assertEqual(len(installer), 1)
        tokens = installer[0]
        self.assertIn("$bootstrap_sdk/cmdline-tools/latest/bin/sdkmanager", tokens)
        self.assertNotIn("$owned_sdk/cmdline-tools/latest/bin/sdkmanager", tokens)
        self.assertIn("--sdk_root=$owned_sdk", tokens)
        self.assertEqual(tokens[tokens.index("--install") + 1:],
                         ["cmdline-tools;latest", "platform-tools", "emulator",
                          "platforms;android-36", "system-images;android-36;google_apis;x86_64"])
        for name in ("owned_sdk", "bootstrap_sdk"):
            self.assertIn(["test", "!", "-e", "$" + name], commands)
        clone = ["cp", "-R", "$ANDROID_HOME/cmdline-tools/latest", "$bootstrap_sdk/cmdline-tools/latest"]
        self.assertIn(clone, commands)
        self.assertIn(["cp", "-R", "$ANDROID_HOME/licenses", "$owned_sdk/licenses"], commands)
        guard = ["python", "tests/mobile-browser/qualify_android_stack.py", "guard-clone"]
        self.assertLess(commands.index(clone), commands.index(guard))
        self.assertLess(commands.index(guard), commands.index(tokens))


class CaptureDiagnosticTests(unittest.TestCase):
    def test_known_refusal_is_bounded_and_never_grants_credit(self):
        for code in Q.PUBLIC_CAPTURE_REFUSALS:
            record = Q.capture_refusal_diagnostic(H.Refusal(code), "sdk-observation")
            self.assertEqual(record["refusal_code"], code)
            self.assertFalse(record["approval"])
            self.assertEqual(record["readiness_credit"], 0)
            raw = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
            self.assertTrue(raw.isascii())
            self.assertLessEqual(len(raw), 512)

    def test_unknown_private_and_hostile_values_are_never_stringified(self):
        class HostileString(str):
            def __str__(self):
                raise AssertionError("stringification")
            def __hash__(self):
                raise AssertionError("hash")
        class HostileRefusal(H.Refusal):
            def __str__(self):
                raise AssertionError("stringification")
        values = (H.Refusal(), H.Refusal("one", "two"), H.Refusal("/private/example"),
                  H.Refusal("x" * 10000), H.Refusal(HostileString("tree-hardlink")),
                  H.Refusal(object()), HostileRefusal("tree-hardlink"), RuntimeError("/private/example"))
        for exc in values:
            with self.subTest(kind=type(exc).__name__):
                record = Q.capture_refusal_diagnostic(exc, HostileString("sdk-observation"))
                self.assertEqual(record["refusal_code"], "unclassified")
                self.assertEqual(record["phase"], "unobserved")
                self.assertNotIn("private", json.dumps(record))
        for exc, code in ((FileNotFoundError("/private/example"), "missing-input"),
                          (PermissionError("/private/example"), "input-access-refused")):
            self.assertEqual(Q.capture_refusal_diagnostic(exc, None)["refusal_code"], code)

    def test_every_fixed_missing_metadata_path_remains_a_refusal(self):
        sdk = Path("/owned-sdk")
        for (component, name), code in Q.SDK_METADATA_REFUSALS.items():
            missing = sdk / component / name
            def read(path, maximum, missing=missing):
                if path == missing:
                    raise FileNotFoundError("/private/example")
                return b"Pkg.Revision=1\n"
            with self.subTest(component=component, name=name), mock.patch.object(H, "read_plain", side_effect=read), mock.patch.object(H, "tree_digest", side_effect=AssertionError("tree")), mock.patch.object(H, "Managed", side_effect=AssertionError("native")):
                with self.assertRaises(H.Refusal) as error:
                    Q.sdk_inventory(sdk)
                self.assertEqual(error.exception.args, (code,))

    def test_publisher_or_stderr_failure_preserves_original_refusal_and_cleanup(self):
        class BrokenStream:
            def write(self, value):
                raise RuntimeError("/private/printing")
        for broken in (False, True):
            original = H.Refusal("plain-bounded-input-required")
            stream = BrokenStream() if broken else io.StringIO()
            with self.subTest(broken=broken), mock.patch.object(Q, "event_guard", return_value={}), mock.patch.object(Q, "commands", return_value=(object(), 0)), mock.patch.object(Q, "source_binding", return_value={}), mock.patch.object(Q, "clone_guard", side_effect=original), mock.patch.object(Q, "public_receipt", side_effect=RuntimeError("/private/publisher")), mock.patch.object(H, "cleanup_all", return_value=[]) as cleanup, mock.patch.object(H, "Managed", side_effect=AssertionError("native")), mock.patch.object(sys, "stderr", stream):
                with self.assertRaises(H.Refusal) as error:
                    Q.capture(HERE)
                self.assertIs(error.exception, original)
                cleanup.assert_called_once_with([])
            if not broken:
                record = json.loads(stream.getvalue())
                self.assertEqual(record["phase"], "bootstrap-and-cloned-sdk")
                self.assertEqual(record["refusal_code"], original.args[0])
                self.assertNotIn("private", stream.getvalue())

    def test_pre_context_failure_uses_only_unobserved_phase(self):
        original = H.Refusal("qualification-command-original-budget")
        stream = io.StringIO()
        with mock.patch.object(Q, "event_guard", return_value={}), mock.patch.object(Q, "commands", side_effect=original), mock.patch.object(Q, "public_receipt", side_effect=AssertionError("publisher")), mock.patch.object(H, "cleanup_all", return_value=[]) as cleanup, redirect_stderr(stream):
            with self.assertRaises(H.Refusal) as error:
                Q.capture(HERE)
            self.assertIs(error.exception, original)
            cleanup.assert_called_once_with([])
        self.assertEqual(json.loads(stream.getvalue())["phase"], "unobserved")


def _kvm_snapshot(**changes):
    value = {"path": "/dev/kvm", "present": True, "mode": stat.S_IFCHR | 0o660,
             "uid": 0, "gid": 108, "dev": 23, "ino": 45, "nlink": 1,
             "rdev_major": 10, "rdev_minor": 232, "readable": False, "writable": False}
    value.update(changes)
    return value


def _kvm_stat(**changes):
    value = {"st_mode": stat.S_IFCHR | 0o660, "st_uid": 0, "st_gid": 108,
             "st_dev": 23, "st_ino": 45, "st_nlink": 1, "st_rdev": 791,
             "st_ctime_ns": 100, "st_mtime_ns": 200}
    value.update(changes)
    return SimpleNamespace(**value)


@contextmanager
def _kvm_mocked(before=None, after=None, read=False, write=False, major=10, minor=232,
                sources=None, guard_error=None, cleanup_complete=True, access_error=None):
    order = []
    owner = object()
    binding = {"source_sha": SOURCE, "source_tree": "c" * 40, "run_id": "12345", "run_attempt": "2"}
    source_values = iter(sources if sources is not None else [binding, binding])
    stat_values = iter([before if before is not None else _kvm_stat(),
                        after if after is not None else _kvm_stat()])
    accesses = iter([read, write])
    short = mock.Mock(side_effect=AssertionError("unmocked-command-refused"))

    def guard(_root):
        order.append("event")
        if guard_error is not None:
            raise guard_error
        return {}

    def commands(_root, leaders):
        order.append("commands")
        leaders.append(owner)
        return short, 0

    def source(_root, observed_short):
        assert observed_short is short
        order.append("source")
        value = next(source_values)
        if isinstance(value, BaseException):
            raise value
        return value

    def lstat(path):
        assert path == "/dev/kvm"
        order.append("lstat")
        value = next(stat_values)
        if isinstance(value, BaseException):
            raise value
        return value

    def access(path, flag, **kwargs):
        assert path == "/dev/kvm" and flag in {Q.os.R_OK, Q.os.W_OK}
        assert kwargs == {"effective_ids": True, "follow_symlinks": False}
        order.append("read" if flag == Q.os.R_OK else "write")
        if access_error is not None:
            raise access_error
        return next(accesses)

    def cleanup(leaders):
        assert leaders == [owner]
        order.append("cleanup")
        return [{"complete": cleanup_complete}]

    stdout, stderr = io.StringIO(), io.StringIO()
    with ExitStack() as stack:
        guard_mock = stack.enter_context(mock.patch.object(Q, "event_guard", side_effect=guard))
        command_mock = stack.enter_context(mock.patch.object(Q, "commands", side_effect=commands))
        source_mock = stack.enter_context(mock.patch.object(Q, "source_binding", side_effect=source))
        lstat_mock = stack.enter_context(mock.patch.object(Q.os, "lstat", side_effect=lstat))
        access_mock = stack.enter_context(mock.patch.object(Q.os, "access", side_effect=access))
        major_mock = stack.enter_context(mock.patch.object(Q.os, "major", return_value=major, create=True))
        minor_mock = stack.enter_context(mock.patch.object(Q.os, "minor", return_value=minor, create=True))
        cleanup_mock = stack.enter_context(mock.patch.object(H, "cleanup_all", side_effect=cleanup))
        stack.enter_context(mock.patch.object(H, "Managed", side_effect=AssertionError("real-process-refused")))
        stack.enter_context(mock.patch.object(Q.urllib.request, "build_opener", side_effect=AssertionError("real-network-refused")))
        path_mock = stack.enter_context(mock.patch.object(Q, "Path"))
        path_mock.cwd.return_value.resolve.return_value = HERE
        stack.enter_context(redirect_stdout(stdout))
        stack.enter_context(redirect_stderr(stderr))
        yield {"order": order, "binding": binding, "stdout": stdout, "stderr": stderr,
               "guard": guard_mock, "commands": command_mock, "source": source_mock,
               "lstat": lstat_mock, "access": access_mock, "major": major_mock,
               "minor": minor_mock, "cleanup": cleanup_mock, "short": short}


class KvmFocusedTests(unittest.TestCase):
    def test_kvm_projection_exact_layout_bounds_and_missing_errno(self):
        for number, expected in ((2, "device-missing"), (13, "device-stat-refused")):
            with self.subTest(errno=number):
                value = Q.kvm_projection({"path": "/dev/kvm", "present": False, "errno": number})
                self.assertEqual(value["classification"], expected)
                self.assertFalse(value["qualified_device_identity"])
        for change in ({"uid": True}, {"mode": 0o200000}, {"dev": -1}, {"ino": 0}, {"nlink": True},
                       {"rdev_minor": "232"}, {"readable": 1}, {"writable": 0}, {"path": "/tmp/kvm"},
                       {"present": 1}, {"ino": 1 << 63}, {"private": "must not retain"}):
            with self.subTest(change=change), self.assertRaises(Q.KvmContractRefusal):
                Q.kvm_projection(_kvm_snapshot(**change))
        for value in (None, [], {"path": "/dev/kvm", "present": False, "errno": 0},
                      {"path": "/dev/kvm", "present": False, "errno": True},
                      {"path": "/dev/kvm", "present": False, "errno": 4096},
                      {"path": "/dev/kvm", "present": False, "errno": 2, "private": "no"}):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(Q.KvmContractRefusal):
                Q.kvm_projection(value)

    def test_kvm_projection_identity_refuses_and_read_write_facts_have_no_credit(self):
        for change in ({"mode": stat.S_IFLNK | 0o777}, {"mode": stat.S_IFREG | 0o660}, {"uid": 1001},
                       {"nlink": 2}, {"rdev_major": 11}, {"rdev_minor": 233}):
            with self.subTest(change=change):
                value = Q.kvm_projection(_kvm_snapshot(**change))
                self.assertEqual(value["classification"], "device-identity-refused")
                self.assertFalse(value["qualified_device_identity"])
        for read, write, expected in ((False, False, "device-read-access-refused"),
                                     (False, True, "device-read-access-refused"),
                                     (True, False, "device-write-access-refused"),
                                     (True, True, "device-read-write-observed")):
            with self.subTest(read=read, write=write):
                value = Q.kvm_projection(_kvm_snapshot(readable=read, writable=write))
                self.assertEqual(value["classification"], expected)
                self.assertTrue(value["qualified_device_identity"])
                self.assertEqual((value["approval"], value["permission_change"], value["readiness_credit"]), (False, False, 0))

    def test_kvm_preflight_fixed_observation_is_between_source_checks_and_cleanup(self):
        with _kvm_mocked(read=True, write=True) as case:
            value = Q.kvm_preflight(HERE)
            self.assertEqual(case["order"], ["event", "commands", "source", "lstat", "read", "write", "lstat", "source", "cleanup"])
            self.assertEqual(value["binding"], case["binding"])
            self.assertEqual(value["device"]["classification"], "device-read-write-observed")
            self.assertEqual((value["approval"], value["readiness_credit"]), (False, 0))
            self.assertEqual(case["stdout"].getvalue(), "")
            self.assertEqual(case["major"].call_args.args, (791,))
            self.assertEqual(case["minor"].call_args.args, (791,))
            case["short"].assert_not_called()

    def test_kvm_preflight_local_guard_refuses_before_commands_or_device(self):
        refusal = H.Refusal("synthetic-local-guard")
        with _kvm_mocked(guard_error=refusal) as case, self.assertRaises(H.Refusal) as error:
            Q.kvm_preflight(HERE)
        self.assertIs(error.exception, refusal)
        self.assertEqual(case["order"], ["event"])
        for name in ("commands", "source", "lstat", "access", "cleanup"):
            case[name].assert_not_called()

    def test_kvm_preflight_initial_source_refusal_never_observes_device(self):
        refusal = H.Refusal("synthetic-source-refusal")
        with _kvm_mocked(sources=[refusal]) as case, self.assertRaises(H.Refusal) as error:
            Q.kvm_preflight(HERE)
        self.assertIs(error.exception, refusal)
        self.assertEqual(case["order"], ["event", "commands", "source", "cleanup"])
        case["lstat"].assert_not_called()
        case["access"].assert_not_called()
        self.assertEqual(case["stdout"].getvalue(), "")

    def test_kvm_preflight_changed_source_refuses_before_diagnostic_output(self):
        with _kvm_mocked(sources=[{"head": SOURCE}, {"head": EVENT}]) as case:
            with self.assertRaisesRegex(H.Refusal, "qualification-current-source-changed"):
                Q.kvm_preflight(HERE)
            self.assertEqual(case["source"].call_count, 2)
            self.assertEqual(case["stdout"].getvalue(), "")
            self.assertEqual(case["order"][-1], "cleanup")

    def test_kvm_preflight_missing_stat_emits_only_bound_fixed_errno_facts(self):
        for number, expected in ((2, "device-missing"), (13, "device-stat-refused"), (None, "device-stat-refused")):
            failure = OSError(number, "private path and private exception detail")
            with self.subTest(errno=number), _kvm_mocked(before=failure) as case:
                with self.assertRaisesRegex(H.Refusal, "owned-host-character-kvm-identity-required"):
                    Q.kvm_preflight(HERE)
                record = json.loads(case["stdout"].getvalue())
                self.assertEqual(record["binding"], case["binding"])
                self.assertEqual(record["device"]["classification"], expected)
                self.assertEqual(record["device"]["errno"], number if number is not None else 4095)
                self.assertNotIn("private", case["stdout"].getvalue())
                self.assertEqual(case["lstat"].call_count, 1)
                case["access"].assert_not_called()
                self.assertEqual(case["source"].call_count, 2)
                self.assertEqual(case["order"][-1], "cleanup")

    def test_kvm_preflight_changed_identity_or_second_stat_failure_refuses(self):
        changes = ({"st_dev": 24}, {"st_ino": 46}, {"st_mode": stat.S_IFREG | 0o660},
                   {"st_uid": 1001}, {"st_gid": 109}, {"st_nlink": 2}, {"st_rdev": 792},
                   {"st_ctime_ns": 101}, {"st_mtime_ns": 201})
        for after in [*(_kvm_stat(**change) for change in changes), OSError(2, "private disappearance")]:
            with self.subTest(after=type(after).__name__), _kvm_mocked(after=after) as case:
                with self.assertRaisesRegex(H.Refusal, "owned-host-kvm-stable-identity-required"):
                    Q.kvm_preflight(HERE)
                record = json.loads(case["stdout"].getvalue())
                self.assertEqual(set(record["device"]), {"path", "classification", "permission_change", "qualified_device_identity"})
                self.assertEqual(record["device"]["classification"], "device-stat-access-raced-refused")
                self.assertFalse(record["device"]["qualified_device_identity"])
                self.assertNotIn("private", case["stdout"].getvalue())
                self.assertEqual(case["source"].call_count, 2)
                self.assertEqual(case["order"][-1], "cleanup")

    def test_kvm_preflight_wrong_node_identity_refuses_before_shell_stage(self):
        cases = [({"st_mode": stat.S_IFLNK | 0o777}, 10, 232), ({"st_uid": 1001}, 10, 232),
                 ({"st_nlink": 2}, 10, 232), ({}, 11, 232), ({}, 10, 233)]
        for change, major, minor in cases:
            with self.subTest(change=change, major=major, minor=minor), _kvm_mocked(before=_kvm_stat(**change), after=_kvm_stat(**change), major=major, minor=minor) as case:
                with self.assertRaisesRegex(H.Refusal, "owned-host-character-kvm-identity-required"):
                    Q.kvm_preflight(HERE)
                record = json.loads(case["stdout"].getvalue())
                self.assertEqual(record["device"]["classification"], "device-identity-refused")
                self.assertFalse(record["device"]["qualified_device_identity"])
                case["short"].assert_not_called()

    def test_kvm_preflight_cleanup_uncertainty_rejects_success_preserves_original_refusal(self):
        with _kvm_mocked(read=True, write=True, cleanup_complete=False) as case:
            with self.assertRaisesRegex(H.Refusal, "qualification-owned-cleanup-unproved"):
                Q.kvm_preflight(HERE)
            self.assertEqual(case["stdout"].getvalue(), "")
        refusal = H.Refusal("synthetic-original-refusal")
        with _kvm_mocked(sources=[refusal], cleanup_complete=False) as case, self.assertRaises(H.Refusal) as error:
            Q.kvm_preflight(HERE)
        self.assertIs(error.exception, refusal)
        case["cleanup"].assert_called_once()

    def test_kvm_main_private_access_error_or_uncertain_cleanup_stays_nonzero(self):
        for options in ({"access_error": RuntimeError("private host information")}, {"cleanup_complete": False}):
            with self.subTest(options=tuple(options)), _kvm_mocked(**options) as case:
                self.assertEqual(Q.main(["kvm-preflight"]), 1)
                self.assertEqual(case["stdout"].getvalue(), "")
                self.assertEqual(case["stderr"].getvalue(), "android-toolchain-qualification-refused\n")
                self.assertNotIn("private", case["stderr"].getvalue())
                self.assertEqual(case["order"][-1], "cleanup")

    def test_kvm_main_returns_zero_only_after_cleanup_and_retains_access_refusal(self):
        with _kvm_mocked() as case:
            self.assertEqual(Q.main(["kvm-preflight"]), 0)
            record = json.loads(case["stdout"].getvalue())
            self.assertEqual(record["device"]["classification"], "device-read-access-refused")
            self.assertFalse(record["device"]["readable"])
            self.assertEqual(case["order"][-1], "cleanup")
            self.assertEqual(case["stderr"].getvalue(), "")

    def test_kvm_workflow_preflight_once_before_original_shell_read_write_gates(self):
        raw = (HERE.parents[1] / Q.WORKFLOW).read_text(encoding="utf-8")
        command = "python tests/mobile-browser/qualify_android_stack.py kvm-preflight"
        self.assertEqual(raw.count(command), 1)
        self.assertLess(raw.index("phase=isolated-sdkmanager-zero-exit"), raw.index(command))
        self.assertLess(raw.index(command), raw.index("if ! test -r /dev/kvm; then"))
        self.assertLess(raw.index("if ! test -r /dev/kvm; then"), raw.index("if ! test -w /dev/kvm; then"))
        self.assertIn("android-kvm-read-access-refused", raw)
        self.assertIn("android-kvm-write-access-refused", raw)
        setup_marker = "      - name: Enable KVM only for this disposable runner user\n"
        collector_marker = "      - name: Observe actual KVM access before emulator capture\n"
        self.assertEqual(raw.count(setup_marker), 1)
        self.assertEqual(raw.count(collector_marker), 1)
        prefix, _, remainder = raw.partition(setup_marker)
        setup, _, collector = remainder.partition(collector_marker)
        self.assertLess(raw.index("phase=isolated-sdkmanager-zero-exit"), raw.index(setup_marker))
        self.assertIn(command, collector)
        for forbidden in ("sudo", "setfacl", "chmod", "chown"):
            self.assertNotIn(forbidden, prefix + collector)
        mutation = 'sudo --non-interactive setfacl --no-mask --modify "u:$runner_uid:rw" -- /dev/kvm'
        self.assertEqual(setup.count(mutation), 1)
        self.assertEqual(setup.count("sudo"), 1)
        self.assertEqual(setup.count("setfacl"), 1)
        self.assertNotIn("chmod", setup)
        self.assertNotIn("chown", setup)
        for guard in (
            "test -c /dev/kvm",
            "test ! -L /dev/kvm",
            "test \"$(stat -c '%u:%h:%t:%T' /dev/kvm)\" = '0:1:a:e8'",
            "test \"$(stat -c '%a' /dev/kvm)\" = '660'",
            'runner_uid="$(id -u)"',
            'test "$runner_uid" -gt 0',
            'device_identity="$(stat -c \'%d:%i:%u:%g:%h:%f:%r\' /dev/kvm)"',
            'test "$(stat -c \'%d:%i:%u:%g:%h:%f:%r\' /dev/kvm)" = "$device_identity"',
            'test "$other_acl_after" = "$other_acl_before"',
        ):
            self.assertIn(guard, setup)
        self.assertLess(setup.index('test "$runner_uid" -gt 0'), setup.index(mutation))
        self.assertLess(setup.index('test "${#acl_before}" -le 8192'), setup.index(mutation))
        self.assertGreater(setup.index('test "$other_acl_after" = "$other_acl_before"'), setup.index(mutation))


class SdkTreeLimitDiagnosticTests(unittest.TestCase):
    @staticmethod
    def observation():
        return {"component": "system-image-api36-x86-64", "sampled_stat_bytes": Q.SDK_TREE_MAXIMUM_BYTES + 1,
                "maximum_bytes": Q.SDK_TREE_MAXIMUM_BYTES, "file_stat_bytes": 6, "sampled_nodes": 7,
                "maximum_nodes": 30000, "complete": False, "file_digest_observed": False}

    def test_tree_budget_refuses_before_rejected_file_read(self):
        for relative, component in (("system-images/android-36/google_apis/x86_64/private.img", "system-image-api36-x86-64"),
                                    ("private-name/private.img", "other"), ("private.img", "other")):
            with self.subTest(component=component), fixture() as root:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"sample")
                with mock.patch.object(Path, "open", side_effect=AssertionError("file read")) as opened:
                    with self.assertRaises(H.Refusal) as error:
                        H.tree_digest(root, maximum_files=30000, maximum_bytes=5)
                opened.assert_not_called()
                self.assertEqual(error.exception.args, ("tree-total-byte-bound",))
                value = error.exception.tree_limit_observation
                self.assertEqual(value["component"], component)
                self.assertEqual(value["sampled_stat_bytes"], 6)
                self.assertEqual(value["maximum_bytes"], 5)
                self.assertEqual(value["file_stat_bytes"], 6)
                self.assertGreaterEqual(value["sampled_nodes"], 2)
                self.assertFalse(value["complete"])
                self.assertFalse(value["file_digest_observed"])
                self.assertNotIn("private", json.dumps(value))

    def test_component_classification_is_fixed_and_prefix_exact(self):
        root = Path("/owned-sdk")
        for relative, component in (("cmdline-tools/latest/private", "cmdline-tools"),
                                    ("platform-tools/private", "platform-tools"), ("emulator/private", "emulator"),
                                    ("platforms/android-36/private", "platform-api36"),
                                    ("system-images/android-36/google_apis/x86_64/private", "system-image-api36-x86-64"),
                                    ("licenses/private", "licenses"), ("private", "other"),
                                    ("cmdline-tools/latest-extra/private", "other"),
                                    ("platforms/android-360/private", "other"),
                                    ("system-images/android-36/google_apis/x86_64-extra/private", "other")):
            with self.subTest(component=component):
                error = H._tree_byte_bound_refusal(root, root / relative, 6, 6, 2, 30000, 5)
                self.assertEqual(error.args, ("tree-total-byte-bound",))
                self.assertEqual(error.tree_limit_observation["component"], component)
                self.assertNotIn("private", json.dumps(error.tree_limit_observation))

    def test_diagnostic_construction_failure_preserves_budget_refusal(self):
        with mock.patch.object(Path, "relative_to", side_effect=KeyboardInterrupt("/private/example")):
            error = H._tree_byte_bound_refusal(Path("/owned-sdk"), Path("/owned-sdk/private"), 6, 6, 2, 30000, 5)
        self.assertEqual(error.args, ("tree-total-byte-bound",))
        self.assertNotIn("tree_limit_observation", error.__dict__)

    def test_bounded_partial_projection_never_claims_complete_size(self):
        for component in ("cmdline-tools", "platform-tools", "emulator", "platform-api36",
                          "system-image-api36-x86-64", "licenses", "other"):
            for large in (False, True):
                value = self.observation()
                value["component"] = component
                if large:
                    value["sampled_stat_bytes"] = 2 ** 64 - 1
                    value["file_stat_bytes"] = value["sampled_stat_bytes"] - value["maximum_bytes"]
                    value["sampled_nodes"] = 30000
                error = H.Refusal("tree-total-byte-bound")
                error.tree_limit_observation = value
                with self.subTest(component=component, large=large):
                    record = Q.capture_refusal_diagnostic(error, "sdk-observation")
                    self.assertEqual(record["sdk_tree_limit"], value)
                    self.assertFalse(record["sdk_tree_limit"]["complete"])
                    self.assertFalse(record["sdk_tree_limit"]["file_digest_observed"])
                    self.assertFalse(record["approval"])
                    self.assertEqual(record["readiness_credit"], 0)
                    raw = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
                    self.assertTrue(raw.isascii())
                    self.assertLessEqual(len(raw), 512)

    def test_malformed_private_or_inconsistent_metrics_are_omitted(self):
        class HostileString(str):
            def __hash__(self):
                raise AssertionError("hash")
            def __str__(self):
                raise AssertionError("stringification")
        base = self.observation()
        values = (None, [], {**base, "path": "/private/example"},
                  {key: value for key, value in base.items() if key != "component"},
                  {(1 if key == "component" else key): value for key, value in base.items()},
                  {("path" if key == "component" else key): value for key, value in base.items()},
                  {**base, "component": "/private/example"}, {**base, "component": HostileString("emulator")},
                  {**base, "sampled_stat_bytes": True}, {**base, "file_stat_bytes": "6"},
                  {**base, "sampled_stat_bytes": 2 ** 64}, {**base, "file_stat_bytes": -1},
                  {**base, "maximum_bytes": 5}, {**base, "maximum_nodes": 12000},
                  {**base, "sampled_nodes": 0}, {**base, "sampled_nodes": 30001},
                  {**base, "file_stat_bytes": 0}, {**base, "file_stat_bytes": base["sampled_stat_bytes"] + 1},
                  {**base, "sampled_stat_bytes": base["maximum_bytes"]},
                  {**base, "sampled_stat_bytes": base["maximum_bytes"] + 7},
                  {**base, "complete": True}, {**base, "file_digest_observed": True})
        expected = Q.capture_refusal_diagnostic(H.Refusal("tree-total-byte-bound"), "sdk-observation")
        for index, value in enumerate(values):
            error = H.Refusal("tree-total-byte-bound")
            error.tree_limit_observation = value
            with self.subTest(index=index):
                record = Q.capture_refusal_diagnostic(error, "sdk-observation")
                self.assertEqual(record, expected)
                self.assertNotIn("private", json.dumps(record))

    def test_other_phase_or_reason_does_not_publish_metrics(self):
        class RefusalSubclass(H.Refusal):
            pass
        for phase, error in ((None, H.Refusal("tree-total-byte-bound")),
                             ("bootstrap-and-cloned-sdk", H.Refusal("tree-total-byte-bound")),
                             ("sdk-observation", H.Refusal("tree-hardlink")),
                             ("sdk-observation", RefusalSubclass("tree-total-byte-bound"))):
            error.tree_limit_observation = self.observation()
            with self.subTest(phase=phase, kind=type(error).__name__):
                record = Q.capture_refusal_diagnostic(error, phase)
                self.assertNotIn("sdk_tree_limit", record)
                self.assertFalse(record["approval"])

    def test_capture_preserves_original_refusal_and_cleanup_with_metrics(self):
        class BrokenStream:
            def write(self, value):
                raise RuntimeError("/private/printing")
        sdk = HERE / "unobserved-sdk"
        for broken in (False, True):
            original = H.Refusal("tree-total-byte-bound")
            original.tree_limit_observation = self.observation()
            stream = BrokenStream() if broken else io.StringIO()
            with self.subTest(broken=broken), mock.patch.dict(os.environ, {"ANDROID_HOME": str(sdk)}, clear=True), mock.patch.object(Q, "event_guard", return_value={}), mock.patch.object(Q, "commands", return_value=(object(), 0)), mock.patch.object(Q, "source_binding", return_value={}), mock.patch.object(Q, "clone_guard", return_value=({}, {})), mock.patch.object(Q, "owned_sdk", return_value=sdk), mock.patch.object(Q, "sdk_inventory", side_effect=original), mock.patch.object(Q, "public_receipt", side_effect=RuntimeError("/private/publisher")), mock.patch.object(H, "cleanup_all", return_value=[]) as cleanup, mock.patch.object(H, "Managed", side_effect=AssertionError("native")) as managed, mock.patch.object(sys, "stderr", stream):
                with self.assertRaises(H.Refusal) as error:
                    Q.capture(HERE)
                self.assertIs(error.exception, original)
                cleanup.assert_called_once_with([])
                managed.assert_not_called()
            if not broken:
                record = json.loads(stream.getvalue())
                self.assertEqual(record["sdk_tree_limit"], self.observation())
                self.assertEqual(record["refusal_code"], "tree-total-byte-bound")
                self.assertNotIn("private", stream.getvalue())

    def test_sdk_inventory_forwards_scoped_budget_after_all_metadata_and_tools(self):
        sdk = Path("/owned-sdk")
        prefixes = ("cmdline-tools/latest", "platform-tools", "emulator", "platforms/android-36",
                    "system-images/android-36/google_apis/x86_64")
        raw_by_path, expected_reads, expected_metadata = {}, [], []
        for prefix in prefixes:
            for name in ("package.xml", "source.properties"):
                raw = b"<repository/>" if name == "package.xml" else b"Pkg.Revision=17.0.1\n"
                path = sdk / prefix / name
                raw_by_path[path] = raw
                expected_reads.append(mock.call(path, 512 * 1024))
                row = {"component": prefix, "file": name, "bytes": len(raw), "sha256": H.sha(raw)}
                if name == "source.properties":
                    row["revision"] = "17.0.1"
                expected_metadata.append(row)
        expected_tools = []
        for name, relative in (("adb", "platform-tools/adb"), ("emulator", "emulator/emulator"),
                               ("avdmanager", "cmdline-tools/latest/bin/avdmanager"),
                               ("sdkmanager", "cmdline-tools/latest/bin/sdkmanager")):
            raw = ("synthetic-" + name).encode("ascii")
            path = sdk / relative
            raw_by_path[path] = raw
            expected_reads.append(mock.call(path, 128 * 1024 * 1024))
            expected_tools.append({"tool": name, "bytes": len(raw), "sha256": H.sha(raw)})
        reads = []

        def read(path, maximum):
            reads.append(mock.call(path, maximum))
            return raw_by_path[path]

        def tree(path, *, maximum_files, maximum_bytes):
            self.assertEqual(reads, expected_reads)
            self.assertEqual(path, sdk)
            self.assertEqual(maximum_files, 30000)
            self.assertEqual(maximum_bytes, 8 * 1024 ** 3)
            return "c" * 64

        self.assertEqual(Q.SDK_TREE_MAXIMUM_BYTES, 8 * 1024 ** 3)
        with mock.patch.object(H, "read_plain", side_effect=read) as files, mock.patch.object(H, "tree_digest", side_effect=tree) as digest, mock.patch.object(H, "Managed", side_effect=AssertionError("native")) as managed:
            observed = Q.sdk_inventory(sdk)
        self.assertEqual(files.call_args_list, expected_reads)
        digest.assert_called_once_with(sdk, maximum_files=30000, maximum_bytes=8 * 1024 ** 3)
        managed.assert_not_called()
        self.assertEqual(observed, {"tree_sha256": "c" * 64, "metadata": expected_metadata,
                                   "tools": expected_tools, "catalog_approval": False,
                                   "license_approval": False, "whole_image_semantic_closure": "not-established"})

    def test_scoped_overflow_still_refuses_and_old_budget_metrics_are_omitted(self):
        sdk = Path("/owned-sdk")
        original = H.Refusal("tree-total-byte-bound")
        original.tree_limit_observation = self.observation()
        with mock.patch.object(H, "read_plain", return_value=b"Pkg.Revision=1\n") as files, mock.patch.object(H, "tree_digest", side_effect=original) as digest, mock.patch.object(H, "Managed", side_effect=AssertionError("native")) as managed:
            with self.assertRaises(H.Refusal) as caught:
                Q.sdk_inventory(sdk)
        self.assertIs(caught.exception, original)
        self.assertEqual(files.call_count, 14)
        digest.assert_called_once_with(sdk, maximum_files=30000, maximum_bytes=8 * 1024 ** 3)
        managed.assert_not_called()
        record = Q.capture_refusal_diagnostic(original, "sdk-observation")
        self.assertEqual(record["refusal_code"], "tree-total-byte-bound")
        self.assertEqual(record["sdk_tree_limit"]["maximum_bytes"], 8 * 1024 ** 3)
        self.assertFalse(record["sdk_tree_limit"]["complete"])
        self.assertFalse(record["sdk_tree_limit"]["file_digest_observed"])
        self.assertFalse(record["approval"])
        self.assertEqual(record["readiness_credit"], 0)
        stale = H.Refusal("tree-total-byte-bound")
        stale.tree_limit_observation = {**self.observation(), "maximum_bytes": 4 * 1024 ** 3,
                                       "sampled_stat_bytes": 4 * 1024 ** 3 + 1}
        stale_record = Q.capture_refusal_diagnostic(stale, "sdk-observation")
        self.assertEqual(stale_record["refusal_code"], "tree-total-byte-bound")
        self.assertNotIn("sdk_tree_limit", stale_record)
        self.assertFalse(stale_record["approval"])


class OwnedProcessDiagnosticTests(unittest.TestCase):
    @staticmethod
    def leader(role="adb", failed=False, status=1):
        leader = object.__new__(H.Managed)
        leader.failed = mock.Mock()
        leader.failed.is_set.return_value = failed
        leader.child = SimpleNamespace(poll=mock.Mock(return_value=status))
        leader.buffers = [bytearray(b"private stdout"), bytearray(b"private stderr")]
        leader._public_caller_role = role
        return leader

    @staticmethod
    def observation(role="adb", failed=False, status=1):
        return {"role": role, "reason": "pipe-failed" if failed else "leader-exited",
                "pipe_failed": failed, "poll_observed": not failed,
                "exit_status": None if failed else status,
                "stdout_retained_bytes": 4194304, "stderr_retained_bytes": 1048576,
                "counts_partial": True}

    def test_pipe_failure_short_circuit_never_polls(self):
        for role in ("adb", "emulator"):
            leader = self.leader(role, failed=True)
            with self.subTest(role=role), self.assertRaises(H.Refusal) as error:
                leader.live()
            self.assertEqual(error.exception.args, ("owned-leader-or-pipe-unavailable",))
            leader.failed.is_set.assert_called_once_with()
            leader.child.poll.assert_not_called()
            value = error.exception.owned_process_observation
            self.assertTrue(value["pipe_failed"])
            self.assertFalse(value["poll_observed"])
            self.assertIsNone(value["exit_status"])
            self.assertEqual(value["role"], role)
            self.assertEqual(value["stdout_retained_bytes"], len(b"private stdout"))
            self.assertEqual(value["stderr_retained_bytes"], len(b"private stderr"))
            self.assertTrue(value["counts_partial"])
            self.assertNotIn("private", json.dumps(value))

    def test_exited_leader_samples_existing_poll_once(self):
        for role in ("adb", "emulator"):
            for status in (0, 1, -9):
                leader = self.leader(role, status=status)
                with self.subTest(role=role, status=status), self.assertRaises(H.Refusal) as error:
                    leader.live()
                leader.failed.is_set.assert_called_once_with()
                leader.child.poll.assert_called_once_with()
                value = error.exception.owned_process_observation
                self.assertEqual(value["reason"], "leader-exited")
                self.assertEqual(value["exit_status"], status)
                self.assertTrue(value["poll_observed"])
                self.assertFalse(value["pipe_failed"])
                self.assertTrue(value["counts_partial"])

    def test_running_leader_retains_existing_acceptance(self):
        leader = self.leader(status=None)
        self.assertIsNone(leader.live())
        leader.failed.is_set.assert_called_once_with()
        leader.child.poll.assert_called_once_with()

    def test_diagnostic_failure_cannot_replace_liveness_refusal(self):
        for failure in (RuntimeError("/private/diagnostic"), KeyboardInterrupt("/private/interrupt")):
            leader = self.leader()
            with self.subTest(kind=type(failure).__name__), mock.patch.object(H, "_owned_live_observation", side_effect=failure), self.assertRaises(H.Refusal) as error:
                leader.live()
            self.assertEqual(error.exception.args, ("owned-leader-or-pipe-unavailable",))
            self.assertNotIn("owned_process_observation", error.exception.__dict__)
            leader.child.poll.assert_called_once_with()

    def test_unclassified_caller_or_malformed_private_snapshot_is_omitted(self):
        class HostileString(str):
            def __hash__(self):
                raise AssertionError("hash")
            def __str__(self):
                raise AssertionError("stringification")
        cases = ({"role": "/private/role"}, {"role": HostileString("adb")},
                 {"status": True}, {"status": 2 ** 31}, {"status": -(2 ** 31) - 1})
        for case in cases:
            leader = self.leader(**case)
            with self.subTest(case=list(case)), self.assertRaises(H.Refusal) as error:
                leader.live()
            self.assertEqual(error.exception.args, ("owned-leader-or-pipe-unavailable",))
            self.assertNotIn("owned_process_observation", error.exception.__dict__)

    def test_fixed_phase_role_stage_exit_and_partial_counts_project_within_bound(self):
        for role in ("adb", "emulator"):
            for failed, status in ((True, None), (False, -(2 ** 31)), (False, 2 ** 31 - 1)):
                value = self.observation(role, failed, status)
                error = H.Refusal("owned-leader-or-pipe-unavailable")
                error.owned_process_observation = value
                for stage in Q.OWNED_PROCESS_SUBSTAGES:
                    with self.subTest(role=role, failed=failed, status=status, stage=stage):
                        record = Q.capture_refusal_diagnostic(error, "owned-api36-emulator", stage)
                        self.assertEqual(record["owned_process"], value)
                        self.assertEqual(record["owned_substage"], stage)
                        self.assertFalse(record["approval"])
                        self.assertEqual(record["readiness_credit"], 0)
                        raw = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
                        self.assertTrue(raw.isascii())
                        self.assertLessEqual(len(raw), 512)
                        self.assertNotIn("private", raw)

    def test_malformed_or_private_projection_fields_are_never_published(self):
        class HostileString(str):
            def __hash__(self):
                raise AssertionError("hash")
            def __str__(self):
                raise AssertionError("stringification")
        base = self.observation()
        cases = (None, [], {**base, "path": "/private/path"},
                 {k: v for k, v in base.items() if k != "role"},
                 {(1 if k == "role" else k): v for k, v in base.items()},
                 {**base, "role": "/private/role"}, {**base, "role": HostileString("adb")},
                 {**base, "reason": HostileString("leader-exited")},
                 {**base, "reason": "pipe-failed"}, {**base, "pipe_failed": 0},
                 {**base, "poll_observed": False}, {**base, "exit_status": None},
                 {**base, "exit_status": True}, {**base, "exit_status": 2 ** 31},
                 {**base, "stdout_retained_bytes": True}, {**base, "stdout_retained_bytes": -1},
                 {**base, "stdout_retained_bytes": 4194305}, {**base, "stderr_retained_bytes": 1048577},
                 {**base, "counts_partial": False},
                 {**self.observation(failed=True), "poll_observed": True},
                 {**self.observation(failed=True), "exit_status": 0})
        for index, value in enumerate(cases):
            error = H.Refusal("owned-leader-or-pipe-unavailable")
            error.owned_process_observation = value
            with self.subTest(index=index):
                record = Q.capture_refusal_diagnostic(error, "owned-api36-emulator", HostileString("adb-listener"))
                self.assertNotIn("owned_process", record)
                self.assertNotIn("owned_substage", record)
                self.assertNotIn("private", json.dumps(record))

    def test_other_phase_code_and_exception_subclass_omit_process_snapshot(self):
        class RefusalSubclass(H.Refusal):
            pass
        for phase, error in (("sdk-observation", H.Refusal("owned-leader-or-pipe-unavailable")),
                             ("owned-api36-emulator", H.Refusal("tree-hardlink")),
                             ("owned-api36-emulator", RefusalSubclass("owned-leader-or-pipe-unavailable"))):
            error.owned_process_observation = self.observation()
            with self.subTest(phase=phase, kind=type(error).__name__):
                record = Q.capture_refusal_diagnostic(error, phase, "adb-listener")
                self.assertNotIn("owned_process", record)
                self.assertFalse(record["approval"])

    def test_capture_trusted_role_substage_original_refusal_and_cleanup_are_preserved(self):
        for failed_role in ("adb", "emulator"):
            with self.subTest(failed_role=failed_role), fixture() as root:
                (root / ".tmp").mkdir()
                sdk = root / "owned-sdk"
                avd = SimpleNamespace(child=SimpleNamespace(stdin=mock.Mock()), zero=mock.Mock(),
                                      buffers=[bytearray(), bytearray()])
                adb, emulator = self.leader("adb", status=None), self.leader("emulator")
                if failed_role == "adb":
                    adb.child.poll.return_value = 1
                born, originals = [], []
                managed_type = H.Managed

                def managed(argv, env, cwd, born=born, avd=avd, adb=adb, emulator=emulator):
                    leader = (avd, adb, emulator)[len(born)]
                    born.append(leader)
                    return leader

                def live(leader, managed_type=managed_type, originals=originals):
                    try:
                        managed_type.live(leader)
                    except H.Refusal as error:
                        originals.append(error)
                        raise

                def listener(leader, port, adb=adb, live=live):
                    self.assertIs(leader, adb)
                    self.assertEqual(leader._public_caller_role, "adb")
                    live(leader)
                    return True

                emulator.live = lambda emulator=emulator, live=live: live(emulator)
                stream = io.StringIO()
                with mock.patch.dict(os.environ, {"ANDROID_HOME": str(sdk)}, clear=True), mock.patch.object(Q, "event_guard", return_value={}), mock.patch.object(Q, "commands", return_value=(object(), 0)), mock.patch.object(Q, "source_binding", return_value={}), mock.patch.object(Q, "clone_guard", return_value=({}, {})), mock.patch.object(Q, "owned_sdk", return_value=sdk), mock.patch.object(Q, "sdk_inventory", return_value={"tree_sha256": "e" * 64}), mock.patch.object(Q.time, "monotonic", return_value=0), mock.patch.object(Q.socket, "socket", return_value=mock.MagicMock()), mock.patch.object(H, "Managed", side_effect=managed) as provider, mock.patch.object(H, "owned_listener", side_effect=listener), mock.patch.object(H, "AdbSocket", return_value=object()), mock.patch.object(Q, "public_receipt", side_effect=RuntimeError("/private/publisher")), mock.patch.object(H, "cleanup_all", return_value=[]) as cleanup, mock.patch.object(sys, "stderr", stream):
                    with self.assertRaises(H.Refusal) as error:
                        Q.capture(root)
                    self.assertIs(error.exception, originals[0])
                    self.assertEqual(provider.call_count, 2 if failed_role == "adb" else 3)
                    cleanup.assert_called_once_with(born)
                record = json.loads(stream.getvalue())
                self.assertEqual(record["owned_process"]["role"], failed_role)
                self.assertEqual(record["owned_process"]["exit_status"], 1)
                self.assertEqual(record["owned_substage"], "adb-listener" if failed_role == "adb" else "device-connect")
                self.assertFalse(record["approval"])
                self.assertEqual(record["readiness_credit"], 0)
                self.assertNotIn("private", stream.getvalue())


class OwnedListenerOperationDiagnosticTests(unittest.TestCase):
    @staticmethod
    def providers():
        leader = SimpleNamespace(live=mock.Mock(), child=SimpleNamespace(pid=123))
        directory = mock.MagicMock()
        directory.__enter__.return_value = [SimpleNamespace(path="/PRIVATE/fd")]
        table = mock.MagicMock()
        stream = table.__enter__.return_value
        stream.read.return_value = b"header\n0: 0100007F:13AF 00000000:0000 0A x x x x x 123\n"
        return leader, directory, table, stream

    def test_missing_and_access_errors_keep_entered_operation_and_same_exception(self):
        class BrokenEntries:
            def __init__(self, error):
                self.error = error

            def __iter__(self):
                raise self.error

        stages = ("leader-before", "fd-directory-open", "fd-enumeration", "fd-readlink",
                  "socket-table-open", "socket-table-read", "leader-after")
        for error_type in (FileNotFoundError, PermissionError):
            for stage in stages:
                leader, directory, table, stream = self.providers()
                original = error_type("/PRIVATE/source")
                if stage == "leader-before":
                    leader.live.side_effect = original
                elif stage == "leader-after":
                    leader.live.side_effect = [None, original]
                elif stage == "fd-enumeration":
                    directory.__enter__.return_value = BrokenEntries(original)
                elif stage == "socket-table-read":
                    stream.read.side_effect = original
                with self.subTest(error=error_type.__name__, stage=stage), \
                     mock.patch.object(H.os, "scandir", side_effect=original if stage == "fd-directory-open" else None, return_value=directory) as scanned, \
                     mock.patch.object(H.os, "readlink", side_effect=original if stage == "fd-readlink" else None, return_value="socket:[123]") as linked, \
                     mock.patch.object(Path, "open", side_effect=original if stage == "socket-table-open" else None, return_value=table) as opened, \
                     mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
                    with self.assertRaises(error_type) as caught:
                        H.owned_listener(leader, H.ADB_PORT)
                    self.assertIs(caught.exception, original)
                    self.assertEqual(original.owned_listener_stage, stage)
                    self.assertEqual(leader.live.call_count, 2 if stage == "leader-after" else 1)
                    if stage == "leader-before":
                        scanned.assert_not_called()
                    else:
                        scanned.assert_called_once_with(Path("/proc") / "123" / "fd")
                    self.assertLessEqual(linked.call_count, 1)
                    self.assertLessEqual(opened.call_count, 1)
                    self.assertLessEqual(stream.read.call_count, 1)
                    native.assert_not_called()

    def test_context_close_failure_remains_original_and_is_not_retried(self):
        for stage in ("fd-directory-close", "socket-table-close"):
            leader, directory, table, stream = self.providers()
            original = FileNotFoundError("/PRIVATE/close")
            (directory if stage == "fd-directory-close" else table).__exit__.side_effect = original
            with self.subTest(stage=stage), mock.patch.object(H.os, "scandir", return_value=directory), \
                 mock.patch.object(H.os, "readlink", return_value="socket:[123]"), \
                 mock.patch.object(Path, "open", return_value=table), \
                 mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
                with self.assertRaises(FileNotFoundError) as caught:
                    H.owned_listener(leader, H.ADB_PORT)
                self.assertIs(caught.exception, original)
                self.assertEqual(original.owned_listener_stage, stage)
                directory.__exit__.assert_called_once()
                if stage == "socket-table-close":
                    table.__exit__.assert_called_once()
                self.assertEqual(leader.live.call_count, 1)
                native.assert_not_called()

    def test_success_keeps_calls_and_exact_owned_listener_requirement(self):
        leader, directory, table, stream = self.providers()
        with mock.patch.object(H.os, "scandir", return_value=directory) as scanned, \
             mock.patch.object(H.os, "readlink", return_value="socket:[123]") as linked, \
             mock.patch.object(Path, "open", return_value=table) as opened, \
             mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
            self.assertTrue(H.owned_listener(leader, H.ADB_PORT))
            self.assertEqual(leader.live.call_count, 2)
            scanned.assert_called_once_with(Path("/proc") / "123" / "fd")
            linked.assert_called_once_with("/PRIVATE/fd")
            opened.assert_called_once_with("rb")
            stream.read.assert_called_once_with(1024 * 1024 + 1)
            directory.__exit__.assert_called_once()
            table.__exit__.assert_called_once()
            native.assert_not_called()

    def test_missing_foreign_and_malformed_listener_remain_refusals(self):
        for case, code, stage in (("missing", "owned-loopback-listener-missing", "listener-match"),
                                  ("foreign", "owned-loopback-listener-unproved", "listener-match"),
                                  ("layout", "owned-socket-table-layout", "socket-table-parse"),
                                  ("bound", "owned-socket-table-bound", "socket-table-bound")):
            leader, directory, table, stream = self.providers()
            if case == "missing":
                stream.read.return_value = b"header\n"
            elif case == "layout":
                stream.read.return_value = b"header\nmalformed\n"
            elif case == "bound":
                stream.read.return_value = b"x" * (1024 * 1024 + 1)
            with self.subTest(case=case), mock.patch.object(H.os, "scandir", return_value=directory), \
                 mock.patch.object(H.os, "readlink", return_value="socket:[321]" if case == "foreign" else "socket:[123]"), \
                 mock.patch.object(Path, "open", return_value=table), \
                 mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
                with self.assertRaises(H.Refusal) as caught:
                    H.owned_listener(leader, H.ADB_PORT)
                self.assertEqual(caught.exception.args, (code,))
                self.assertEqual(caught.exception.owned_listener_stage, stage)
                self.assertEqual(leader.live.call_count, 2 if case in ("missing", "foreign") else 1)
                stream.read.assert_called_once_with(1024 * 1024 + 1)
                native.assert_not_called()

    def test_attachment_failure_cannot_replace_body_error(self):
        class Unattachable(FileNotFoundError):
            def __setattr__(self, name, value):
                if name == "owned_listener_stage":
                    raise KeyboardInterrupt("/PRIVATE/attachment")
                return super().__setattr__(name, value)

        leader, directory, table, stream = self.providers()
        original = Unattachable("/PRIVATE/readlink")
        with mock.patch.object(H.os, "scandir", return_value=directory), \
             mock.patch.object(H.os, "readlink", side_effect=original), \
             mock.patch.object(Path, "open", return_value=table) as opened, \
             mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
            with self.assertRaises(Unattachable) as caught:
                H.owned_listener(leader, H.ADB_PORT)
            self.assertIs(caught.exception, original)
            self.assertNotIn("owned_listener_stage", original.__dict__)
            self.assertEqual(leader.live.call_count, 1)
            opened.assert_not_called()
            native.assert_not_called()

    def test_fixed_operation_projection_is_private_typed_and_bounded(self):
        for stage in H.OWNED_LISTENER_STAGES:
            for kind in ("missing", "access", "leader"):
                error = (FileNotFoundError("/PRIVATE/path") if kind == "missing" else
                         PermissionError("/PRIVATE/path") if kind == "access" else
                         H.Refusal("owned-leader-or-pipe-unavailable"))
                error.owned_listener_stage = stage
                if kind == "leader":
                    error.owned_process_observation = OwnedProcessDiagnosticTests.observation("emulator", status=-(2 ** 31))
                with self.subTest(stage=stage, kind=kind):
                    record = Q.capture_refusal_diagnostic(error, "owned-api36-emulator", "port-reservation")
                    self.assertEqual(record["owned_listener_stage"], stage)
                    self.assertEqual(record["refusal_code"], "missing-input" if kind == "missing" else
                                     "input-access-refused" if kind == "access" else "owned-leader-or-pipe-unavailable")
                    self.assertFalse(record["approval"])
                    self.assertEqual(record["readiness_credit"], 0)
                    raw = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
                    self.assertTrue(raw.isascii())
                    self.assertLessEqual(len(raw), 512)
                    self.assertNotIn("PRIVATE", raw)
                    if kind != "leader":
                        self.assertNotIn("owned_process", record)

    def test_unknown_hostile_stage_family_and_phase_are_omitted(self):
        class Hostile(str):
            def __str__(self):
                raise AssertionError("private text")

            def __hash__(self):
                raise AssertionError("private hash")

        class OtherMissing(FileNotFoundError):
            pass

        for value in (None, True, b"fd-readlink", "/PRIVATE/operation", Hostile("fd-readlink")):
            error = FileNotFoundError("/PRIVATE/path")
            error.owned_listener_stage = value
            with self.subTest(value=type(value).__name__):
                record = Q.capture_refusal_diagnostic(error, "owned-api36-emulator", "adb-listener")
                self.assertNotIn("owned_listener_stage", record)
                self.assertNotIn("PRIVATE", json.dumps(record))
        for phase, error in (("sdk-observation", FileNotFoundError("PRIVATE")),
                             ("owned-api36-emulator", OtherMissing("PRIVATE")),
                             ("owned-api36-emulator", RuntimeError("PRIVATE")),
                             ("owned-api36-emulator", H.Refusal("tree-hardlink")),
                             ("owned-api36-emulator", H.Refusal("PRIVATE"))):
            error.owned_listener_stage = "fd-readlink"
            with self.subTest(phase=phase, kind=type(error).__name__):
                record = Q.capture_refusal_diagnostic(error, phase, "adb-listener")
                self.assertNotIn("owned_listener_stage", record)
                self.assertNotIn("PRIVATE", json.dumps(record))


class AdbFixedMessageMarkerTests(unittest.TestCase):
    @staticmethod
    def leader(raw=b"", role="adb", failed=False, status=-6):
        leader = OwnedProcessDiagnosticTests.leader(role, failed=failed, status=status)
        leader.buffers = [bytearray(), bytearray(raw)]
        return leader

    def refused(self, leader):
        with mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
            with self.assertRaises(H.Refusal) as caught:
                leader.live()
            native.assert_not_called()
        self.assertEqual(caught.exception.args, ("owned-leader-or-pipe-unavailable",))
        leader.failed.is_set.assert_called_once_with()
        if leader.failed.is_set.return_value:
            leader.child.poll.assert_not_called()
        else:
            leader.child.poll.assert_called_once_with()
        return caught.exception

    def test_each_public_literal_projects_its_bit_without_private_suffix(self):
        for bit, literal in H.ADB_MESSAGE_MARKERS:
            raw = b"PRIVATE/path PID errno " + literal + b"PRIVATE/dynamic-suffix"
            leader = self.leader(raw)
            with self.subTest(bit=bit):
                error = self.refused(leader)
                observed = error.owned_process_observation
                self.assertEqual(observed["adb_message_bits"], bit)
                self.assertEqual(observed["stderr_retained_bytes"], len(raw))
                self.assertTrue(observed["counts_partial"])
                record = Q.capture_refusal_diagnostic(error, "owned-api36-emulator", "adb-listener")
                self.assertEqual(record["owned_process"], observed)
                self.assertFalse(record["approval"])
                self.assertEqual(record["readiness_credit"], 0)
                self.assertNotIn("PRIVATE", json.dumps(record))

    def test_unknown_empty_case_changed_and_incomplete_literals_are_zero(self):
        cases = [b"", b"PRIVATE unknown fatal", b"\x00\xff\x80"]
        for _, literal in H.ADB_MESSAGE_MARKERS:
            cases.extend((literal[:-1], literal.upper()))
        for index, raw in enumerate(cases):
            with self.subTest(index=index):
                observed = self.refused(self.leader(raw)).owned_process_observation
                self.assertEqual(observed["adb_message_bits"], 0)
                self.assertTrue(observed["counts_partial"])

    def test_multiple_and_repeated_markers_preserve_all_bits_without_order_claim(self):
        literals = [literal for _, literal in H.ADB_MESSAGE_MARKERS]
        cases = (b"\n".join(literals), b"\n".join(reversed(literals)), b"\n".join(literals * 2))
        for index, raw in enumerate(cases):
            with self.subTest(index=index):
                observed = self.refused(self.leader(raw)).owned_process_observation
                self.assertEqual(observed["adb_message_bits"], 31)
                self.assertTrue(observed["counts_partial"])

    def test_prefix_boundary_requires_the_complete_literal_inside_the_snapshot(self):
        bit, literal = H.ADB_MESSAGE_MARKERS[0]
        cases = ((b"x" * (4096 - len(literal)) + literal, bit),
                 (b"x" * 4096 + literal, 0),
                 (b"x" * (4097 - len(literal)) + literal, 0),
                 (literal + b"x" * (4096 - len(literal)) + H.ADB_MESSAGE_MARKERS[1][1], bit))
        for index, (raw, expected) in enumerate(cases):
            leader = self.leader(raw)
            with self.subTest(index=index):
                observed = self.refused(leader).owned_process_observation
                self.assertEqual(observed["adb_message_bits"], expected)
                self.assertEqual(observed["stderr_retained_bytes"], len(raw))

    def test_classifier_rejects_wrong_types_and_oversized_inputs(self):
        class HostileBytes(bytes):
            def __len__(self):
                raise AssertionError("private length")

        cases = (None, True, bytearray(b"unknown"), "PRIVATE", b"x" * 4097, HostileBytes(b"unknown"))
        for index, prefix in enumerate(cases):
            with self.subTest(index=index):
                self.assertIsNone(H._adb_message_bits(prefix))
        leader = self.leader(b"x" * (1024 * 1024 + 1))
        with mock.patch.object(H, "_adb_message_bits", side_effect=AssertionError("classifier")) as classified:
            error = self.refused(leader)
            self.assertNotIn("owned_process_observation", error.__dict__)
            classified.assert_not_called()

    def test_classifier_observes_one_immutable_partial_snapshot(self):
        bit, literal = H.ADB_MESSAGE_MARKERS[0]
        leader = self.leader(literal)
        original_classifier = H._adb_message_bits
        received = []

        def classify(prefix):
            received.append(prefix)
            leader.buffers[1][:] = b"PRIVATE replacement after snapshot"
            return original_classifier(prefix)

        with mock.patch.object(H, "_adb_message_bits", side_effect=classify) as classified:
            observed = self.refused(leader).owned_process_observation
            classified.assert_called_once_with(literal)
        self.assertEqual(len(received), 1)
        self.assertIs(type(received[0]), bytes)
        self.assertEqual(received[0], literal)
        self.assertEqual(observed["adb_message_bits"], bit)
        self.assertEqual(observed["stderr_retained_bytes"], len(literal))
        self.assertTrue(observed["counts_partial"])

    def test_wrong_context_retains_original_short_circuit_without_classifying(self):
        cases = (("emulator", False, -6), ("adb", True, -6), ("adb", False, -9),
                 ("adb", False, 0), ("adb", False, True), ("PRIVATE", False, -6),
                 ("adb", False, 2 ** 31))
        for role, failed, status in cases:
            leader = self.leader(H.ADB_MESSAGE_MARKERS[0][1], role, failed, status)
            with self.subTest(role=role, failed=failed, status=status), \
                 mock.patch.object(H, "_adb_message_bits", side_effect=AssertionError("classifier")) as classified:
                error = self.refused(leader)
                observed = error.__dict__.get("owned_process_observation")
                if observed is not None:
                    self.assertNotIn("adb_message_bits", observed)
                classified.assert_not_called()
        leader = self.leader(H.ADB_MESSAGE_MARKERS[0][1])
        for failed, polled in ((0, True), (False, 1)):
            with self.subTest(failed=failed, polled=polled):
                self.assertIsNone(H._owned_live_observation(leader, failed, polled, -6))

    def test_classifier_and_snapshot_interruptions_keep_original_error_and_eight_fields(self):
        refusal_type = H.Refusal
        failures = (RuntimeError("PRIVATE classifier"), KeyboardInterrupt("PRIVATE interrupt"),
                    SystemExit("PRIVATE exit"))
        for failure in failures:
            leader = self.leader(H.ADB_MESSAGE_MARKERS[0][1])
            original = refusal_type("owned-leader-or-pipe-unavailable")
            with self.subTest(failure=type(failure).__name__), \
                 mock.patch.object(H, "Refusal", return_value=original), \
                 mock.patch.object(H, "_adb_message_bits", side_effect=failure) as classified, \
                 mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
                with self.assertRaises(refusal_type) as caught:
                    leader.live()
                self.assertIs(caught.exception, original)
                self.assertEqual(len(original.owned_process_observation), 8)
                self.assertNotIn("adb_message_bits", original.owned_process_observation)
                self.assertNotIn("PRIVATE", json.dumps(original.owned_process_observation))
                classified.assert_called_once()
                leader.failed.is_set.assert_called_once_with()
                leader.child.poll.assert_called_once_with()
                native.assert_not_called()
        leader = self.leader(H.ADB_MESSAGE_MARKERS[0][1])
        original = refusal_type("owned-leader-or-pipe-unavailable")
        with mock.patch.object(H, "Refusal", return_value=original), \
             mock.patch.object(H, "bytes", side_effect=KeyboardInterrupt("PRIVATE snapshot"), create=True), \
             mock.patch.object(H, "_adb_message_bits", side_effect=AssertionError("classifier")) as classified:
            with self.assertRaises(refusal_type) as caught:
                leader.live()
            self.assertIs(caught.exception, original)
            self.assertEqual(len(original.owned_process_observation), 8)
            classified.assert_not_called()
            leader.child.poll.assert_called_once_with()

    def test_malformed_classifier_results_preserve_old_observation(self):
        class Hostile:
            def __str__(self):
                raise AssertionError("private stringify")

        for result in (None, True, -1, 32, "PRIVATE", Hostile()):
            leader = self.leader(H.ADB_MESSAGE_MARKERS[0][1])
            with self.subTest(kind=type(result).__name__), \
                 mock.patch.object(H, "_adb_message_bits", return_value=result) as classified:
                observed = self.refused(leader).owned_process_observation
                self.assertEqual(len(observed), 8)
                self.assertNotIn("adb_message_bits", observed)
                classified.assert_called_once()
                self.assertNotIn("PRIVATE", json.dumps(observed))

    def test_every_allowed_bit_combination_has_the_closed_typed_projection(self):
        for bits in range(32):
            value = {**OwnedProcessDiagnosticTests.observation(status=-6), "adb_message_bits": bits}
            error = H.Refusal("owned-leader-or-pipe-unavailable")
            error.owned_process_observation = value
            with self.subTest(bits=bits):
                record = Q.capture_refusal_diagnostic(error, "owned-api36-emulator", "adb-listener")
                self.assertEqual(record["owned_process"], value)
                self.assertEqual(set(record["owned_process"]), set(value))
                self.assertFalse(record["approval"])
                self.assertEqual(record["readiness_credit"], 0)

    def test_optional_key_rejects_malformed_types_private_keys_and_wrong_context(self):
        class HostileInt(int):
            def __str__(self):
                raise AssertionError("private stringify")

        base = {**OwnedProcessDiagnosticTests.observation(status=-6), "adb_message_bits": 1}
        cases = [{**base, "adb_message_bits": value}
                 for value in (None, True, False, -1, 32, "PRIVATE", HostileInt(1))]
        cases.extend(({**base, "pid": 123}, {key: value for key, value in base.items() if key != "role"},
                      {**base, "role": "emulator"}, {**base, "exit_status": 0},
                      {**base, "exit_status": True}, {**base, "poll_observed": False},
                      {**base, "reason": "pipe-failed"}, {**base, "counts_partial": False},
                      {**base, "pipe_failed": True, "poll_observed": False,
                       "reason": "pipe-failed", "exit_status": None},
                      {**base, "stdout_retained_bytes": 4194305}))
        for index, value in enumerate(cases):
            error = H.Refusal("owned-leader-or-pipe-unavailable")
            error.owned_process_observation = value
            with self.subTest(index=index):
                record = Q.capture_refusal_diagnostic(error, "owned-api36-emulator", "adb-listener")
                self.assertNotIn("owned_process", record)
                self.assertNotIn("PRIVATE", json.dumps(record))

    def test_all_existing_substage_listener_combinations_stay_within_ascii_cap(self):
        value = {**OwnedProcessDiagnosticTests.observation(status=-6), "adb_message_bits": 31}
        maximum = 0
        for substage in Q.OWNED_PROCESS_SUBSTAGES:
            for entered in H.OWNED_LISTENER_STAGES:
                error = H.Refusal("owned-leader-or-pipe-unavailable")
                error.owned_process_observation = value
                error.owned_listener_stage = entered
                with self.subTest(substage=substage, entered=entered):
                    record = Q.capture_refusal_diagnostic(error, "owned-api36-emulator", substage)
                    self.assertEqual(record["owned_process"], value)
                    self.assertEqual(record["owned_listener_stage"], entered)
                    self.assertEqual(record["owned_substage"], substage)
                    raw = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
                    maximum = max(maximum, len(raw))
                    self.assertTrue(raw.isascii())
                    self.assertLessEqual(len(raw), 512)
                    self.assertLessEqual(len(raw + "\n"), 512)
                    self.assertFalse(record["approval"])
                    self.assertEqual(record["readiness_credit"], 0)
        self.assertEqual(maximum, 483)

    def test_listener_start_refusal_keeps_marker_without_proc_or_native_calls(self):
        leader = self.leader(H.ADB_MESSAGE_MARKERS[0][1])
        with mock.patch.object(H.os, "scandir", side_effect=AssertionError("proc")) as scanned, \
             mock.patch.object(H.os, "readlink", side_effect=AssertionError("readlink")) as linked, \
             mock.patch.object(Path, "open", side_effect=AssertionError("open")) as opened, \
             mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
            with self.assertRaises(H.Refusal) as caught:
                H.owned_listener(leader, H.ADB_PORT)
            self.assertEqual(caught.exception.args, ("owned-leader-or-pipe-unavailable",))
            self.assertEqual(caught.exception.owned_listener_stage, "leader-before")
            self.assertEqual(caught.exception.owned_process_observation["adb_message_bits"], 1)
            leader.failed.is_set.assert_called_once_with()
            leader.child.poll.assert_called_once_with()
            scanned.assert_not_called()
            linked.assert_not_called()
            opened.assert_not_called()
            native.assert_not_called()

    def test_running_leader_keeps_acceptance_without_classifier(self):
        leader = self.leader(H.ADB_MESSAGE_MARKERS[0][1], status=None)
        with mock.patch.object(H, "_adb_message_bits", side_effect=AssertionError("classifier")) as classified:
            self.assertIsNone(leader.live())
            classified.assert_not_called()
            leader.failed.is_set.assert_called_once_with()
            leader.child.poll.assert_called_once_with()


class AdbServerListenContractTests(unittest.TestCase):
    @staticmethod
    def leader(output=b"{}"):
        return SimpleNamespace(child=SimpleNamespace(stdin=mock.Mock()), zero=mock.Mock(),
                               buffers=[bytearray(output), bytearray()])

    @staticmethod
    def reservations():
        values = [mock.MagicMock() for _ in range(3)]
        for value in values:
            value.__enter__.return_value = value
        return values

    def test_hosted_run_uses_localhost_server_and_numeric_client_before_early_refusal(self):
        with fixture() as root:
            (root / ".tmp").mkdir()
            source = root / "tests/mobile-browser"
            source.mkdir(parents=True)
            sdk = root / "owned-sdk"
            digest, raw = "f" * 64, b"{}"
            tools = {name: {"path": str(sdk / name), "sha256": digest}
                     for name in ("adb", "avdmanager", "emulator")}
            pins = {"npm_lock_sha256": digest, "npm_tree_sha256": digest,
                    "sdk_tree_sha256": digest, "tools": tools}
            leaders = [self.leader(raw) for _ in range(6)]
            reservations = self.reservations()
            births = []
            original = H.Refusal("owned-leader-or-pipe-unavailable")

            def managed(argv, env, cwd):
                self.assertIs(cwd, root)
                self.assertEqual(env["ADB_SERVER_SOCKET"], "tcp:127.0.0.1:5039")
                self.assertEqual(env["ANDROID_ADB_SERVER_PORT"], "5039")
                if len(births) == 5:
                    self.assertEqual(argv, [tools["adb"]["path"], "-L", "tcp:localhost:5039", "nodaemon", "server"])
                    for reservation, port in zip(reservations, (5039, 5556, 5557), strict=True):
                        reservation.bind.assert_called_once_with(("127.0.0.1", port))
                        reservation.__exit__.assert_called_once()
                self.assertLess(len(births), 6)
                leader = leaders[len(births)]
                births.append((argv, env.copy(), leader))
                return leader

            environment = env_data(root, root / "event.json")
            environment["ANDROID_HOME"] = str(sdk)
            with ExitStack() as patches:
                patches.enter_context(mock.patch.dict(os.environ, environment, clear=True))
                patches.enter_context(mock.patch.object(H, "HERE", source))
                host = patches.enter_context(mock.patch.object(H, "host_guard"))
                patches.enter_context(mock.patch.object(H, "validate_pins", return_value=pins))
                patches.enter_context(mock.patch.object(H, "read_plain", return_value=raw))
                patches.enter_context(mock.patch.object(H, "sha", return_value=digest))
                patches.enter_context(mock.patch.object(H, "tree_digest", return_value=digest))
                guard = patches.enter_context(mock.patch.object(H, "source_guard", return_value={"live_manifest": {}}))
                patches.enter_context(mock.patch.object(H.time, "monotonic", return_value=0))
                sockets = patches.enter_context(mock.patch.object(H.socket, "socket", side_effect=reservations))
                provider = patches.enter_context(mock.patch.object(H, "Managed", side_effect=managed))
                listener = patches.enter_context(mock.patch.object(H, "owned_listener", side_effect=original))
                client = patches.enter_context(mock.patch.object(H, "AdbSocket"))
                cleanup = patches.enter_context(mock.patch.object(H, "cleanup_all", return_value=[{"complete": True}] * 6))
                process = patches.enter_context(mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native birth")))
                with self.assertRaises(H.Refusal) as error:
                    H.run(root, root / "pins.json")
                self.assertIs(error.exception, original)
                host.assert_called_once_with(root)
                guard.assert_called_once_with(root, mock.ANY)
                self.assertEqual(provider.call_count, 6)
                self.assertEqual(sockets.call_count, 3)
                listener.assert_called_once_with(leaders[5], 5039)
                client.assert_not_called()
                process.assert_not_called()
                cleanup.assert_called_once_with(leaders)
            self.assertEqual({row[0][2] for row in births[:4]},
                             {H.SOURCE + ":tests/mobile-browser/" + name for name in
                              ("hosted_controller.py", "android_browser_probe.mjs", "fixture_server.py", "source-manifest.json")})
            for argv, _env, leader in births[:4]:
                self.assertEqual(argv[:2], ["git", "show"])
                leader.child.stdin.write.assert_not_called()
                leader.child.stdin.close.assert_called_once_with()
                leader.zero.assert_called_once_with(30)
            self.assertEqual(births[4][0][0], tools["avdmanager"]["path"])
            leaders[4].child.stdin.write.assert_called_once_with(b"no\n")
            leaders[4].child.stdin.flush.assert_called_once_with()
            leaders[4].child.stdin.close.assert_called_once_with()
            leaders[4].zero.assert_called_once_with(180)
            leaders[5].zero.assert_not_called()
            self.assertNotIn(tools["emulator"]["path"], [row[0][0] for row in births])

    def test_qualification_capture_keeps_order_cleanup_and_refused_receipt(self):
        with fixture() as root:
            (root / ".tmp").mkdir()
            sdk = root / "owned-sdk"
            avd, adb = self.leader(b""), self.leader(b"")
            leaders, births = [avd, adb], []
            reservations = self.reservations()
            original = H.Refusal("owned-leader-or-pipe-unavailable")

            def managed(argv, env, cwd):
                self.assertIs(cwd, root)
                self.assertEqual(env["ADB_SERVER_SOCKET"], "tcp:127.0.0.1:5039")
                self.assertEqual(env["ANDROID_ADB_SERVER_PORT"], "5039")
                if len(births) == 1:
                    self.assertEqual(argv, [str(sdk / "platform-tools/adb"), "-L", "tcp:localhost:5039", "nodaemon", "server"])
                    for reservation, port in zip(reservations, (5039, 5556, 5557), strict=True):
                        reservation.bind.assert_called_once_with(("127.0.0.1", port))
                        reservation.__exit__.assert_called_once()
                self.assertLess(len(births), 2)
                leader = leaders[len(births)]
                births.append((argv, env.copy(), leader))
                return leader

            stream = io.StringIO()
            with ExitStack() as patches:
                patches.enter_context(mock.patch.dict(os.environ, {"ANDROID_HOME": str(sdk)}, clear=True))
                patches.enter_context(mock.patch.object(Q, "event_guard", return_value={}))
                patches.enter_context(mock.patch.object(Q, "commands", return_value=(object(), 0)))
                patches.enter_context(mock.patch.object(Q, "source_binding", return_value={}))
                patches.enter_context(mock.patch.object(Q, "clone_guard", return_value=({}, {})))
                patches.enter_context(mock.patch.object(Q, "owned_sdk", return_value=sdk))
                inventory = patches.enter_context(mock.patch.object(Q, "sdk_inventory", return_value={"tree_sha256": "e" * 64}))
                patches.enter_context(mock.patch.object(Q.time, "monotonic", return_value=0))
                sockets = patches.enter_context(mock.patch.object(Q.socket, "socket", side_effect=reservations))
                provider = patches.enter_context(mock.patch.object(H, "Managed", side_effect=managed))
                listener = patches.enter_context(mock.patch.object(H, "owned_listener", side_effect=original))
                client = patches.enter_context(mock.patch.object(H, "AdbSocket"))
                receipt = patches.enter_context(mock.patch.object(Q, "public_receipt"))
                cleanup = patches.enter_context(mock.patch.object(H, "cleanup_all", return_value=[{"complete": True}] * 2))
                process = patches.enter_context(mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native birth")))
                patches.enter_context(mock.patch.object(sys, "stderr", stream))
                with self.assertRaises(H.Refusal) as error:
                    Q.capture(root)
                self.assertIs(error.exception, original)
                inventory.assert_called_once_with(sdk)
                self.assertEqual(provider.call_count, 2)
                self.assertEqual(sockets.call_count, 3)
                listener.assert_called_once_with(adb, 5039)
                self.assertEqual(adb._public_caller_role, "adb")
                client.assert_not_called()
                process.assert_not_called()
                cleanup.assert_called_once_with(leaders)
                receipt.assert_called_once()
                saved_root, saved = receipt.call_args.args
                self.assertIs(saved_root, root)
                self.assertEqual(saved["status"], "refused")
                self.assertFalse(saved["native_product_or_browser_launch"])
                self.assertFalse(saved["approval"])
                self.assertEqual(saved["readiness_credit"], 0)
            self.assertEqual(births[0][0][0], str(sdk / "cmdline-tools/latest/bin/avdmanager"))
            avd.child.stdin.write.assert_called_once_with(b"no\n")
            avd.child.stdin.flush.assert_called_once_with()
            avd.child.stdin.close.assert_called_once_with()
            avd.zero.assert_called_once_with(180)
            adb.zero.assert_not_called()
            self.assertNotIn(str(sdk / "emulator/emulator"), [row[0][0] for row in births])
            diagnostic = json.loads(stream.getvalue())
            self.assertEqual(diagnostic["owned_substage"], "adb-listener")
            self.assertFalse(diagnostic["approval"])
            self.assertEqual(diagnostic["readiness_credit"], 0)

    def test_direct_client_stays_numeric_without_cli_or_auto_start(self):
        server = SimpleNamespace(live=mock.Mock())
        listener = mock.Mock()
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.recv.side_effect = [b"OKAY", b"device-response", b""]
        with mock.patch.object(H.socket, "create_connection", return_value=connection) as connect, mock.patch.object(H, "Managed") as provider, mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native birth")) as process:
            result = H.AdbSocket(server, clock=lambda: 0, listener=listener).command("host:devices", timeout=30)
            self.assertEqual(result, b"device-response")
            connect.assert_called_once_with(("127.0.0.1", 5039), timeout=30)
            listener.assert_called_once_with(server, 5039)
            self.assertEqual(server.live.call_count, 2)
            connection.sendall.assert_called_once_with(b"000chost:devices")
            self.assertEqual(connection.recv.call_count, 3)
            connection.__exit__.assert_called_once()
            provider.assert_not_called()
            process.assert_not_called()


class InventoryQueryDiagnosticTests(unittest.TestCase):
    TAGS = ("chrome-package-dump", "chrome-package-paths", "chrome-apk-sha256",
            "chrome-apk-stat", "device-unix-sockets")
    APK = "/product/app/PRIVATE/Chrome.apk"
    COMMANDS = ("dumpsys package com.android.chrome", "pm path com.android.chrome",
                "sha256sum " + APK, "stat -c %s " + APK)
    RESPONSES = (b"Packages:\n  Package [com.android.chrome] (abc):\n    versionCode=456 minSdk=26 targetSdk=36\n    versionName=123.0\n",
                 ("package:" + APK + "\n").encode(),
                 ("a" * 64 + "  " + APK + "\n").encode(), b"123\n")

    def test_wrapper_success_preserves_one_positional_call_and_return_identity(self):
        for tag in self.TAGS:
            result = object()
            adb = SimpleNamespace(shell=mock.Mock(return_value=result))
            with self.subTest(tag=tag):
                self.assertIs(H.inventory_shell(adb, "fixed-original-command", tag), result)
                adb.shell.assert_called_once_with("fixed-original-command")

    def test_wrapper_only_annotates_the_exact_original_overflow(self):
        class OtherRefusal(H.Refusal):
            pass

        cases = (H.Refusal("adb-output-bound"), H.Refusal("adb-service-refused"),
                 H.Refusal("adb-output-bound", "PRIVATE"), OtherRefusal("adb-output-bound"),
                 PermissionError("/PRIVATE"))
        for original in cases:
            adb = SimpleNamespace(shell=mock.Mock(side_effect=original))
            args = original.args
            with self.subTest(kind=type(original).__name__, argc=len(args)):
                with self.assertRaises(type(original)) as caught:
                    H.inventory_shell(adb, "fixed-original-command", "chrome-package-dump")
                self.assertIs(caught.exception, original)
                self.assertEqual(original.args, args)
                adb.shell.assert_called_once_with("fixed-original-command")
                if type(original) is H.Refusal and args == ("adb-output-bound",):
                    self.assertEqual(original.adb_query_tag, "chrome-package-dump")
                else:
                    self.assertNotIn("adb_query_tag", original.__dict__)

    def test_attachment_interruptions_preserve_original_object_and_args(self):
        class InterruptibleRefusal(ValueError):
            interrupt = None

            def __setattr__(self, name, value):
                raise self.interrupt

        for interrupt_type in (KeyboardInterrupt, SystemExit):
            InterruptibleRefusal.interrupt = interrupt_type("/PRIVATE")
            original = InterruptibleRefusal("adb-output-bound")
            adb = SimpleNamespace(shell=mock.Mock(side_effect=original))
            with self.subTest(interrupt=interrupt_type.__name__), mock.patch.object(H, "Refusal", InterruptibleRefusal):
                with self.assertRaises(InterruptibleRefusal) as caught:
                    H.inventory_shell(adb, "fixed-original-command", "chrome-package-dump")
                self.assertIs(caught.exception, original)
                self.assertEqual(original.args, ("adb-output-bound",))
                self.assertNotIn("adb_query_tag", original.__dict__)
                adb.shell.assert_called_once_with("fixed-original-command")

    def test_projection_is_closed_by_tag_type_phase_code_and_refusal_type(self):
        for tag in self.TAGS:
            original = H.Refusal("adb-output-bound")
            original.adb_query_tag = tag
            with self.subTest(tag=tag):
                record = Q.capture_refusal_diagnostic(original, "chrome-static-device-inventory")
                self.assertEqual(record["adb_query_tag"], tag)
                self.assertEqual(set(record), {"schema", "status", "phase", "refusal_code", "approval", "readiness_credit", "adb_query_tag"})
                self.assertFalse(record["approval"])
                self.assertEqual(record["readiness_credit"], 0)

        class StringAlias(str):
            pass

        for tag in (None, False, 1, {}, [], "PRIVATE", "x" * 33, StringAlias("chrome-package-dump")):
            original = H.Refusal("adb-output-bound")
            original.adb_query_tag = tag
            with self.subTest(kind=type(tag).__name__):
                record = Q.capture_refusal_diagnostic(original, "chrome-static-device-inventory")
                self.assertNotIn("adb_query_tag", record)
                self.assertNotIn("PRIVATE", json.dumps(record))
                self.assertEqual(original.args, ("adb-output-bound",))

        class RefusalAlias(H.Refusal):
            pass

        for original, phase in ((H.Refusal("adb-service-refused"), "chrome-static-device-inventory"),
                                (H.Refusal("adb-output-bound"), "owned-api36-emulator"),
                                (RefusalAlias("adb-output-bound"), "chrome-static-device-inventory"),
                                (H.Refusal("adb-output-bound", "PRIVATE"), "chrome-static-device-inventory")):
            original.adb_query_tag = "chrome-package-dump"
            with self.subTest(kind=type(original).__name__, phase=phase):
                self.assertNotIn("adb_query_tag", Q.capture_refusal_diagnostic(original, phase))

    def test_projection_bad_attribute_access_is_diagnostic_only(self):
        class BadAccessRefusal(ValueError):
            interrupt = None

            def __getattribute__(self, name):
                if name == "__dict__":
                    raise type(self).interrupt
                return super().__getattribute__(name)

        for interrupt_type in (KeyboardInterrupt, SystemExit):
            BadAccessRefusal.interrupt = interrupt_type("/PRIVATE")
            original = BadAccessRefusal("adb-output-bound")
            with self.subTest(interrupt=interrupt_type.__name__), mock.patch.object(H, "Refusal", BadAccessRefusal):
                record = Q.capture_refusal_diagnostic(original, "chrome-static-device-inventory")
                self.assertNotIn("adb_query_tag", record)
                self.assertEqual(record["refusal_code"], "adb-output-bound")
                self.assertEqual(original.args, ("adb-output-bound",))
                self.assertNotIn("PRIVATE", json.dumps(record))

    def test_package_queries_stop_at_each_original_failure_with_fixed_tag(self):
        for index in range(4):
            original = H.Refusal("adb-output-bound")
            adb = SimpleNamespace(shell=mock.Mock(side_effect=[*self.RESPONSES[:index], original]))
            with self.subTest(index=index):
                with self.assertRaises(H.Refusal) as caught:
                    H.package_inventory(adb, "com.android.chrome")
                self.assertIs(caught.exception, original)
                self.assertEqual(original.args, ("adb-output-bound",))
                self.assertEqual(original.adb_query_tag, self.TAGS[index])
                self.assertEqual(adb.shell.call_args_list, [mock.call(value) for value in self.COMMANDS[:index + 1]])
                record = Q.capture_refusal_diagnostic(original, "chrome-static-device-inventory")
                self.assertEqual(record["adb_query_tag"], self.TAGS[index])
                self.assertNotIn("PRIVATE", json.dumps(record))

    def test_package_success_keeps_inventory_and_unowned_package_precedes_provider(self):
        adb = SimpleNamespace(shell=mock.Mock(side_effect=self.RESPONSES))
        observed = H.package_inventory(adb, "com.android.chrome")
        self.assertEqual(observed, {"package": "com.android.chrome", "version": "123.0", "version_code": "456",
                                   "apks": [{"path": self.APK, "sha256": "a" * 64, "bytes": 123}],
                                   "publisher_signing_trust": "not-approved-by-this-test"})
        self.assertEqual(adb.shell.call_args_list, [mock.call(value) for value in self.COMMANDS])
        unused = SimpleNamespace(shell=mock.Mock())
        with self.assertRaisesRegex(H.Refusal, "unowned-package-probe") as caught:
            H.package_inventory(unused, "PRIVATE")
        unused.shell.assert_not_called()
        self.assertNotIn("adb_query_tag", caught.exception.__dict__)

    @staticmethod
    def shell_frame(payload):
        return b"\x01" + len(payload).to_bytes(4, "little") + payload + b"\x03\x01\x00\x00\x00\x00"

    def capture_unix_failure(self, *, publication=None, interrupt_type=None, real_wire=False):
        with fixture() as root:
            (root / ".tmp").mkdir()
            sdk = root / "owned-sdk"
            leaders = [SimpleNamespace(child=SimpleNamespace(stdin=mock.Mock()), zero=mock.Mock(),
                                       live=mock.Mock(), buffers=[bytearray(), bytearray()]) for _ in range(3)]
            born = []

            def managed(argv, env, cwd):
                self.assertLess(len(born), 3)
                self.assertIs(cwd, root)
                self.assertEqual(env["ADB_SERVER_SOCKET"], "tcp:127.0.0.1:5039")
                leader = leaders[len(born)]
                born.append(leader)
                return leader

            original = H.Refusal("adb-output-bound")
            adb = SimpleNamespace(command=mock.Mock(side_effect=[(H.SERIAL + "\tdevice\n").encode(), self.shell_frame(b"1\n")]),
                                  shell=mock.Mock(side_effect=[b"36\n", b"x86_64\n", original]))
            listener = mock.Mock()
            client_type = H.AdbSocket
            connections = []
            if real_wire:
                devices = (H.SERIAL + "\tdevice\n").encode()
                wire_responses = ([b"OKAY", f"{len(devices):04x}".encode(), devices, b""],
                                  [b"OKAY", b"OKAY", self.shell_frame(b"1\n"), b""],
                                  [b"OKAY", b"OKAY", self.shell_frame(b"36\n"), b""],
                                  [b"OKAY", b"OKAY", self.shell_frame(b"x86_64\n"), b""],
                                  [b"OKAY", b"OKAY", b"x" * 65536, b"x"])
                for values in wire_responses:
                    connection = mock.MagicMock()
                    connection.__enter__.return_value = connection
                    connection.recv.side_effect = values
                    connections.append(connection)
                adb = client_type(leaders[1], clock=lambda: 0, listener=listener)

            class BrokenStream(io.StringIO):
                def write(self, value):
                    raise interrupt_type("/PRIVATE")

            stream = BrokenStream() if publication == "diagnostic" else io.StringIO()
            with ExitStack() as patches:
                patches.enter_context(mock.patch.dict(os.environ, {"ANDROID_HOME": str(sdk)}, clear=True))
                patches.enter_context(mock.patch.object(Q, "event_guard", return_value={}))
                patches.enter_context(mock.patch.object(Q, "commands", return_value=(object(), 0)))
                patches.enter_context(mock.patch.object(Q, "source_binding", return_value={}))
                patches.enter_context(mock.patch.object(Q, "clone_guard", return_value=({}, {})))
                patches.enter_context(mock.patch.object(Q, "owned_sdk", return_value=sdk))
                patches.enter_context(mock.patch.object(Q, "sdk_inventory", return_value={"tree_sha256": "e" * 64}))
                patches.enter_context(mock.patch.object(Q.time, "monotonic", return_value=0))
                reservations = patches.enter_context(mock.patch.object(Q.socket, "socket", side_effect=[mock.MagicMock() for _ in range(3)]))
                provider = patches.enter_context(mock.patch.object(H, "Managed", side_effect=managed))
                ready = patches.enter_context(mock.patch.object(H, "owned_listener", return_value=None))
                patches.enter_context(mock.patch.object(H, "AdbSocket", return_value=adb))
                inventory = patches.enter_context(mock.patch.object(H, "package_inventory", return_value={"apks": [{}]}))
                cleanup = patches.enter_context(mock.patch.object(H, "cleanup_all", return_value=[]))
                receipt = patches.enter_context(mock.patch.object(Q, "public_receipt",
                    side_effect=interrupt_type("/PRIVATE") if publication == "receipt" else None))
                patches.enter_context(mock.patch.object(sys, "stderr", stream))
                process = patches.enter_context(mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native birth")))
                connect = patches.enter_context(mock.patch.object(H.socket, "create_connection", side_effect=connections))
                decoder = patches.enter_context(mock.patch.object(H, "shell_v2", wraps=H.shell_v2))
                with self.assertRaises(H.Refusal) as caught:
                    Q.capture(root)
                if not real_wire:
                    self.assertIs(caught.exception, original)
                    self.assertEqual(adb.shell.call_args_list, [mock.call("getprop ro.build.version.sdk"),
                        mock.call("getprop ro.product.cpu.abi"), mock.call("cat /proc/net/unix")])
                    self.assertEqual(adb.command.call_args_list, [mock.call("host:devices", framed=True, timeout=30),
                        mock.call("shell,v2,raw:getprop sys.boot_completed", transport=True, timeout=30)])
                    connect.assert_not_called()
                else:
                    self.assertEqual(connect.call_count, 5)
                    self.assertEqual(decoder.call_count, 3)
                self.assertEqual(caught.exception.args, ("adb-output-bound",))
                self.assertEqual(caught.exception.adb_query_tag, "device-unix-sockets")
                self.assertEqual(provider.call_count, 3)
                self.assertEqual(reservations.call_count, 3)
                ready.assert_called_once_with(leaders[1], 5039)
                inventory.assert_called_once_with(adb, "com.android.chrome")
                cleanup.assert_called_once_with(born)
                receipt.assert_called_once()
                process.assert_not_called()
                record = receipt.call_args.args[1]
                self.assertEqual(record["status"], "refused")
                self.assertFalse(record["approval"])
                self.assertEqual(record["readiness_credit"], 0)
            return caught.exception, stream.getvalue(), connections, leaders, listener

    def test_capture_fixed_unix_tag_has_original_failure_and_cleanup(self):
        original, line, connections, _leaders, _listener = self.capture_unix_failure()
        self.assertEqual(original.args, ("adb-output-bound",))
        self.assertEqual(connections, [])
        record = json.loads(line)
        self.assertEqual(record["phase"], "chrome-static-device-inventory")
        self.assertEqual(record["adb_query_tag"], "device-unix-sockets")
        self.assertFalse(record["approval"])
        self.assertEqual(record["readiness_credit"], 0)

    def test_capture_publication_interruptions_keep_original_failure_and_cleanup(self):
        for publication in ("diagnostic", "receipt"):
            for interrupt_type in (KeyboardInterrupt, SystemExit):
                with self.subTest(publication=publication, interrupt=interrupt_type.__name__):
                    original, _line, _connections, _leaders, _listener = self.capture_unix_failure(
                        publication=publication, interrupt_type=interrupt_type)
                    self.assertEqual(original.args, ("adb-output-bound",))
                    self.assertEqual(original.adb_query_tag, "device-unix-sockets")

    def test_real_mocked_wire_overflow_closes_sockets_and_cleans_retained_leaders(self):
        original, line, connections, leaders, listener = self.capture_unix_failure(real_wire=True)
        self.assertEqual(original.args, ("adb-output-bound",))
        self.assertEqual(len(connections), 5)
        for connection in connections:
            connection.__exit__.assert_called_once()
        self.assertEqual(connections[-1].recv.call_args_list,
                         [mock.call(4), mock.call(4), mock.call(65536), mock.call(1)])
        self.assertEqual(connections[-1].sendall.call_count, 2)
        self.assertEqual(connections[-1].sendall.call_args_list[1].args[0][4:], b"shell,v2,raw:cat /proc/net/unix")
        self.assertEqual(leaders[1].live.call_count, 9)
        self.assertEqual(listener.call_count, 5)
        self.assertEqual(json.loads(line)["adb_query_tag"], "device-unix-sockets")

    def test_closed_tag_records_fit_existing_ascii_publication_cap(self):
        self.assertEqual(H.ADB_INVENTORY_QUERY_TAGS, self.TAGS)
        self.assertEqual(Q.INVENTORY_QUERY_TAGS, self.TAGS)
        for tag in self.TAGS:
            original = H.Refusal("adb-output-bound")
            original.adb_query_tag = tag
            with self.subTest(tag=tag):
                record = Q.capture_refusal_diagnostic(original, "chrome-static-device-inventory")
                raw = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
                self.assertLessEqual(len(raw), 512)
                self.assertNotIn(b"PRIVATE", raw)
                self.assertNotIn("owned_process", record)
                self.assertNotIn("sdk_tree_limit", record)


class VanishedDescriptorTests(unittest.TestCase):
    TABLE = b"header\n0: 0100007F:13AF 00000000:0000 0A x x x x x 123\n"

    @staticmethod
    def entries(count):
        return [SimpleNamespace(path=f"/PRIVATE/fd/{index}") for index in range(count)]

    @staticmethod
    def vanished():
        return FileNotFoundError(H.errno.ENOENT, "/PRIVATE/vanished")

    def invoke(self, entries, outcomes, *, table_raw=TABLE, live=None, expected=None,
               directory_error=None, directory_close=None, table_error=None, table_close=None):
        leader, directory, table, stream = OwnedListenerOperationDiagnosticTests.providers()
        directory.__enter__.return_value = entries
        directory.__exit__.side_effect = directory_close
        table.__exit__.side_effect = table_close
        stream.read.return_value = table_raw
        leader.live.side_effect = live
        with mock.patch.object(H.os, "scandir", return_value=directory,
                               side_effect=directory_error) as scanned, \
             mock.patch.object(H.os, "readlink", side_effect=outcomes) as linked, \
             mock.patch.object(Path, "open", return_value=table, side_effect=table_error) as opened, \
             mock.patch.object(H.subprocess, "Popen", side_effect=AssertionError("native")) as native:
            if expected is None:
                result = H.owned_listener(leader, H.ADB_PORT)
                self.assertIs(result, True)
            else:
                with self.assertRaises(expected) as caught:
                    H.owned_listener(leader, H.ADB_PORT)
                result = caught.exception
            native.assert_not_called()
        return result, leader, directory, table, stream, scanned, linked, opened

    def test_unrelated_vanished_entry_requires_the_same_remaining_positive_proof(self):
        result, leader, directory, table, stream, scanned, linked, opened = self.invoke(
            self.entries(3), [self.vanished(), "pipe:[456]", "socket:[123]"])
        self.assertIs(result, True)
        self.assertEqual(leader.live.call_count, 2)
        scanned.assert_called_once_with(Path("/proc") / "123" / "fd")
        self.assertEqual(linked.call_args_list, [mock.call(f"/PRIVATE/fd/{index}") for index in range(3)])
        opened.assert_called_once_with("rb")
        stream.read.assert_called_once_with(1024 * 1024 + 1)
        directory.__exit__.assert_called_once()
        table.__exit__.assert_called_once()

    def test_no_disappearance_normal_calls_remain_exact(self):
        _result, leader, directory, table, stream, scanned, linked, opened = self.invoke(
            self.entries(1), ["socket:[123]"])
        self.assertEqual(leader.live.call_count, 2)
        scanned.assert_called_once_with(Path("/proc") / "123" / "fd")
        linked.assert_called_once_with("/PRIVATE/fd/0")
        opened.assert_called_once_with("rb")
        stream.read.assert_called_once_with(1024 * 1024 + 1)
        directory.__exit__.assert_called_once()
        table.__exit__.assert_called_once()

    def test_vanished_sole_all_missing_foreign_and_duplicate_listeners_refuse(self):
        cases = (
            ([self.vanished()], self.TABLE, "owned-loopback-listener-unproved"),
            ([self.vanished()], b"header\n", "owned-loopback-listener-missing"),
            ([self.vanished(), self.vanished()], self.TABLE, "owned-loopback-listener-unproved"),
            ([self.vanished(), "socket:[321]"], self.TABLE, "owned-loopback-listener-unproved"),
            ([self.vanished(), "socket:[123]"], self.TABLE + self.TABLE.splitlines(keepends=True)[1],
             "owned-loopback-listener-unproved"),
        )
        for outcomes, table_raw, code in cases:
            with self.subTest(code=code, count=len(outcomes)):
                result, leader, directory, table, stream, _scanned, linked, opened = self.invoke(
                    self.entries(len(outcomes)), outcomes, table_raw=table_raw, expected=H.Refusal)
                self.assertEqual(result.args, (code,))
                self.assertEqual(result.owned_listener_stage, "listener-match")
                self.assertEqual(leader.live.call_count, 2)
                self.assertEqual(linked.call_count, len(outcomes))
                opened.assert_called_once_with("rb")
                stream.read.assert_called_once_with(1024 * 1024 + 1)
                directory.__exit__.assert_called_once()
                table.__exit__.assert_called_once()

    def test_final_dead_or_pipe_failed_leader_remains_original_refusal(self):
        for code in ("owned-leader-or-pipe-unavailable", "original-leader-refusal"):
            original = H.Refusal(code)
            with self.subTest(code=code):
                result, leader, directory, table, _stream, _scanned, linked, _opened = self.invoke(
                    self.entries(2), [self.vanished(), "socket:[123]"], live=[None, original], expected=H.Refusal)
                self.assertIs(result, original)
                self.assertEqual(result.owned_listener_stage, "leader-after")
                self.assertEqual(leader.live.call_count, 2)
                self.assertEqual(linked.call_count, 2)
                directory.__exit__.assert_called_once()
                table.__exit__.assert_called_once()

    def test_nonexact_errno_types_and_errors_preserve_original_identity(self):
        class MissingAlias(FileNotFoundError):
            pass

        errors = [FileNotFoundError("/PRIVATE/errno-none"),
                  FileNotFoundError(H.errno.EIO, "/PRIVATE/wrong-errno"),
                  MissingAlias(H.errno.ENOENT, "/PRIVATE/subclass"),
                  PermissionError(H.errno.EACCES, "/PRIVATE/access"),
                  OSError(getattr(H.errno, "ESTALE", 116), "/PRIVATE/stale"),
                  OSError(H.errno.EIO, "/PRIVATE/io"), KeyboardInterrupt("/PRIVATE"), SystemExit("/PRIVATE")]
        for value in (None, True, False, 2.0):
            original = FileNotFoundError(H.errno.ENOENT, "/PRIVATE/type")
            original.errno = value
            errors.append(original)
        other = OSError("/PRIVATE/exact-oserror")
        other.errno = H.errno.ENOENT
        errors.append(other)
        for original in errors:
            with self.subTest(kind=type(original).__name__, errno_type=type(getattr(original, "errno", None)).__name__):
                result, leader, directory, _table, _stream, _scanned, linked, opened = self.invoke(
                    self.entries(1), [original], expected=type(original))
                self.assertIs(result, original)
                self.assertEqual(result.owned_listener_stage, "fd-readlink")
                self.assertEqual(leader.live.call_count, 1)
                linked.assert_called_once_with("/PRIVATE/fd/0")
                opened.assert_not_called()
                directory.__exit__.assert_called_once()

    def test_ENOENT_outside_readlink_is_not_handled_or_retried(self):
        for stage in ("fd-directory-open", "fd-directory-close", "socket-table-open", "socket-table-close"):
            original = self.vanished()
            options = {"directory_error": original} if stage == "fd-directory-open" else (
                {"directory_close": original} if stage == "fd-directory-close" else (
                {"table_error": original} if stage == "socket-table-open" else {"table_close": original}))
            with self.subTest(stage=stage):
                result, leader, directory, table, stream, scanned, linked, opened = self.invoke(
                    self.entries(1), [self.vanished()], expected=FileNotFoundError, **options)
                self.assertIs(result, original)
                self.assertEqual(result.owned_listener_stage, stage)
                self.assertEqual(leader.live.call_count, 1)
                scanned.assert_called_once()
                self.assertEqual(linked.call_count, 0 if stage == "fd-directory-open" else 1)
                self.assertEqual(opened.call_count, 1 if stage.startswith("socket-") else 0)
                self.assertEqual(stream.read.call_count, 1 if stage == "socket-table-close" else 0)
                self.assertEqual(directory.__exit__.call_count, 0 if stage == "fd-directory-open" else 1)
                self.assertEqual(table.__exit__.call_count, 1 if stage == "socket-table-close" else 0)

    def test_iterator_after_skip_retains_enumeration_stage_and_original_error(self):
        original = self.vanished()

        class Entries:
            def __iter__(self):
                yield SimpleNamespace(path="/PRIVATE/fd/0")
                raise original

        result, leader, directory, _table, _stream, _scanned, linked, opened = self.invoke(
            Entries(), [self.vanished()], expected=FileNotFoundError)
        self.assertIs(result, original)
        self.assertEqual(result.owned_listener_stage, "fd-enumeration")
        self.assertEqual(leader.live.call_count, 1)
        linked.assert_called_once_with("/PRIVATE/fd/0")
        opened.assert_not_called()
        directory.__exit__.assert_called_once()

    def test_skipped_entries_still_consume_4096_and_stop_before_next_readlink(self):
        result, leader, directory, _table, _stream, _scanned, linked, opened = self.invoke(
            self.entries(4097), [self.vanished() for _ in range(4096)], expected=H.Refusal)
        self.assertEqual(result.args, ("owned-descriptor-bound",))
        self.assertEqual(result.owned_listener_stage, "fd-enumeration")
        self.assertEqual(leader.live.call_count, 1)
        self.assertEqual(linked.call_count, 4096)
        self.assertEqual(linked.call_args_list[-1], mock.call("/PRIVATE/fd/4095"))
        opened.assert_not_called()
        directory.__exit__.assert_called_once()

    def test_table_bound_and_layout_refusals_still_follow_a_skip(self):
        for table_raw, code, stage in ((b"x" * (1024 * 1024 + 1), "owned-socket-table-bound", "socket-table-bound"),
                                       (b"header\nmalformed\n", "owned-socket-table-layout", "socket-table-parse")):
            with self.subTest(code=code):
                result, leader, directory, table, stream, _scanned, linked, _opened = self.invoke(
                    self.entries(1), [self.vanished()], table_raw=table_raw, expected=H.Refusal)
                self.assertEqual(result.args, (code,))
                self.assertEqual(result.owned_listener_stage, stage)
                self.assertEqual(leader.live.call_count, 1)
                linked.assert_called_once_with("/PRIVATE/fd/0")
                stream.read.assert_called_once_with(1024 * 1024 + 1)
                directory.__exit__.assert_called_once()
                table.__exit__.assert_called_once()


class ChromeDumpWireBudgetTests(unittest.TestCase):
    FIXED = "dumpsys package com.android.chrome"
    SERVICE = "shell,v2,raw:dumpsys package com.android.chrome"
    APK = "/product/app/Chrome/Chrome.apk"

    @staticmethod
    def frame(kind, payload):
        return bytes((kind,)) + len(payload).to_bytes(4, "little") + payload

    @classmethod
    def wire(cls, stdout):
        chunks = [cls.frame(1, stdout[index:index + 65536]) for index in range(0, len(stdout), 65536)]
        return b"".join(chunks) + cls.frame(3, b"\0")

    @classmethod
    def dump(cls, version=b"123.0", suffix=b""):
        return (b"Packages:\n  Package [com.android.chrome] (abc):\n    padding=" + b"x" * 65536
                + b"\n    versionCode=456 minSdk=26 targetSdk=36\n    versionName=" + version + b"\n" + suffix)

    @contextmanager
    def transport(self, wire, *, transport=True, clock=None, live_error=None, listener_error=None,
                  provider_error=None, receive_error=None, close_error=None):
        data = bytearray((b"OKAYOKAY" if transport else b"OKAY") + wire)
        connection = mock.MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        if close_error is not None:
            connection.__exit__.side_effect = close_error
        state = {"eof": False}

        def receive(size):
            self.assertIs(type(size), int)
            self.assertGreater(size, 0)
            self.assertLessEqual(size, 65536)
            if receive_error is not None:
                raise receive_error
            result = bytes(data[:size])
            del data[:size]
            state["eof"] = not result
            return result

        connection.recv.side_effect = receive
        server = SimpleNamespace(live=mock.Mock(side_effect=live_error))
        listener = mock.Mock(side_effect=listener_error)
        with ExitStack() as patches:
            provider = patches.enter_context(mock.patch.object(H.socket, "create_connection",
                side_effect=provider_error, return_value=connection))
            process = patches.enter_context(mock.patch.object(H.subprocess, "Popen"))
            thread = patches.enter_context(mock.patch.object(H.threading, "Thread"))
            client = H.AdbSocket(server, clock=(lambda: 0) if clock is None else clock, listener=listener)
            yield client, connection, provider, server, listener, state
            process.assert_not_called()
            thread.assert_not_called()

    def test_complete_multiframe_dump_has_only_exact_query_allowance(self):
        payload = self.dump()
        wire = self.wire(payload)
        self.assertGreater(len(wire), 65536)
        with self.transport(wire) as (client, connection, provider, server, listener, _state):
            self.assertEqual(client.shell(self.FIXED), payload)
            provider.assert_called_once_with(("127.0.0.1", 5039), timeout=30)
            self.assertEqual(server.live.call_count, 2)
            listener.assert_called_once_with(server, 5039)
            self.assertEqual([call.args[0][4:] for call in connection.sendall.call_args_list],
                             [("host:transport:" + H.SERIAL).encode(), self.SERVICE.encode()])
            connection.__exit__.assert_called_once()
        self.assertEqual(H.shell_v2(wire, service=self.SERVICE), payload)
        with self.assertRaisesRegex(H.Refusal, "adb-shell-v2-total-bound"):
            H.shell_v2(wire)
        for fixed in ("getprop ro.build.version.sdk", "cat /proc/net/unix", self.FIXED + " "):
            with self.subTest(fixed=fixed), self.transport(wire) as (client, connection, _provider, _server, _listener, _state):
                with self.assertRaisesRegex(H.Refusal, "adb-output-bound"):
                    client.shell(fixed)
                connection.__exit__.assert_called_once()

    def test_exact_total_wire_boundary_and_one_byte_sentinel(self):
        payload = b"x" * (1048576 - 86)  # 16 stdout headers and one six-byte zero exit.
        wire = self.wire(payload)
        self.assertEqual(len(wire), 1048576)
        with self.transport(wire) as (client, connection, _provider, _server, _listener, _state):
            self.assertEqual(client.shell(self.FIXED), payload)
            connection.__exit__.assert_called_once()
        with self.transport(wire + b"x") as (client, connection, _provider, _server, _listener, _state):
            with self.assertRaisesRegex(H.Refusal, "adb-output-bound"):
                client.shell(self.FIXED)
            self.assertEqual(connection.recv.call_args_list[-1], mock.call(1))
            connection.__exit__.assert_called_once()
        with self.transport(b"x" * 65537) as (client, connection, _provider, _server, _listener, _state):
            with self.assertRaisesRegex(H.Refusal, "adb-output-bound"):
                client.shell("getprop ro.product.cpu.abi")
            self.assertEqual(connection.recv.call_args_list[-1], mock.call(1))
            connection.__exit__.assert_called_once()
        with self.transport(b"x" * 65, transport=False) as (client, connection, _provider, _server, _listener, _state):
            with self.assertRaisesRegex(H.Refusal, "adb-output-bound"):
                client.command("ordinary-forward", limit=64)
            connection.__exit__.assert_called_once()

    def test_command_limit_types_refuse_before_active_owner_and_provider(self):
        class IntegerAlias(int):
            pass

        for limit in (False, True, 0, -1, 1.0, None, "PRIVATE", IntegerAlias(1048576),
                      65537, 1048575, 1048577):
            with self.subTest(limit_type=type(limit).__name__), self.transport(b"") as (client, _connection, provider, server, listener, _state):
                with self.assertRaisesRegex(H.Refusal, "adb-query-wire-budget"):
                    client.command(self.SERVICE, transport=True, limit=limit)
                server.live.assert_not_called()
                listener.assert_not_called()
                provider.assert_not_called()

    def test_special_command_context_is_independent_of_parser_and_query_tag(self):
        class StringAlias(str):
            pass

        rows = (("PRIVATE", True, False), (StringAlias(self.SERVICE), True, False),
                (self.SERVICE + " ", True, False), (self.SERVICE, False, False),
                (self.SERVICE, 1, False), (self.SERVICE, None, False),
                (self.SERVICE, True, True), (self.SERVICE, True, 0), (self.SERVICE, True, None))
        for service, transport, framed in rows:
            with self.subTest(service_type=type(service).__name__, transport=transport, framed=framed), self.transport(b"") as (client, _connection, provider, server, listener, _state):
                with self.assertRaisesRegex(H.Refusal, "adb-query-wire-budget"):
                    client.command(service, transport=transport, framed=framed, limit=1048576)
                server.live.assert_not_called()
                listener.assert_not_called()
                provider.assert_not_called()
        with self.transport(b"x" * 65537) as (client, connection, _provider, _server, _listener, _state):
            with self.assertRaises(H.Refusal) as caught:
                H.inventory_shell(client, "cat /proc/net/unix", "chrome-package-dump")
            self.assertEqual(caught.exception.args, ("adb-output-bound",))
            self.assertEqual(caught.exception.adb_query_tag, "chrome-package-dump")
            connection.__exit__.assert_called_once()
        with self.transport(self.wire(self.dump())) as (client, connection, _provider, _server, _listener, _state):
            with self.assertRaisesRegex(H.Refusal, "adb-output-bound"):
                client.shell(StringAlias(self.FIXED))
            connection.__exit__.assert_called_once()

    def test_parser_context_is_closed_and_default_remains_small(self):
        class StringAlias(str):
            pass

        for service in (False, True, 1, {}, [], "PRIVATE", self.SERVICE + "\n", StringAlias(self.SERVICE)):
            with self.subTest(service_type=type(service).__name__):
                with self.assertRaisesRegex(H.Refusal, "adb-shell-v2-query-context"):
                    H.shell_v2(self.wire(b"ok"), service=service)
        with self.assertRaisesRegex(H.Refusal, "adb-shell-v2-total-bound"):
            H.shell_v2(self.wire(self.dump()), service=None)
        with self.assertRaisesRegex(TypeError, "limit"):
            H.shell_v2(self.wire(b"ok"), limit=1048576)

    def test_special_total_preserves_all_frame_packet_and_exit_refusals(self):
        cases = (
            (self.frame(1, b"x" * 65537) + self.frame(3, b"\0"), "adb-shell-v2-payload-bound"),
            (self.frame(1, b"") * 1025 + self.frame(3, b"\0"), "adb-shell-v2-packet-layout"),
            (b"\x01\x00", "adb-shell-v2-packet-layout"),
            (b"\x01\x0c\x00\x00\x00x", "adb-shell-v2-payload-bound"),
            (self.frame(2, b"PRIVATE") + self.frame(3, b"\0"), "adb-shell-v2-nonzero-stderr-or-type"),
            (self.frame(4, b"") + self.frame(3, b"\0"), "adb-shell-v2-nonzero-stderr-or-type"),
            (self.frame(1, b"x"), "adb-shell-v2-zero-exit-unproved"),
            (self.frame(3, b"\x01"), "adb-shell-v2-nonzero-stderr-or-type"),
            (self.frame(3, b"\0") * 2, "adb-shell-v2-packet-layout"),
            (self.frame(3, b"\0") + b"tail", "adb-shell-v2-packet-layout"),
        )
        for raw, code in cases:
            with self.subTest(code=code), self.assertRaises(H.Refusal) as caught:
                H.shell_v2(raw, service=self.SERVICE)
            self.assertEqual(caught.exception.args, (code,))
        valid = self.frame(2, b"") + self.wire(b"ok")
        self.assertEqual(H.shell_v2(valid, service=self.SERVICE), b"ok")

        class BytesAlias(bytes):
            pass

        self.assertEqual(H.shell_v2(BytesAlias(valid), service=self.SERVICE), b"ok")
        for raw in (None, False, bytearray(valid)):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaisesRegex(H.Refusal, "adb-shell-v2-total-bound"):
                H.shell_v2(raw, service=self.SERVICE)

    def test_full_large_package_inventory_keeps_exact_four_positional_queries(self):
        client = H.AdbSocket(SimpleNamespace(live=mock.Mock()), listener=mock.Mock())
        responses = (self.wire(self.dump()), self.wire(("package:" + self.APK + "\n").encode()),
                     self.wire(("a" * 64 + " " + self.APK + "\n").encode()), self.wire(b"123\n"))
        with mock.patch.object(client, "command", side_effect=responses) as command, mock.patch.object(H.socket, "create_connection") as provider:
            observed = H.package_inventory(client, "com.android.chrome")
            self.assertEqual(observed, {"package": "com.android.chrome", "version": "123.0", "version_code": "456",
                "apks": [{"path": self.APK, "sha256": "a" * 64, "bytes": 123}],
                "publisher_signing_trust": "not-approved-by-this-test"})
            self.assertEqual(command.call_args_list, [
                mock.call(self.SERVICE, transport=True, limit=1048576),
                mock.call("shell,v2,raw:pm path com.android.chrome", transport=True),
                mock.call("shell,v2,raw:sha256sum " + self.APK, transport=True),
                mock.call("shell,v2,raw:stat -c %s " + self.APK, transport=True)])
            provider.assert_not_called()

    def test_duplicate_versions_beyond_old_boundary_stop_before_later_query(self):
        for suffix in (b"versionName=123.0\n", b"versionCode=456\n"):
            client = H.AdbSocket(SimpleNamespace(live=mock.Mock()), listener=mock.Mock())
            with self.subTest(suffix=suffix), mock.patch.object(client, "command", return_value=self.wire(self.dump(suffix=suffix))) as command:
                with self.assertRaisesRegex(H.Refusal, "actual-package-version-unobserved"):
                    H.package_inventory(client, "com.android.chrome")
                command.assert_called_once_with(self.SERVICE, transport=True, limit=1048576)

    def test_large_dump_does_not_relax_path_digest_or_size_inventory(self):
        good = [self.wire(self.dump()), self.wire(("package:" + self.APK + "\n").encode()),
                self.wire(("a" * 64 + " " + self.APK + "\n").encode()), self.wire(b"123\n")]
        rows = ((1, self.wire(("package:" + self.APK + "\n").encode() * 2), "actual-apk-path-inventory-unobserved"),
                (1, self.wire(b"package:/product/../PRIVATE.apk\n"), "apk-path-bound"),
                (2, self.wire(b"a" * 64 + b" /wrong.apk\n"), "actual-apk-digest-layout"),
                (2, self.wire(("invalid-digest " + self.APK + "\n").encode()), "unobserved-exact-digest"),
                (3, self.wire(b"0\n"), "actual-apk-size-layout"))
        for index, raw, code in rows:
            responses = [*good[:index], raw] + ([good[3]] if code == "unobserved-exact-digest" else [])
            client = H.AdbSocket(SimpleNamespace(live=mock.Mock()), listener=mock.Mock())
            with self.subTest(code=code), mock.patch.object(client, "command", side_effect=responses) as command:
                with self.assertRaisesRegex(H.Refusal, code):
                    H.package_inventory(client, "com.android.chrome")
                if code == "unobserved-exact-digest":
                    self.assertEqual(command.call_count, index + 2)
                    self.assertEqual(command.call_args_list, [
                        mock.call(self.SERVICE, transport=True, limit=1048576),
                        mock.call("shell,v2,raw:pm path com.android.chrome", transport=True),
                        mock.call("shell,v2,raw:sha256sum " + self.APK, transport=True),
                        mock.call("shell,v2,raw:stat -c %s " + self.APK, transport=True)])
                else:
                    self.assertEqual(command.call_count, index + 1)
        unused = SimpleNamespace(shell=mock.Mock())
        with self.assertRaisesRegex(H.Refusal, "unowned-package-probe"):
            H.package_inventory(unused, "PRIVATE")
        unused.shell.assert_not_called()

    def test_original_owner_listener_deadline_and_late_completion_still_refuse(self):
        for kind in ("live", "listener"):
            original = H.Refusal("original-owned-guard")
            kwargs = {"live_error" if kind == "live" else "listener_error": original}
            with self.subTest(kind=kind), self.transport(self.wire(b"ok"), **kwargs) as (client, _connection, provider, _server, _listener, _state):
                with self.assertRaises(H.Refusal) as caught:
                    client.shell(self.FIXED)
                self.assertIs(caught.exception, original)
                provider.assert_not_called()
        clock = mock.Mock(side_effect=(0, 30))
        with self.transport(self.wire(b"ok"), clock=clock) as (client, connection, _provider, _server, _listener, _state):
            with self.assertRaisesRegex(H.Refusal, "adb-original-command-deadline"):
                client.shell(self.FIXED)
            connection.recv.assert_not_called()
            connection.__exit__.assert_called_once()
        with self.transport(self.wire(b"ok")) as (client, connection, _provider, server, _listener, state):
            client.clock = lambda: 31 if state["eof"] else 0
            with self.assertRaisesRegex(H.Refusal, "adb-late-completed-command"):
                client.shell(self.FIXED)
            self.assertEqual(server.live.call_count, 2)
            connection.__exit__.assert_called_once()

    def test_socket_errors_and_finally_selected_close_keep_identity(self):
        for kind in ("provider", "read"):
            original = OSError("/PRIVATE")
            kwargs = {"provider_error" if kind == "provider" else "receive_error": original}
            with self.subTest(kind=kind), self.transport(self.wire(b"ok"), **kwargs) as (client, connection, _provider, _server, _listener, _state):
                with self.assertRaises(OSError) as caught:
                    client.shell(self.FIXED)
                self.assertIs(caught.exception, original)
                if kind == "read":
                    connection.__exit__.assert_called_once()
                else:
                    connection.__exit__.assert_not_called()
        close = RuntimeError("/PRIVATE/close")
        with self.transport(b"x" * 1048577, close_error=close) as (client, connection, _provider, _server, _listener, _state):
            with self.assertRaises(RuntimeError) as caught:
                client.shell(self.FIXED)
            self.assertIs(caught.exception, close)
            self.assertIs(type(close.__context__), H.Refusal)
            self.assertEqual(close.__context__.args, ("adb-output-bound",))
            connection.__exit__.assert_called_once()

    def test_capture_larger_before_after_inventory_mismatch_keeps_cleanup_and_zero_credit(self):
        with fixture() as root:
            (root / ".tmp").mkdir()
            sdk = root / "owned-sdk"
            leaders = [SimpleNamespace(child=SimpleNamespace(stdin=mock.Mock()), zero=mock.Mock(),
                live=mock.Mock(), buffers=[bytearray(), bytearray()]) for _ in range(3)]
            born, queried, dumps = [], [], []

            def managed(argv, env, cwd):
                self.assertLess(len(born), 3)
                self.assertIs(cwd, root)
                self.assertEqual(env["ADB_SERVER_SOCKET"], "tcp:127.0.0.1:5039")
                leader = leaders[len(born)]
                born.append(leader)
                return leader

            def command(service, **kwargs):
                queried.append((service, kwargs))
                if service == "host:devices":
                    return (H.SERIAL + "\tdevice\n").encode()
                if service == "shell,v2,raw:getprop sys.boot_completed":
                    return self.wire(b"1\n")
                if service == "shell,v2,raw:getprop ro.build.version.sdk":
                    return self.wire(b"36\n")
                if service == "shell,v2,raw:getprop ro.product.cpu.abi":
                    return self.wire(b"x86_64\n")
                if service == self.SERVICE:
                    self.assertEqual(kwargs, {"transport": True, "limit": 1048576})
                    dumps.append(service)
                    return self.wire(self.dump(version=b"123.0" if len(dumps) == 1 else b"124.0"))
                if service == "shell,v2,raw:pm path com.android.chrome":
                    return self.wire(("package:" + self.APK + "\n").encode())
                if service == "shell,v2,raw:sha256sum " + self.APK:
                    return self.wire(("a" * 64 + " " + self.APK + "\n").encode())
                if service == "shell,v2,raw:stat -c %s " + self.APK:
                    return self.wire(b"123\n")
                self.assertEqual(service, "shell,v2,raw:cat /proc/net/unix")
                return self.wire(b"header\n")

            client = H.AdbSocket(leaders[1], clock=lambda: 0, listener=mock.Mock())
            with ExitStack() as patches:
                patches.enter_context(mock.patch.object(client, "command", side_effect=command))
                patches.enter_context(mock.patch.dict(os.environ, {"ANDROID_HOME": str(sdk)}, clear=True))
                patches.enter_context(mock.patch.object(Q, "event_guard", return_value={}))
                patches.enter_context(mock.patch.object(Q, "commands", return_value=(object(), 0)))
                patches.enter_context(mock.patch.object(Q, "source_binding", return_value={}))
                patches.enter_context(mock.patch.object(Q, "clone_guard", return_value=({}, {})))
                patches.enter_context(mock.patch.object(Q, "owned_sdk", return_value=sdk))
                patches.enter_context(mock.patch.object(Q, "sdk_inventory", return_value={"tree_sha256": "e" * 64}))
                patches.enter_context(mock.patch.object(Q.time, "monotonic", return_value=0))
                reservations = patches.enter_context(mock.patch.object(Q.socket, "socket", side_effect=[mock.MagicMock() for _ in range(3)]))
                provider = patches.enter_context(mock.patch.object(H, "Managed", side_effect=managed))
                patches.enter_context(mock.patch.object(H, "owned_listener", return_value=None))
                patches.enter_context(mock.patch.object(H, "AdbSocket", return_value=client))
                cleanup = patches.enter_context(mock.patch.object(H, "cleanup_all", return_value=[]))
                receipt = patches.enter_context(mock.patch.object(Q, "public_receipt"))
                process = patches.enter_context(mock.patch.object(H.subprocess, "Popen"))
                connect = patches.enter_context(mock.patch.object(H.socket, "create_connection"))
                stream = io.StringIO()
                patches.enter_context(mock.patch.object(sys, "stderr", stream))
                with self.assertRaisesRegex(H.Refusal, "qualification-current-source-tool-or-device-changed"):
                    Q.capture(root)
                self.assertEqual(len(queried), 13)
                self.assertEqual(len(dumps), 2)
                self.assertEqual(provider.call_count, 3)
                self.assertEqual(reservations.call_count, 3)
                cleanup.assert_called_once_with(born)
                receipt.assert_called_once()
                self.assertEqual(receipt.call_args.args[1]["status"], "refused")
                self.assertFalse(receipt.call_args.args[1]["approval"])
                self.assertEqual(receipt.call_args.args[1]["readiness_credit"], 0)
                self.assertNotIn("padding", json.dumps(receipt.call_args.args[1]))
                self.assertNotIn("adb_query_tag", json.loads(stream.getvalue()))
                process.assert_not_called()
                connect.assert_not_called()


class ChromeVersionShapeDiagnosticTests(unittest.TestCase):
    PHASE = "chrome-static-device-inventory"
    CODE = "actual-package-version-unobserved"
    KEYS = ("name_matches", "code_matches", "name_labels", "code_labels")

    def refused_inventory(self, dump):
        adb = SimpleNamespace(shell=mock.Mock(return_value=dump))
        with mock.patch.object(H.socket, "create_connection") as socket_provider, \
             mock.patch.object(H.subprocess, "Popen") as process_provider:
            with self.assertRaises(H.Refusal) as caught:
                H.package_inventory(adb, "com.android.chrome")
            adb.shell.assert_called_once_with("dumpsys package com.android.chrome")
            socket_provider.assert_not_called()
            process_provider.assert_not_called()
        self.assertEqual(caught.exception.args, (self.CODE,))
        return caught.exception

    def test_absent_multiple_and_malformed_lexical_shapes_keep_original_refusal(self):
        rows = ((b"PRIVATE\n", (0, 0, 0, 0)),
                (b"versionName=123.0\n", (1, 0, 1, 0)),
                (b"versionCode=456\n", (0, 1, 0, 1)),
                (b"versionName=123.0 versionCode=456\n" * 3, (2, 2, 2, 2)),
                (b"versionName=PRIVATE versionCode=1234567890123\n", (0, 0, 1, 1)),
                (b"versionName=123.0\nversionName=124.0\nversionCode=456\n", (2, 1, 2, 1)))
        for dump, expected in rows:
            with self.subTest(expected=expected):
                original = self.refused_inventory(dump)
                record = Q.capture_refusal_diagnostic(original, self.PHASE)
                self.assertEqual(record["chrome_version_shape"], dict(zip(self.KEYS, expected, strict=True)))
                self.assertEqual(record["refusal_code"], self.CODE)
                self.assertNotIn("PRIVATE", json.dumps(record))
                self.assertIsNone(original.__context__)

    def test_exact_success_keeps_full_four_queries_and_apk_proof(self):
        adb = SimpleNamespace(shell=mock.Mock(side_effect=[b"Packages:\n  Package [com.android.chrome] (abc):\n    versionCode=456 minSdk=26 targetSdk=36\n    versionName=123.0\n",
            b"package:/product/app/Chrome/Chrome.apk\n", b"a" * 64 + b" /product/app/Chrome/Chrome.apk\n", b"123\n"]))
        with mock.patch.object(H, "_note_chrome_version_shape") as observer:
            actual = H.package_inventory(adb, "com.android.chrome")
        self.assertEqual(actual["version"], "123.0")
        self.assertEqual(actual["version_code"], "456")
        self.assertEqual(actual["apks"], [{"path": "/product/app/Chrome/Chrome.apk", "sha256": "a" * 64, "bytes": 123}])
        self.assertEqual(adb.shell.call_args_list, [mock.call("dumpsys package com.android.chrome"),
            mock.call("pm path com.android.chrome"), mock.call("sha256sum /product/app/Chrome/Chrome.apk"),
            mock.call("stat -c %s /product/app/Chrome/Chrome.apk")])
        observer.assert_not_called()
        record = Q.capture_refusal_diagnostic(H.Refusal(self.CODE), self.PHASE)
        self.assertNotIn("chrome_version_shape", record)

    def test_independent_closed_exact_types_and_consistency(self):
        class IntegerAlias(int):
            pass

        good = {"name_matches": 0, "code_matches": 1, "name_labels": 1, "code_labels": 1}
        wrong = [None, False, "PRIVATE", [], {**good, "PRIVATE": 0},
            {key: value for key, value in good.items() if key != "name_labels"},
            {**good, "name_matches": True}, {**good, "name_matches": IntegerAlias(0)},
            {**good, "name_matches": -1}, {**good, "name_matches": 3},
            {**good, "name_matches": 2}, {**good, "name_matches": 1}]
        for value in wrong:
            original = H.Refusal(self.CODE)
            original.chrome_version_shape = value
            with self.subTest(value_type=type(value).__name__):
                self.assertIsNone(Q.chrome_version_shape_diagnostic(original))
                self.assertNotIn("chrome_version_shape", Q.capture_refusal_diagnostic(original, self.PHASE))
        original = H.Refusal(self.CODE)
        original.chrome_version_shape = good
        self.assertEqual(Q.chrome_version_shape_diagnostic(original), good)
        self.assertIsNot(Q.chrome_version_shape_diagnostic(original), good)
        for phase in ("sdk-observation", "owned-api36-emulator", "PRIVATE", self.PHASE + " "):
            self.assertNotIn("chrome_version_shape", Q.capture_refusal_diagnostic(original, phase))
        for original in (H.Refusal("adb-output-bound"), H.Refusal(self.CODE, "PRIVATE"), RuntimeError(self.CODE)):
            original.chrome_version_shape = good
            self.assertIsNone(Q.chrome_version_shape_diagnostic(original))

    def test_original_helper_fault_and_attachment_interruptions_keep_selected_error(self):
        for interruption in (RuntimeError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(interruption).__name__), \
                 mock.patch.object(H, "_note_chrome_version_shape", side_effect=interruption) as observer:
                original = self.refused_inventory(b"PRIVATE\n")
            self.assertIs(observer.call_args.args[0], original)
            self.assertEqual(original.args, (self.CODE,))
            self.assertIsNone(original.__context__)
            self.assertNotIn("chrome_version_shape", Q.capture_refusal_diagnostic(original, self.PHASE))

        class AttachmentInterrupted(H.Refusal):
            def __setattr__(self, name, value):
                if name == "chrome_version_shape":
                    raise KeyboardInterrupt("PRIVATE")
                super().__setattr__(name, value)

        with mock.patch.object(H, "Refusal", AttachmentInterrupted):
            original = self.refused_inventory(b"PRIVATE\n")
            self.assertIs(type(original), AttachmentInterrupted)
            self.assertNotIn("chrome_version_shape", Q.capture_refusal_diagnostic(original, self.PHASE))

    def test_poisoned_projection_access_is_omitted_and_ascii_decode_stays_original(self):
        class GetterInterrupted(H.Refusal):
            def __getattribute__(self, name):
                if name == "__dict__":
                    raise SystemExit(9)
                return super().__getattribute__(name)

        with mock.patch.object(H, "Refusal", GetterInterrupted):
            original = GetterInterrupted(self.CODE)
            self.assertIsNone(Q.chrome_version_shape_diagnostic(original))
            self.assertNotIn("chrome_version_shape", Q.capture_refusal_diagnostic(original, self.PHASE))
        adb = SimpleNamespace(shell=mock.Mock(return_value=b"\xff"))
        with mock.patch.object(H, "_note_chrome_version_shape") as observer:
            with self.assertRaises(UnicodeDecodeError):
                H.package_inventory(adb, "com.android.chrome")
        adb.shell.assert_called_once_with("dumpsys package com.android.chrome")
        observer.assert_not_called()
        original = H.Refusal(self.CODE)
        H._note_chrome_version_shape(original, "versionName=" * 3 + " versionCode=", [], [])
        self.assertEqual(original.chrome_version_shape, {"name_matches": 0, "code_matches": 0,
            "name_labels": 2, "code_labels": 1})
        for dump, names, codes in ((b"PRIVATE", [], []), ("x" * 1048577, [], []),
                                    ("versionName=", (), []), ("versionName=", [], ())):
            original = H.Refusal(self.CODE)
            H._note_chrome_version_shape(original, dump, names, codes)
            self.assertNotIn("chrome_version_shape", original.__dict__)

    def capture_bad_dump(self, publication_error=None):
        with fixture() as root:
            (root / ".tmp").mkdir()
            sdk = root / "owned-sdk"
            born, queried = [], []
            leaders = [SimpleNamespace(child=SimpleNamespace(stdin=mock.Mock()), zero=mock.Mock(),
                live=mock.Mock(), buffers=[bytearray(), bytearray()]) for _ in range(3)]

            def managed(argv, env, cwd):
                self.assertLess(len(born), 3)
                self.assertIs(cwd, root)
                self.assertEqual(env["ADB_SERVER_SOCKET"], "tcp:127.0.0.1:5039")
                leader = leaders[len(born)]
                born.append(leader)
                return leader

            def command(service, **kwargs):
                queried.append((service, kwargs))
                if service == "host:devices":
                    return (H.SERIAL + "\tdevice\n").encode()
                rows = {"shell,v2,raw:getprop sys.boot_completed": b"1\n",
                    "shell,v2,raw:getprop ro.build.version.sdk": b"36\n",
                    "shell,v2,raw:getprop ro.product.cpu.abi": b"x86_64\n",
                    "shell,v2,raw:dumpsys package com.android.chrome": b"PRIVATE\n"}
                self.assertIn(service, rows)
                if service.endswith("dumpsys package com.android.chrome"):
                    self.assertEqual(kwargs, {"transport": True, "limit": 1048576})
                return ChromeDumpWireBudgetTests.wire(rows[service])

            client = H.AdbSocket(leaders[1], clock=lambda: 0, listener=mock.Mock())
            stream = io.StringIO()
            if publication_error is not None:
                stream = mock.Mock()
                stream.write.side_effect = publication_error
            with ExitStack() as patches:
                patches.enter_context(mock.patch.object(client, "command", side_effect=command))
                patches.enter_context(mock.patch.dict(os.environ, {"ANDROID_HOME": str(sdk)}, clear=True))
                for name, value in (("event_guard", {}), ("commands", (object(), 0)), ("source_binding", {}),
                    ("clone_guard", ({}, {})), ("owned_sdk", sdk), ("sdk_inventory", {"tree_sha256": "e" * 64})):
                    patches.enter_context(mock.patch.object(Q, name, return_value=value))
                patches.enter_context(mock.patch.object(Q.time, "monotonic", return_value=0))
                reservations = patches.enter_context(mock.patch.object(Q.socket, "socket", side_effect=[mock.MagicMock() for _ in range(3)]))
                provider = patches.enter_context(mock.patch.object(H, "Managed", side_effect=managed))
                patches.enter_context(mock.patch.object(H, "owned_listener", return_value=None))
                patches.enter_context(mock.patch.object(H, "AdbSocket", return_value=client))
                cleanup = patches.enter_context(mock.patch.object(H, "cleanup_all", return_value=[]))
                receipt = patches.enter_context(mock.patch.object(Q, "public_receipt"))
                process = patches.enter_context(mock.patch.object(H.subprocess, "Popen"))
                connect = patches.enter_context(mock.patch.object(H.socket, "create_connection"))
                patches.enter_context(mock.patch.object(sys, "stderr", stream))
                with self.assertRaises(H.Refusal) as caught:
                    Q.capture(root)
                self.assertEqual(caught.exception.args, (self.CODE,))
                self.assertEqual([service for service, _kwargs in queried], ["host:devices",
                    "shell,v2,raw:getprop sys.boot_completed", "shell,v2,raw:getprop ro.build.version.sdk",
                    "shell,v2,raw:getprop ro.product.cpu.abi", "shell,v2,raw:dumpsys package com.android.chrome"])
                self.assertEqual(provider.call_count, 3)
                self.assertEqual(reservations.call_count, 3)
                cleanup.assert_called_once_with(born)
                receipt.assert_called_once()
                self.assertFalse(receipt.call_args.args[1]["approval"])
                self.assertEqual(receipt.call_args.args[1]["readiness_credit"], 0)
                process.assert_not_called()
                connect.assert_not_called()
                return caught.exception, stream

    def test_actual_capture_cardinality_failure_keeps_cleanup_and_bounded_public_record(self):
        original, stream = self.capture_bad_dump()
        line = stream.getvalue()
        self.assertTrue(line.isascii())
        self.assertLessEqual(len(line.encode("ascii")), 512)
        record = json.loads(line)
        self.assertEqual(record["phase"], self.PHASE)
        self.assertEqual(record["refusal_code"], self.CODE)
        self.assertEqual(record["chrome_version_shape"], dict.fromkeys(self.KEYS, 0))
        self.assertNotIn("PRIVATE", line)
        self.assertIsNone(original.__context__)

    def test_publication_interruptions_do_not_replace_capture_refusal_or_cleanup(self):
        for interruption in (RuntimeError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(interruption).__name__):
                original, _stream = self.capture_bad_dump(publication_error=interruption)
            self.assertIs(type(original), H.Refusal)
            self.assertEqual(original.args, (self.CODE,))
            self.assertIsNone(original.__context__)


class ActiveChromePackageVersionTests(unittest.TestCase):
    FIXED = "dumpsys package com.android.chrome"
    APK = "/product/app/Chrome/Chrome.apk"
    CODE = "actual-package-version-unobserved"

    @staticmethod
    def dump(*, name="123.0", code="456", hidden=None, padding=0):
        result = ("Packages:\n  Package [com.android.chrome] (abc):\n    padding=" + "x" * padding
                  + "\n    versionCode=" + code + " minSdk=26 targetSdk=36\n    versionName=" + name + "\n")
        if hidden is not None:
            result += ("Hidden system packages:\n  Package [com.android.chrome] (def):\n    versionCode="
                       + hidden[1] + " minSdk=26 targetSdk=36\n    versionName=" + hidden[0] + "\n")
        return result.encode("ascii")

    def inventory(self, dump, *, paths=None, digest=None, size=b"123\n"):
        paths = ("package:" + self.APK + "\n").encode() if paths is None else paths
        digest = ("a" * 64 + " " + self.APK + "\n").encode() if digest is None else digest
        adb = SimpleNamespace(shell=mock.Mock(side_effect=[dump, paths, digest, size]))
        return adb

    def refused(self, dump):
        adb = self.inventory(dump)
        with self.assertRaises(H.Refusal) as caught:
            H.package_inventory(adb, "com.android.chrome")
        self.assertIs(type(caught.exception), H.Refusal)
        self.assertEqual(caught.exception.args, (self.CODE,))
        self.assertIsNone(caught.exception.__context__)
        adb.shell.assert_called_once_with(self.FIXED)
        return caught.exception

    def test_active_and_hidden_are_separate_and_full_queries_are_preserved(self):
        for hidden in (None, ("98.0", "789"), ("123.0", "456")):
            with self.subTest(hidden=hidden):
                adb = self.inventory(self.dump(hidden=hidden))
                with mock.patch.object(H.subprocess, "Popen") as process, mock.patch.object(H.socket, "create_connection") as provider:
                    result = H.package_inventory(adb, "com.android.chrome")
                self.assertEqual(result["version"], "123.0")
                self.assertEqual(result["version_code"], "456")
                self.assertEqual(result["apks"], [{"path": self.APK, "sha256": "a" * 64, "bytes": 123}])
                self.assertEqual(result["publisher_signing_trust"], "not-approved-by-this-test")
                self.assertEqual(adb.shell.call_args_list, [mock.call(self.FIXED), mock.call("pm path com.android.chrome"),
                    mock.call("sha256sum " + self.APK), mock.call("stat -c %s " + self.APK)])
                process.assert_not_called()
                provider.assert_not_called()

    def test_duplicate_active_fields_even_beyond_old_boundary_refuse(self):
        for duplicate in (b"    versionName=123.0\n", b"    versionCode=456 minSdk=26 targetSdk=36\n",
                          b"    versionName=123.0\n    versionCode=456 minSdk=26 targetSdk=36\n"):
            raw = self.dump(padding=65536) + duplicate
            self.assertGreater(raw.index(duplicate), 65536)
            original = self.refused(raw)
            self.assertEqual(Q.capture_refusal_diagnostic(original, "chrome-static-device-inventory")["refusal_code"], self.CODE)

    def test_missing_repeated_reversed_or_foreign_critical_structure_refuses(self):
        active = self.dump()
        hidden = self.dump(hidden=("98.0", "789"))[len(active):]
        cases = (b"", active.replace(b"Packages:\n", b""), active.replace(b"  Package [com.android.chrome] (abc):\n", b""),
            active + active, hidden + active, active + hidden + hidden,
            active.replace(b"com.android.chrome]", b"com.android.foreign]"),
            active.replace(b"(abc):", b"(ABC):"), active.replace(b"(abc):", b"(123456789):"),
            active.replace(b"Packages:", b" Packages:"), active.replace(b"Packages:", b"Packages:PRIVATE"),
            active + b"  Package [com.android.chrome] (abc):\n",
            active + b"Renamed packages:\n  PRIVATE\n", active + b"    compat name=PRIVATE\n",
            active + b"Hidden system packages:\n",
            active + b'  Package\t[com.android.chrome] (abc):\n',
            active + b'  Package\t[com.android.foreign] (abc):\n',
            active + b'    field=Package\t[com.android.chrome] (abc):\n',
            active + b'    field=Package\t[com.android.foreign] (abc):\n',
            active + b'  Package\tcom.android.chrome (abc):\n',
            active + b'  Package\tcom.android.foreign (abc):\n',
            active + b'  Package\n',
            active + b'  Package: com.android.chrome (abc):\n',
            active + b'  Package(com.android.foreign) (abc):\n',
            active + hidden + b'  Package\t[com.android.chrome] (abc):\n',
            active + hidden + b'  Package\t[com.android.foreign] (abc):\n',
            active + hidden + b'    field=Package\t[com.android.chrome] (abc):\n',
            active + hidden + b'    field=Package\t[com.android.foreign] (abc):\n',
            active + hidden + b'  Package\tcom.android.chrome (abc):\n',
            active + hidden + b'  Package\tcom.android.foreign (abc):\n',
            active + hidden + b'  Package\n',
            active + hidden + b'  Package: com.android.chrome (abc):\n',
            active + hidden + b'  Package(com.android.foreign) (abc):\n')
        for raw in cases:
            with self.subTest(case=len(raw)):
                self.refused(raw)

    def test_closed_labels_values_and_controls_refuse_before_paths(self):
        active = self.dump()
        cases = (self.dump(name="123.0-private"), self.dump(name="1.2.3.4.5"), self.dump(code="1234567890123"),
            active.replace(b"    versionName=123.0\n", b""), active.replace(b"    versionCode=456 minSdk=26 targetSdk=36\n", b""),
            active.replace(b" minSdk=26 targetSdk=36", b""), active.replace(b"    versionName=", b"   versionName="),
            active.replace(b"versionName=", b"versionname="), active.replace(b"versionCode=", b"versionCodeMajor="),
            b"versionName=123.0\n" + active, active + b"Other:\n    versionCode=456 targetSdk=36\n",
            active + b"    PRIVATE versionName=999.0\n", active + b"Other:\n    PRIVATE Packages:\n",
            active + b"\r", active + b"\v", active + b"\f", active + b"\0")
        for raw in cases:
            with self.subTest(case=len(raw)):
                self.refused(raw)

    def test_hidden_pair_is_validated_independently_never_used_as_fallback(self):
        active = self.dump()
        complete = self.dump(hidden=("98.0", "789"))
        cases = (complete.replace(b"    versionName=98.0\n", b""), complete.replace(b"versionName=98.0", b"versionName=PRIVATE"),
            complete + b"    versionName=98.0\n", complete.replace(b"(def):", b"(DEF):"),
            complete.replace(b"    versionName=123.0\n", b""), complete.replace(b"com.android.chrome] (def)", b"com.android.foreign] (def)"))
        self.assertLess(len(active), len(complete))
        for raw in cases:
            with self.subTest(case=len(raw)):
                self.refused(raw)

    def test_actual_shell_v2_path_accepts_only_existing_dump_budget(self):
        dump = self.dump(padding=65536, hidden=("98.0", "789"))
        responses = {"shell,v2,raw:" + self.FIXED: dump, "shell,v2,raw:pm path com.android.chrome": ("package:" + self.APK + "\n").encode(),
                     "shell,v2,raw:sha256sum " + self.APK: ("a" * 64 + " " + self.APK + "\n").encode(),
                     "shell,v2,raw:stat -c %s " + self.APK: b"123\n"}
        calls = []

        def command(service, **kwargs):
            calls.append((service, kwargs))
            self.assertIn(service, responses)
            return ChromeDumpWireBudgetTests.wire(responses[service])

        client = H.AdbSocket(None)
        with (mock.patch.object(client, "command", side_effect=command), mock.patch.object(H.subprocess, "Popen") as process,
                mock.patch.object(H.socket, "create_connection") as provider):
            result = H.package_inventory(client, "com.android.chrome")
        self.assertEqual(result["version"], "123.0")
        self.assertEqual(calls, [("shell,v2,raw:" + self.FIXED, {"transport": True, "limit": 1048576}),
            ("shell,v2,raw:pm path com.android.chrome", {"transport": True}),
            ("shell,v2,raw:sha256sum " + self.APK, {"transport": True}),
            ("shell,v2,raw:stat -c %s " + self.APK, {"transport": True})])
        self.assertGreater(len(ChromeDumpWireBudgetTests.wire(dump)), 65536)
        with self.assertRaisesRegex(H.Refusal, "adb-shell-v2-total-bound"):
            H.shell_v2(ChromeDumpWireBudgetTests.wire(dump))
        process.assert_not_called()
        provider.assert_not_called()

    def test_strict_apk_path_digest_and_size_checks_remain_in_order(self):
        cases = ((b"package:/unowned/PRIVATE.apk\n", None, b"123\n", "apk-path-bound", 2),
            (None, b"PRIVATE " + self.APK.encode() + b"\n", b"123\n", "unobserved-exact-digest", 4),
            (None, None, b"0\n", "actual-apk-size-layout", 4))
        for paths, digest, size, code, count in cases:
            with self.subTest(code=code):
                adb = self.inventory(self.dump(hidden=("98.0", "789")), paths=paths, digest=digest, size=size)
                with self.assertRaises(H.Refusal) as caught:
                    H.package_inventory(adb, "com.android.chrome")
                self.assertEqual(caught.exception.args, (code,))
                self.assertEqual(adb.shell.call_count, count)
                self.assertEqual(adb.shell.call_args_list[:2], [mock.call(self.FIXED), mock.call("pm path com.android.chrome")])
                if count == 4:
                    self.assertEqual(adb.shell.call_args_list[-2:], [mock.call("sha256sum " + self.APK), mock.call("stat -c %s " + self.APK)])

    def test_selected_parser_errors_and_diagnostic_interruptions_keep_identity(self):
        for original in (H.Refusal(self.CODE), RuntimeError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            adb = self.inventory(self.dump())
            with (mock.patch.object(H, "_active_chrome_package_versions", side_effect=original),
                    mock.patch.object(H, "_note_chrome_version_shape", side_effect=KeyboardInterrupt()) as diagnostic):
                with self.assertRaises(type(original)) as caught:
                    H.package_inventory(adb, "com.android.chrome")
            self.assertIs(caught.exception, original)
            adb.shell.assert_called_once_with(self.FIXED)
            if type(original) is H.Refusal:
                self.assertIs(diagnostic.call_args.args[0], original)
                self.assertEqual(diagnostic.call_args.args[2:], (["123.0"], ["456"]))
            else:
                diagnostic.assert_not_called()

    def test_unowned_ascii_and_parser_type_bounds_remain_fail_closed(self):
        adb = SimpleNamespace(shell=mock.Mock(return_value=b"\xff"))
        with self.assertRaises(UnicodeDecodeError):
            H.package_inventory(adb, "com.android.chrome")
        adb.shell.assert_called_once_with(self.FIXED)
        adb.shell.reset_mock()
        with self.assertRaisesRegex(H.Refusal, "unowned-package-probe"):
            H.package_inventory(adb, "com.android.other")
        adb.shell.assert_not_called()
        class Text(str):
            pass
        for value in (b"PRIVATE", Text(self.dump().decode()), "x" * 1048577):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaisesRegex(H.Refusal, self.CODE):
                    H._active_chrome_package_versions(value)

    def test_actual_capture_cleanup_and_publication_failure_contract_is_retained(self):
        case = ChromeVersionShapeDiagnosticTests()
        for interruption in (None, KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(interruption=type(interruption).__name__):
                original, stream = case.capture_bad_dump(publication_error=interruption)
                self.assertIs(type(original), H.Refusal)
                self.assertEqual(original.args, (self.CODE,))
                self.assertIsNone(original.__context__)
                if interruption is None:
                    line = stream.getvalue()
                    self.assertLessEqual(len(line.encode("ascii")), 512)
                    self.assertNotIn("PRIVATE", line)
                    self.assertEqual(json.loads(line)["readiness_credit"], 0)


class ChromeParserCheckDiagnosticTests(unittest.TestCase):
    PHASE = "chrome-static-device-inventory"
    CODE = "actual-package-version-unobserved"

    def setUp(self):
        patch = mock.patch.object(H, "_chrome_parser_current_token", None)
        patch.start()
        self.addCleanup(patch.stop)

    def refused(self, raw):
        adb = SimpleNamespace(shell=mock.Mock(return_value=raw))
        with (mock.patch.object(H.socket, "create_connection") as socket_provider,
                mock.patch.object(H.subprocess, "Popen") as process_provider):
            with self.assertRaises(H.Refusal) as caught:
                H.package_inventory(adb, "com.android.chrome")
            adb.shell.assert_called_once_with("dumpsys package com.android.chrome")
            socket_provider.assert_not_called()
            process_provider.assert_not_called()
        self.assertEqual(caught.exception.args, (self.CODE,))
        self.assertIsNone(caught.exception.__context__)
        return caught.exception

    def test_reachable_checks_and_active_hidden_scopes_keep_strict_refusal(self):
        active = ActiveChromePackageVersionTests.dump()
        hidden = ActiveChromePackageVersionTests.dump(hidden=("98.0", "789"))
        rows = ((b"PRIVATE\r", "ascii-controls", "unobserved"),
            (active.replace(b"    versionName=123.0\n", b""), "block-fields", "active"),
            (b" Packages:\n", "section-title", "unobserved"),
            (active + b"Packages:\n", "active-order", "active"),
            (b"Hidden system packages:\n", "hidden-order", "unobserved"),
            (active + b"    compat name=PRIVATE\n", "renamed-compat", "active"),
            (active.replace(b"com.android.chrome]", b"com.android.foreign]"), "package-header", "active"),
            (b"  Package [com.android.chrome] (abc):\n", "package-position", "unobserved"),
            (b"    versionName=123.0\n", "version-position", "unobserved"),
            (active.replace(b"versionName=123.0", b"versionName=PRIVATE"), "version-line", "active"),
            (active + b"    versionName=123.0\n", "version-name-unique", "active"),
            (active + b"    versionCode=456 targetSdk=36\n", "version-code-unique", "active"),
            (b"Packages:\n    PRIVATE\n", "field-position", "active"),
            (b"PRIVATE\n", "active-final", "unobserved"),
            (hidden.replace(b"versionName=98.0", b"versionName=PRIVATE"), "version-line", "hidden"))
        for raw, check, scope in rows:
            with self.subTest(check=check, scope=scope):
                error = self.refused(raw)
                record = Q.capture_refusal_diagnostic(error, self.PHASE)
                self.assertEqual(record["chrome_parser_check"], {"check": check, "scope": scope,
                    **({"header_kind": "foreign-header"} if check == "package-header" else {})})
                self.assertEqual(record["refusal_code"], self.CODE)
                self.assertNotIn("PRIVATE", json.dumps(record))
        # Structurally unreachable block-unique/hidden-final are not claimed exercised.

    def test_success_preserves_four_queries_apk_proof_and_clears_signal(self):
        original_case = ActiveChromePackageVersionTests()
        for hidden in (None, ("98.0", "789")):
            with self.subTest(hidden=hidden):
                adb = original_case.inventory(original_case.dump(hidden=hidden))
                with (mock.patch.object(H.subprocess, "Popen") as process,
                        mock.patch.object(H.socket, "create_connection") as provider):
                    result = H.package_inventory(adb, "com.android.chrome")
                self.assertEqual(result["version"], "123.0")
                self.assertEqual(result["version_code"], "456")
                self.assertEqual(result["apks"], [{"path": original_case.APK, "sha256": "a" * 64, "bytes": 123}])
                self.assertEqual(adb.shell.call_args_list, [mock.call(original_case.FIXED),
                    mock.call("pm path com.android.chrome"), mock.call("sha256sum " + original_case.APK),
                    mock.call("stat -c %s " + original_case.APK)])
                self.assertIsNone(H._chrome_parser_current_token)
                self.assertIsNone(Q.chrome_parser_check_diagnostic(H.Refusal(self.CODE)))
                process.assert_not_called()
                provider.assert_not_called()

    def test_allocation_setup_faults_keep_one_original_parser_call(self):
        parser = H._active_chrome_package_versions
        for seam in ("object", "_new_chrome_parser_context"):
            for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
                with (self.subTest(seam=seam, kind=type(fault).__name__),
                        mock.patch.object(H, seam, side_effect=fault, create=True),
                        mock.patch.object(H, "_active_chrome_package_versions", wraps=parser) as observed):
                    error = self.refused(b"PRIVATE\n")
                observed.assert_called_once_with("PRIVATE\n", diagnostic_context=None)
                self.assertIsNone(H._chrome_parser_current_token)
                self.assertNotIn("chrome_parser_check", Q.capture_refusal_diagnostic(error, self.PHASE))
        stale = {"attempt_token": object()}
        for candidate in (stale, None, [], {"PRIVATE": object()}):
            with (self.subTest(kind=type(candidate).__name__),
                    mock.patch.object(H, "_new_chrome_parser_context", return_value=candidate),
                    mock.patch.object(H, "_active_chrome_package_versions", wraps=parser) as observed):
                error = self.refused(b"PRIVATE\n")
            observed.assert_called_once_with("PRIVATE\n", diagnostic_context=None)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

        class TextKey(str):
            pass
        def malformed(token):
            return {TextKey("attempt_token"): token}
        with (mock.patch.object(H, "_new_chrome_parser_context", side_effect=malformed),
                mock.patch.object(H, "_active_chrome_package_versions", wraps=parser) as observed):
            error = self.refused(b"PRIVATE\n")
        observed.assert_called_once_with("PRIVATE\n", diagnostic_context=None)
        self.assertIsNone(H._chrome_parser_current_token)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        token = object()
        H._chrome_parser_current_token = token
        with self.assertRaises(H.Refusal) as caught:
            parser("PRIVATE\n", diagnostic_context={TextKey("attempt_token"): token})
        self.assertEqual(caught.exception.args, (self.CODE,))
        self.assertIsNone(Q.chrome_parser_check_diagnostic(caught.exception))

    def test_setup_fault_with_valid_dump_keeps_original_success_and_queries(self):
        case = ActiveChromePackageVersionTests()
        for fault in (MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            adb = case.inventory(case.dump())
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(H, "_new_chrome_parser_context", side_effect=fault),
                    mock.patch.object(H.subprocess, "Popen") as process,
                    mock.patch.object(H.socket, "create_connection") as provider):
                result = H.package_inventory(adb, "com.android.chrome")
            self.assertEqual(result["version"], "123.0")
            self.assertEqual(adb.shell.call_args_list, [mock.call(case.FIXED), mock.call("pm path com.android.chrome"),
                mock.call("sha256sum " + case.APK), mock.call("stat -c %s " + case.APK)])
            self.assertIsNone(H._chrome_parser_current_token)
            process.assert_not_called()
            provider.assert_not_called()

    def test_annotation_complete_then_raise_invalidates_only_current_token(self):
        annotate = H._annotate_chrome_parser_context
        for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            def failed(context, error, check, scope, fault=fault):
                annotate(context, error, check, scope)
                self.assertEqual(set(context), {"attempt_token", "selected_error", "check", "scope"})
                raise fault
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(H, "_annotate_chrome_parser_context", side_effect=failed)):
                error = self.refused(b"PRIVATE\n")
            self.assertIsNone(H._chrome_parser_current_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        newer = object()
        def replaced(context, error, check, scope):
            annotate(context, error, check, scope)
            H._chrome_parser_current_token = newer
            raise KeyboardInterrupt()
        with mock.patch.object(H, "_annotate_chrome_parser_context", side_effect=replaced):
            error = self.refused(b"PRIVATE\n")
        self.assertIs(H._chrome_parser_current_token, newer)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_attachment_complete_then_raise_invalidates_only_current_token(self):
        attach = H._note_chrome_parser_check
        for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            def failed(error, context, token, fault=fault):
                attach(error, context, token)
                self.assertEqual(set(error.chrome_parser_check), {"attempt_token", "selected_error", "check", "scope"})
                raise fault
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(H, "_note_chrome_parser_check", side_effect=failed)):
                error = self.refused(b"PRIVATE\n")
            self.assertIsNone(H._chrome_parser_current_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        newer = object()
        def replaced(error, context, token):
            attach(error, context, token)
            H._chrome_parser_current_token = newer
            raise SystemExit(9)
        with mock.patch.object(H, "_note_chrome_parser_check", side_effect=replaced):
            error = self.refused(b"PRIVATE\n")
        self.assertIs(H._chrome_parser_current_token, newer)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_reused_refusal_and_failed_stale_clear_cannot_publish_old_record(self):
        error = self.refused(b"PRIVATE\n")
        old = error.chrome_parser_check
        old_token = old["attempt_token"]
        self.assertIsNotNone(Q.chrome_parser_check_diagnostic(error))
        for fault in (MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(H.Refusal, "__delattr__", side_effect=fault),
                    mock.patch.object(H, "_active_chrome_package_versions", side_effect=error)):
                selected = self.refused(b"PRIVATE\n")
            self.assertIs(selected, error)
            self.assertIs(error.chrome_parser_check, old)
            self.assertIsNot(H._chrome_parser_current_token, old_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        with (mock.patch.object(H, "_new_chrome_parser_context", side_effect=MemoryError()),
                mock.patch.object(H.Refusal, "__delattr__", side_effect=KeyboardInterrupt()),
                mock.patch.object(H, "_active_chrome_package_versions", side_effect=error)):
            self.assertIs(self.refused(b"PRIVATE\n"), error)
        self.assertIsNone(H._chrome_parser_current_token)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_partial_annotation_and_wrong_selected_context_omit(self):
        def partial(context, error, check, scope):
            context["selected_error"] = error
            raise KeyboardInterrupt()
        with mock.patch.object(H, "_annotate_chrome_parser_context", side_effect=partial):
            error = self.refused(b"PRIVATE\n")
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        token = object()
        H._chrome_parser_current_token = token
        context = {"attempt_token": token, "selected_error": H.Refusal(self.CODE),
                   "check": "active-final", "scope": "unobserved"}
        H._note_chrome_parser_check(error, context, token)
        self.assertNotIn("chrome_parser_check", error.__dict__)
        H._chrome_parser_current_token = object()
        context["selected_error"] = error
        H._note_chrome_parser_check(error, context, token)
        self.assertNotIn("chrome_parser_check", error.__dict__)

    def test_closed_projection_types_keys_context_and_privacy(self):
        class Text(str):
            pass
        class Mapping(dict):
            pass
        token, other = object(), H.Refusal(self.CODE)
        H._chrome_parser_current_token = token
        error = H.Refusal(self.CODE)
        good = {"attempt_token": token, "selected_error": error, "check": "active-final", "scope": "unobserved"}
        cases = (None, [], Mapping(good), {**good, "PRIVATE": 1},
            {key: value for key, value in good.items() if key != "scope"},
            {**good, "attempt_token": object()}, {**good, "selected_error": other},
            {**good, "check": Text("active-final")}, {**good, "scope": Text("unobserved")},
            {**good, "check": True}, {**good, "scope": None}, {**good, "check": "PRIVATE"}, {**good, "scope": "PRIVATE"})
        for value in cases:
            with self.subTest(kind=type(value).__name__):
                error.chrome_parser_check = value
                self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        error.chrome_parser_check = good
        self.assertEqual(Q.chrome_parser_check_diagnostic(error), {"check": "active-final", "scope": "unobserved"})
        for phase in ("sdk-observation", "owned-api36-emulator", self.PHASE + " ", "PRIVATE"):
            self.assertNotIn("chrome_parser_check", Q.capture_refusal_diagnostic(error, phase))
        for selected in (H.Refusal("adb-output-bound"), H.Refusal(self.CODE, "PRIVATE"), RuntimeError(self.CODE)):
            selected.chrome_parser_check = {**good, "selected_error": selected}
            self.assertIsNone(Q.chrome_parser_check_diagnostic(selected))
        class Alias(H.Refusal):
            pass
        selected = Alias(self.CODE)
        selected.chrome_parser_check = {**good, "selected_error": selected}
        self.assertIsNone(Q.chrome_parser_check_diagnostic(selected))

    def test_projector_signal_change_and_poisoned_access_omit(self):
        error = self.refused(b"PRIVATE\n")
        first = H._chrome_parser_current_token
        class ChangingHost:
            Refusal = H.Refusal
            def __init__(self):
                self.reads = 0
            @property
            def _chrome_parser_current_token(self):
                self.reads += 1
                return first if self.reads == 1 else object()
        host = ChangingHost()
        with mock.patch.object(Q, "H", host):
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        self.assertEqual(host.reads, 2)
        class Poisoned(H.Refusal):
            def __getattribute__(self, name):
                if name == "__dict__":
                    raise KeyboardInterrupt()
                return super().__getattribute__(name)
        with mock.patch.object(H, "Refusal", Poisoned):
            selected = Poisoned(self.CODE)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(selected))
        for fault in (MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(Q, "chrome_parser_check_diagnostic", side_effect=fault)):
                record = Q.capture_refusal_diagnostic(error, self.PHASE)
            self.assertNotIn("chrome_parser_check", record)
            self.assertEqual(record["refusal_code"], self.CODE)
            self.assertEqual(record["chrome_version_shape"], dict.fromkeys(ChromeVersionShapeDiagnosticTests.KEYS, 0))

    def test_input_scope_and_success_then_later_errors_cannot_inherit(self):
        error = self.refused(b"PRIVATE\n")
        self.assertIsNotNone(Q.chrome_parser_check_diagnostic(error))
        adb = SimpleNamespace(shell=mock.Mock(return_value=b"\xff"))
        with self.assertRaises(UnicodeDecodeError):
            H.package_inventory(adb, "com.android.chrome")
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        with self.assertRaisesRegex(H.Refusal, "unowned-package-probe"):
            H.package_inventory(adb, "com.android.other")
        self.assertIsNone(H._chrome_parser_current_token)
        case = ActiveChromePackageVersionTests()
        later = H.Refusal(self.CODE)
        later.chrome_parser_check = error.chrome_parser_check
        adb = case.inventory(case.dump())
        adb.shell.side_effect = [case.dump(), later]
        with self.assertRaises(H.Refusal) as caught:
            H.package_inventory(adb, "com.android.chrome")
        self.assertIs(caught.exception, later)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(later))
        self.assertEqual(adb.shell.call_args_list, [mock.call(case.FIXED), mock.call("pm path com.android.chrome")])

    def test_actual_capture_keeps_original_cleanup_and_publication_faults(self):
        case = ChromeVersionShapeDiagnosticTests()
        for fault in (None, MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(fault).__name__):
                error, stream = case.capture_bad_dump(publication_error=fault)
            self.assertEqual(error.args, (self.CODE,))
            self.assertIsNone(error.__context__)
            if fault is None:
                line = stream.getvalue()
                self.assertLessEqual(len(line.encode("ascii")), 512)
                self.assertEqual(json.loads(line)["chrome_parser_check"], {"check": "active-final", "scope": "unobserved"})
                self.assertNotIn("PRIVATE", line)
        with mock.patch.object(H, "_new_chrome_parser_context", side_effect=KeyboardInterrupt()):
            error, stream = case.capture_bad_dump()
        self.assertNotIn("chrome_parser_check", json.loads(stream.getvalue()))
        self.assertEqual(error.args, (self.CODE,))

    def test_maximum_closed_combined_record_is_bounded_and_token_free(self):
        token = object()
        H._chrome_parser_current_token = token
        error = H.Refusal(self.CODE)
        error.chrome_version_shape = dict.fromkeys(ChromeVersionShapeDiagnosticTests.KEYS, 2)
        error.chrome_parser_check = {"attempt_token": token, "selected_error": error,
            "check": "version-code-unique", "scope": "unobserved"}
        line = json.dumps(Q.capture_refusal_diagnostic(error, self.PHASE), ensure_ascii=True, separators=(",", ":")) + "\n"
        self.assertEqual(len(line.encode("ascii")), 359)
        self.assertNotIn("attempt_token", line)
        self.assertNotIn("selected_error", line)
        self.assertNotIn("PRIVATE", line)


class ChromeHeaderKindDiagnosticTests(unittest.TestCase):
    PHASE = "chrome-static-device-inventory"
    CODE = "actual-package-version-unobserved"
    ROWS = ((b"\tPackage [com.android.chrome] (abc):", "target-spacing"),
            (b"  Package [com.android.chrome] (ABC):", "target-identity"),
            (b"  Package [com.android.chrome] (abc)", "target-suffix"),
            (b"  Package [com.android.foreign] (abc):", "foreign-header"),
            (b"Package Changes:", "keyword-title"),
            (b"Package\tPRIVATE", "keyword-prefix"),
            (b"PRIVATE Package [com.android.chrome] (abc):", "embedded-header"),
            (b"Package " + b"P" * 249, "over-bound"))

    def setUp(self):
        ChromeParserCheckDiagnosticTests.setUp(self)

    def refused(self, raw):
        return ChromeParserCheckDiagnosticTests.refused(self, raw)

    @staticmethod
    def raw_for(header, scope):
        active = ActiveChromePackageVersionTests.dump()
        if scope == "active":
            return b"Packages:\n" + header + b"\n"
        if scope == "hidden":
            return active + b"Hidden system packages:\n" + header + b"\n"
        if scope == "before":
            return header + b"\n" + ActiveChromePackageVersionTests.dump(hidden=("98.0", "789"))
        if scope == "after":
            return active + b"Ancillary:\n" + header + b"\n"
        raise AssertionError("unknown synthetic scope")

    def test_eight_structural_categories_on_selected_parser_failures_and_scopes(self):
        for header, kind in self.ROWS:
            for scope in ("active", "hidden", "before", "after"):
                with self.subTest(kind=kind, scope=scope):
                    error = self.refused(self.raw_for(header, scope))
                    expected_scope = scope if scope in ("active", "hidden") else "unobserved"
                    record = Q.capture_refusal_diagnostic(error, self.PHASE)
                    self.assertEqual(record["chrome_parser_check"],
                        {"check": "package-header", "scope": expected_scope, "header_kind": kind,
                         **({"keyword_context": ("before-active-horizontal-word" if scope == "before"
                                                  else "after-active-horizontal-word")}
                            if kind == "keyword-prefix" else {})})
                    self.assertEqual(set(error.chrome_parser_check),
                        {"attempt_token", "selected_error", "check", "scope", "header_kind"}
                        | ({"keyword_context"} if kind == "keyword-prefix" else set()))
                    self.assertIs(error.chrome_parser_check["selected_error"], error)
                    self.assertNotIn("PRIVATE", json.dumps(record))
                    self.assertNotIn("com.android.foreign", json.dumps(record))

    def test_defensive_fallback_direct_branch_and_explicit_mocked_seam(self):
        # No claim that this fallback has a present production candidate.
        self.assertEqual(H._chrome_package_header_kind("PRIVATE"), "other-candidate")
        with mock.patch.object(H, "_chrome_package_header_kind", return_value="other-candidate") as classifier:
            error = self.refused(b"Package\tPRIVATE\n")
        classifier.assert_called_once_with("Package\tPRIVATE")
        self.assertEqual(Q.chrome_parser_check_diagnostic(error),
            {"check": "package-header", "scope": "unobserved", "header_kind": "other-candidate"})

    def test_boundary_and_over_bound_precedes_all_classifier_regex_work(self):
        for size, kind in ((256, "keyword-prefix"), (257, "over-bound")):
            header = b"Package " + b"P" * (size - 8)
            with self.subTest(size=size):
                error = self.refused(header + b"\n")
                self.assertEqual(Q.chrome_parser_check_diagnostic(error)["header_kind"], kind)
        with (mock.patch.object(H.re, "fullmatch", side_effect=AssertionError("regex")) as full,
                mock.patch.object(H.re, "match", side_effect=AssertionError("regex")) as match,
                mock.patch.object(H.re, "search", side_effect=AssertionError("regex")) as search):
            self.assertEqual(H._chrome_package_header_kind("Package " + "P" * 249), "over-bound")
        full.assert_not_called()
        match.assert_not_called()
        search.assert_not_called()

    def test_exact_type_guard_rejects_subclass_before_its_methods(self):
        class Text(str):
            def __len__(self):
                raise AssertionError("length")
            def strip(self, *args):
                raise AssertionError("strip")
            def lower(self):
                raise AssertionError("lower")
        for value in (None, True, [], b"Package PRIVATE", Text("Package PRIVATE")):
            with self.subTest(kind=type(value).__name__):
                self.assertIsNone(H._chrome_package_header_kind(value))

    def test_classification_is_after_original_selected_refusal(self):
        selected = []
        def classifier(line):
            self.assertEqual(line, "Package\tPRIVATE")
            error = sys.exc_info()[1]
            self.assertIs(type(error), H.Refusal)
            self.assertEqual(error.args, (self.CODE,))
            selected.append(error)
            return "keyword-prefix"
        with mock.patch.object(H, "_chrome_package_header_kind", side_effect=classifier) as observed:
            error = self.refused(b"Package\tPRIVATE\n")
        observed.assert_called_once_with("Package\tPRIVATE")
        self.assertEqual(len(selected), 1)
        self.assertIs(error, selected[0])

    def test_valid_inventory_and_other_checks_never_invoke_classifier(self):
        case = ActiveChromePackageVersionTests()
        with mock.patch.object(H, "_chrome_package_header_kind", side_effect=AssertionError("category")) as classifier:
            for hidden in (None, ("98.0", "789")):
                adb = case.inventory(case.dump(hidden=hidden))
                with (mock.patch.object(H.subprocess, "Popen") as process,
                        mock.patch.object(H.socket, "create_connection") as provider):
                    result = H.package_inventory(adb, "com.android.chrome")
                self.assertEqual(result["version"], "123.0")
                self.assertEqual(result["version_code"], "456")
                self.assertEqual(result["apks"], [{"path": case.APK, "sha256": "a" * 64, "bytes": 123}])
                self.assertEqual(adb.shell.call_args_list, [mock.call(case.FIXED),
                    mock.call("pm path com.android.chrome"), mock.call("sha256sum " + case.APK),
                    mock.call("stat -c %s " + case.APK)])
                self.assertIsNone(H._chrome_parser_current_token)
                process.assert_not_called()
                provider.assert_not_called()
            error = self.refused(b"PRIVATE\n")
        classifier.assert_not_called()
        self.assertEqual(Q.chrome_parser_check_diagnostic(error), {"check": "active-final", "scope": "unobserved"})
        self.assertEqual(len(error.chrome_parser_check), 4)

    def test_classifier_faults_and_invalid_returns_keep_original_four_fields(self):
        class Text(str):
            pass
        for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(H, "_chrome_package_header_kind", side_effect=fault)):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertEqual(Q.chrome_parser_check_diagnostic(error), {"check": "package-header", "scope": "unobserved"})
            self.assertEqual(set(error.chrome_parser_check), {"attempt_token", "selected_error", "check", "scope"})
        for value in (None, True, [], "PRIVATE", Text("keyword-prefix")):
            with (self.subTest(kind=type(value).__name__),
                    mock.patch.object(H, "_chrome_package_header_kind", return_value=value)):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertEqual(Q.chrome_parser_check_diagnostic(error), {"check": "package-header", "scope": "unobserved"})
            self.assertEqual(len(error.chrome_parser_check), 4)

    def test_complete_annotation_faults_invalidate_only_matching_token(self):
        annotate = H._annotate_chrome_parser_context
        for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            def failed(context, error, check, scope, fault=fault):
                annotate(context, error, check, scope)
                context["header_kind"] = "keyword-prefix"
                self.assertEqual(len(context), 5)
                raise fault
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(H, "_annotate_chrome_parser_context", side_effect=failed)):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertIsNone(H._chrome_parser_current_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        newer = object()
        def replaced(context, error, check, scope):
            annotate(context, error, check, scope)
            context["header_kind"] = "keyword-prefix"
            H._chrome_parser_current_token = newer
            raise KeyboardInterrupt()
        with mock.patch.object(H, "_annotate_chrome_parser_context", side_effect=replaced):
            error = self.refused(b"Package\tPRIVATE\n")
        self.assertIs(H._chrome_parser_current_token, newer)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_complete_attachment_faults_invalidate_only_matching_token(self):
        attach = H._note_chrome_parser_check
        for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            def failed(error, context, token, fault=fault):
                attach(error, context, token)
                self.assertEqual(len(error.chrome_parser_check), 6)
                raise fault
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(H, "_note_chrome_parser_check", side_effect=failed)):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertIsNone(H._chrome_parser_current_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        newer = object()
        def replaced(error, context, token):
            attach(error, context, token)
            H._chrome_parser_current_token = newer
            raise SystemExit(9)
        with mock.patch.object(H, "_note_chrome_parser_check", side_effect=replaced):
            error = self.refused(b"Package\tPRIVATE\n")
        self.assertIs(H._chrome_parser_current_token, newer)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_independent_H_Q_key_type_value_and_context_closure(self):
        class Text(str):
            pass
        class Mapping(dict):
            pass
        error = self.refused(b"Package\tPRIVATE\n")
        token = H._chrome_parser_current_token
        good = {key: value for key, value in error.chrome_parser_check.items() if key != "keyword_context"}
        bad_key = {Text("attempt_token"): token, **{key: value for key, value in good.items() if key != "attempt_token"}}
        cases = (None, [], Mapping(good), {**good, "PRIVATE": 1}, bad_key,
            {**good, "header_kind": None}, {**good, "header_kind": True},
            {**good, "header_kind": Text("keyword-prefix")}, {**good, "header_kind": "PRIVATE"},
            {**good, "check": "active-final"}, {**good, "check": Text("package-header")},
            {**good, "scope": Text("unobserved")}, {**good, "attempt_token": object()},
            {**good, "selected_error": H.Refusal(self.CODE)})
        for context in cases:
            with self.subTest(kind=type(context).__name__):
                error.__dict__.pop("chrome_parser_check", None)
                H._note_chrome_parser_check(error, context, token)
                self.assertNotIn("chrome_parser_check", error.__dict__)
                error.chrome_parser_check = context
                self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        for kind in H.CHROME_HEADER_KINDS:
            context = {**good, "header_kind": kind}
            H._note_chrome_parser_check(error, context, token)
            self.assertEqual(Q.chrome_parser_check_diagnostic(error),
                {"check": "package-header", "scope": "unobserved", "header_kind": kind})
        for phase in ("sdk-observation", "owned-api36-emulator", "PRIVATE"):
            self.assertNotIn("chrome_parser_check", Q.capture_refusal_diagnostic(error, phase))
        for selected in (H.Refusal("adb-output-bound"), H.Refusal(self.CODE, "PRIVATE"), RuntimeError(self.CODE)):
            selected.chrome_parser_check = {**good, "selected_error": selected}
            self.assertIsNone(Q.chrome_parser_check_diagnostic(selected))

    def test_reused_error_failed_clear_and_projection_signal_changes_omit(self):
        error = self.refused(b"Package\tPRIVATE\n")
        old = error.chrome_parser_check
        old_token = old["attempt_token"]
        for fault in (MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(H.Refusal, "__delattr__", side_effect=fault),
                    mock.patch.object(H, "_active_chrome_package_versions", side_effect=error)):
                self.assertIs(self.refused(b"Package\tPRIVATE\n"), error)
            self.assertIs(error.chrome_parser_check, old)
            self.assertIsNot(H._chrome_parser_current_token, old_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        H._chrome_parser_current_token = old_token
        class ChangingHost:
            Refusal = H.Refusal
            def __init__(self):
                self.reads = 0
            @property
            def _chrome_parser_current_token(self):
                self.reads += 1
                return old_token if self.reads == 1 else object()
        host = ChangingHost()
        with mock.patch.object(Q, "H", host):
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        self.assertEqual(host.reads, 2)
        for fault in (MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with mock.patch.object(Q, "chrome_parser_check_diagnostic", side_effect=fault):
                record = Q.capture_refusal_diagnostic(error, self.PHASE)
            self.assertEqual(record["refusal_code"], self.CODE)
            self.assertNotIn("chrome_parser_check", record)

    def test_closed_public_bound_and_private_input_are_not_serialized(self):
        token = object()
        H._chrome_parser_current_token = token
        error = H.Refusal(self.CODE)
        error.chrome_version_shape = dict.fromkeys(ChromeVersionShapeDiagnosticTests.KEYS, 2)
        maximum = 0
        for kind in H.CHROME_HEADER_KINDS:
            for scope in H.CHROME_PARSER_SCOPES:
                error.chrome_parser_check = {"attempt_token": token, "selected_error": error,
                    "check": "package-header", "scope": scope, "header_kind": kind}
                line = json.dumps(Q.capture_refusal_diagnostic(error, self.PHASE), ensure_ascii=True, separators=(",", ":")) + "\n"
                maximum = max(maximum, len(line.encode("ascii")))
                self.assertLessEqual(len(line.encode("ascii")), 512)
                self.assertNotIn("attempt_token", line)
                self.assertNotIn("selected_error", line)
        self.assertEqual(maximum, 386)
        for header, _kind in self.ROWS:
            selected = self.refused(header + b"\n")
            line = json.dumps(Q.capture_refusal_diagnostic(selected, self.PHASE))
            self.assertNotIn("PRIVATE", line)
            self.assertNotIn("com.android.foreign", line)
            self.assertNotIn("com.android.chrome", line)
            self.assertNotIn("Package Changes", line)

    def test_actual_capture_cleanup_and_publication_interruptions_unchanged(self):
        case = ChromeVersionShapeDiagnosticTests()
        original_wire = ChromeDumpWireBudgetTests.wire
        def wire(raw):
            return original_wire(b"Package\tPRIVATE\n" if raw == b"PRIVATE\n" else raw)
        for fault in (None, MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with (self.subTest(kind=type(fault).__name__),
                    mock.patch.object(ChromeDumpWireBudgetTests, "wire", side_effect=wire)):
                error, stream = case.capture_bad_dump(publication_error=fault)
            self.assertIs(type(error), H.Refusal)
            self.assertEqual(error.args, (self.CODE,))
            self.assertIsNone(error.__context__)
            if fault is None:
                line = stream.getvalue()
                self.assertLessEqual(len(line.encode("ascii")), 512)
                self.assertEqual(json.loads(line)["chrome_parser_check"],
                    {"check": "package-header", "scope": "unobserved", "header_kind": "keyword-prefix",
                     "keyword_context": "before-active-horizontal-word"})
                self.assertNotIn("PRIVATE", line)


class ChromeKeywordContextDiagnosticTests(unittest.TestCase):
    PHASE = "chrome-static-device-inventory"
    CODE = "actual-package-version-unobserved"
    FORMS = ((b"Package", "bare"), (b"Package [PRIVATE]", "horizontal-bracket"),
             (b"Package PRIVATE", "horizontal-word"), (b"Package (PRIVATE)", "horizontal-other"),
             (b"Package: PRIVATE", "colon"), (b"Package=PRIVATE", "equals"),
             (b"Package[PRIVATE]", "bracket"), (b"Package{PRIVATE}", "other-punctuation"))

    def setUp(self):
        ChromeParserCheckDiagnosticTests.setUp(self)

    def refused(self, raw):
        return ChromeParserCheckDiagnosticTests.refused(self, raw)

    def projected(self, error):
        return Q.capture_refusal_diagnostic(error, self.PHASE)["chrome_parser_check"]

    def test_all_sixteen_genuine_selected_refusal_contexts_keep_original_query(self):
        case = ActiveChromePackageVersionTests()
        for header, form in self.FORMS:
            for scope, place in (("before", "before-active"), ("after", "after-active")):
                raw = ChromeHeaderKindDiagnosticTests.raw_for(header, scope)
                adb = case.inventory(raw)
                with (self.subTest(form=form, scope=scope),
                        mock.patch.object(H.subprocess, "Popen") as native,
                        mock.patch.object(H.socket, "create_connection") as provider):
                    with self.assertRaises(H.Refusal) as caught:
                        H.package_inventory(adb, "com.android.chrome")
                error = caught.exception
                self.assertIs(type(error), H.Refusal)
                self.assertEqual(error.args, (self.CODE,))
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
                self.assertEqual(self.projected(error), {"check": "package-header", "scope": "unobserved",
                    "header_kind": "keyword-prefix", "keyword_context": place + "-" + form})
                self.assertEqual(set(error.chrome_parser_check),
                    {"attempt_token", "selected_error", "check", "scope", "header_kind", "keyword_context"})
                self.assertIs(error.chrome_parser_check["selected_error"], error)
                self.assertIs(error.chrome_parser_check["attempt_token"], H._chrome_parser_current_token)
                adb.shell.assert_called_once_with(case.FIXED)
                native.assert_not_called()
                provider.assert_not_called()

    def test_both_end_horizontal_strip_and_internal_tab_have_distinct_contexts(self):
        for raw, form in ((b"Package \t", "bare"), (b" \tPackage\tPRIVATE \t", "horizontal-word"),
                          (b"Package\t(PRIVATE)", "horizontal-other")):
            with self.subTest(form=form):
                error = self.refused(raw + b"\n")
            self.assertEqual(self.projected(error)["keyword_context"], "before-active-" + form)
        self.assertEqual(H._chrome_keyword_context("Package \t", 0), "before-active-bare")
        self.assertEqual(H._chrome_keyword_context("Package\tPRIVATE", 0), "before-active-horizontal-word")

    def test_active_and_hidden_scope_can_only_report_after_active(self):
        for scope in ("active", "hidden"):
            with self.subTest(scope=scope):
                error = self.refused(ChromeHeaderKindDiagnosticTests.raw_for(b"Package\tPRIVATE", scope))
            self.assertEqual(self.projected(error), {"check": "package-header", "scope": scope,
                "header_kind": "keyword-prefix", "keyword_context": "after-active-horizontal-word"})

    def test_context_classifier_runs_after_same_original_selected_refusal(self):
        selected = []
        original = H._chrome_keyword_context
        def classify(line, count):
            error = sys.exc_info()[1]
            self.assertIs(type(error), H.Refusal)
            self.assertEqual(error.args, (self.CODE,))
            self.assertEqual((line, count), ("Package\tPRIVATE", 0))
            selected.append(error)
            return original(line, count)
        with mock.patch.object(H, "_chrome_keyword_context", side_effect=classify) as classifier:
            error = self.refused(b"Package\tPRIVATE\n")
        classifier.assert_called_once_with("Package\tPRIVATE", 0)
        self.assertEqual(selected, [error])
        self.assertIs(error, selected[0])

    def test_256_boundary_and_257_never_enter_optional_classifier(self):
        original = H._chrome_keyword_context
        for size in (256, 257):
            header = b"Package " + b"P" * (size - 8)
            with self.subTest(size=size), mock.patch.object(H, "_chrome_keyword_context", side_effect=original) as classifier:
                error = self.refused(header + b"\n")
            if size == 256:
                classifier.assert_called_once_with(header.decode("ascii"), 0)
                self.assertEqual(self.projected(error)["keyword_context"], "before-active-horizontal-word")
            else:
                classifier.assert_not_called()
                self.assertEqual(self.projected(error), {"check": "package-header", "scope": "unobserved", "header_kind": "over-bound"})
        self.assertIsNone(H._chrome_keyword_context("Package " + "P" * 249, 0))

    def test_exact_line_and_exact_integer_count_reject_before_faulting_methods(self):
        class Text(str):
            def __len__(self):
                raise AssertionError("length")
            def strip(self, *args):
                raise AssertionError("strip")
        class Integer(int):
            def __eq__(self, other):
                raise AssertionError("equality")
        for value in (None, True, [], b"Package PRIVATE", Text("Package PRIVATE")):
            with self.subTest(kind=type(value).__name__):
                self.assertIsNone(H._chrome_keyword_context(value, 0))
        for count in (None, False, True, -1, 2, 0.0, "0", Integer(0)):
            with self.subTest(kind=type(count).__name__):
                self.assertIsNone(H._chrome_keyword_context("Package PRIVATE", count))
        self.assertEqual(H._chrome_keyword_context("Package PRIVATE", 0), "before-active-horizontal-word")
        self.assertEqual(H._chrome_keyword_context("Package PRIVATE", 1), "after-active-horizontal-word")

    def test_invalid_state_and_classifier_faults_keep_eligible_five_fields(self):
        original = H._chrome_keyword_context
        for count in (None, True, False, -1, 2, "0"):
            with self.subTest(count=count), mock.patch.object(H, "_chrome_keyword_context", side_effect=lambda line, _count, count=count: original(line, count)):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertEqual(self.projected(error), {"check": "package-header", "scope": "unobserved", "header_kind": "keyword-prefix"})
            self.assertEqual(len(error.chrome_parser_check), 5)
        class Text(str):
            pass
        for fault in (MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(setup=type(fault).__name__), mock.patch.object(H, "_new_chrome_parser_context", side_effect=fault):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertEqual(error.args, (self.CODE,))
            self.assertIsNone(H._chrome_parser_current_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        def malformed(token):
            return {Text("attempt_token"): token}
        with mock.patch.object(H, "_new_chrome_parser_context", side_effect=malformed):
            error = self.refused(b"Package\tPRIVATE\n")
        self.assertEqual(error.args, (self.CODE,))
        self.assertIsNone(H._chrome_parser_current_token)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(fault).__name__), mock.patch.object(H, "_chrome_keyword_context", side_effect=fault):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertEqual(self.projected(error), {"check": "package-header", "scope": "unobserved", "header_kind": "keyword-prefix"})
            self.assertEqual(len(error.chrome_parser_check), 5)

    def test_invalid_optional_returns_keep_eligible_five_fields(self):
        class Text(str):
            pass
        for value in (None, True, [], "PRIVATE", Text("before-active-horizontal-word")):
            with self.subTest(kind=type(value).__name__), mock.patch.object(H, "_chrome_keyword_context", return_value=value):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertEqual(self.projected(error), {"check": "package-header", "scope": "unobserved", "header_kind": "keyword-prefix"})
            self.assertEqual(len(error.chrome_parser_check), 5)
        with mock.patch.object(H, "_chrome_keyword_context", return_value="before-active-horizontal-word"):
            error = self.refused(ChromeHeaderKindDiagnosticTests.raw_for(b"Package\tPRIVATE", "active"))
        self.assertEqual(self.projected(error), {"check": "package-header", "scope": "active", "header_kind": "keyword-prefix"})

    def test_independent_H_Q_all_four_five_six_key_grammars(self):
        class Text(str):
            pass
        class Mapping(dict):
            pass
        error = self.refused(b"Package\tPRIVATE\n")
        token = H._chrome_parser_current_token
        six = dict(error.chrome_parser_check)
        five = {key: value for key, value in six.items() if key != "keyword_context"}
        four = {key: value for key, value in five.items() if key != "header_kind"}
        for context, expected in ((four, {"check": "package-header", "scope": "unobserved"}),
                                  (five, {"check": "package-header", "scope": "unobserved", "header_kind": "keyword-prefix"}),
                                  (six, {"check": "package-header", "scope": "unobserved", "header_kind": "keyword-prefix", "keyword_context": "before-active-horizontal-word"})):
            error.__dict__.pop("chrome_parser_check", None)
            H._note_chrome_parser_check(error, context, token)
            self.assertEqual(Q.chrome_parser_check_diagnostic(error), expected)
        bad_key = {Text("keyword_context"): six["keyword_context"], **{key: value for key, value in six.items() if key != "keyword_context"}}
        cases = (None, [], Mapping(six), {**six, "PRIVATE": 1}, bad_key,
            {**six, "keyword_context": None}, {**six, "keyword_context": True},
            {**six, "keyword_context": Text("before-active-horizontal-word")}, {**six, "keyword_context": "PRIVATE"},
            {key: value for key, value in six.items() if key != "header_kind"},
            {**six, "header_kind": "target-spacing"}, {**six, "check": "active-final"},
            {**six, "scope": "active"}, {**six, "scope": "hidden"},
            {**six, "attempt_token": object()}, {**six, "selected_error": H.Refusal(self.CODE)})
        for context in cases:
            with self.subTest(kind=type(context).__name__):
                error.__dict__.pop("chrome_parser_check", None)
                H._note_chrome_parser_check(error, context, token)
                self.assertNotIn("chrome_parser_check", error.__dict__)
                error.chrome_parser_check = context
                self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        for key in six:
            context = {Text(current) if current == key else current: value for current, value in six.items()}
            with self.subTest(subclass_key=key):
                error.__dict__.pop("chrome_parser_check", None)
                H._note_chrome_parser_check(error, context, token)
                self.assertNotIn("chrome_parser_check", error.__dict__)
                error.chrome_parser_check = context
                self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_all_contexts_and_scope_relations_independently_checked(self):
        error = self.refused(b"Package\tPRIVATE\n")
        token = H._chrome_parser_current_token
        good = dict(error.chrome_parser_check)
        self.assertEqual(tuple(H.CHROME_KEYWORD_CONTEXTS), tuple(Q.CHROME_KEYWORD_CONTEXTS))
        self.assertEqual(len(set(H.CHROME_KEYWORD_CONTEXTS)), 16)
        for value in H.CHROME_KEYWORD_CONTEXTS:
            for scope in ("unobserved", "active", "hidden"):
                context = {**good, "scope": scope, "keyword_context": value}
                error.__dict__.pop("chrome_parser_check", None)
                H._note_chrome_parser_check(error, context, token)
                eligible = scope == "unobserved" or value.startswith("after-active-")
                if eligible:
                    self.assertEqual(Q.chrome_parser_check_diagnostic(error), {"check": "package-header", "scope": scope,
                        "header_kind": "keyword-prefix", "keyword_context": value})
                else:
                    self.assertNotIn("chrome_parser_check", error.__dict__)
                    error.chrome_parser_check = context
                    self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_complete_six_field_annotation_fault_invalidates_only_current_token(self):
        annotate = H._annotate_chrome_parser_context
        for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            def failed(context, error, check, scope, fault=fault):
                annotate(context, error, check, scope)
                context.update(header_kind="keyword-prefix", keyword_context="before-active-horizontal-word")
                self.assertEqual(len(context), 6)
                raise fault
            with self.subTest(kind=type(fault).__name__), mock.patch.object(H, "_annotate_chrome_parser_context", side_effect=failed):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertIsNone(H._chrome_parser_current_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_complete_six_field_attachment_fault_invalidates_only_current_token(self):
        attach = H._note_chrome_parser_check
        for fault in (MemoryError("PRIVATE"), KeyboardInterrupt(), SystemExit(9)):
            def failed(error, context, token, fault=fault):
                attach(error, context, token)
                self.assertEqual(len(error.chrome_parser_check), 6)
                raise fault
            with self.subTest(kind=type(fault).__name__), mock.patch.object(H, "_note_chrome_parser_check", side_effect=failed):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertIsNone(H._chrome_parser_current_token)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_annotation_and_attachment_fault_never_invalidate_newer_token(self):
        annotate = H._annotate_chrome_parser_context
        attach = H._note_chrome_parser_check
        for stage in ("annotation", "attachment"):
            newer = object()
            def annotation(context, error, check, scope, *, newer=newer):
                annotate(context, error, check, scope)
                context.update(header_kind="keyword-prefix", keyword_context="before-active-horizontal-word")
                H._chrome_parser_current_token = newer
                raise KeyboardInterrupt()
            def attachment(error, context, token, *, newer=newer):
                attach(error, context, token)
                H._chrome_parser_current_token = newer
                raise SystemExit(9)
            name = "_annotate_chrome_parser_context" if stage == "annotation" else "_note_chrome_parser_check"
            callback = annotation if stage == "annotation" else attachment
            with self.subTest(stage=stage), mock.patch.object(H, name, side_effect=callback):
                error = self.refused(b"Package\tPRIVATE\n")
            self.assertIs(H._chrome_parser_current_token, newer)
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        error = self.refused(b"Package\tPRIVATE\n")
        context = dict(error.chrome_parser_check)
        local = H._chrome_parser_current_token
        newer = object()
        def replaced(selected, name, value):
            object.__setattr__(selected, name, value)
            if name == "chrome_parser_check":
                H._chrome_parser_current_token = newer
        with mock.patch.object(H.Refusal, "__setattr__", replaced):
            H._note_chrome_parser_check(error, context, local)
        self.assertIs(error.chrome_parser_check["attempt_token"], local)
        self.assertIs(H._chrome_parser_current_token, newer)
        self.assertIsNone(Q.chrome_parser_check_diagnostic(error))

    def test_reused_error_stale_clear_and_failed_new_attachment_cannot_publish(self):
        for stage in ("clear", "attachment"):
            old_error = self.refused(b"Package\tPRIVATE\n")
            old = old_error.chrome_parser_check
            old_token = old["attempt_token"]
            for fault in (MemoryError(), KeyboardInterrupt(), SystemExit(9)):
                with ExitStack() as stack:
                    stack.enter_context(mock.patch.object(H, "_active_chrome_package_versions", side_effect=old_error))
                    if stage == "clear":
                        stack.enter_context(mock.patch.object(H.Refusal, "__delattr__", side_effect=fault))
                    else:
                        stack.enter_context(mock.patch.object(H, "_note_chrome_parser_check", side_effect=fault))
                    error = self.refused(b"Package\tPRIVATE\n")
                self.assertIs(error, old_error)
                self.assertIsNot(H._chrome_parser_current_token, old_token)
                self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
                if stage == "clear":
                    self.assertIs(error.chrome_parser_check, old)

    def test_projector_fault_and_mid_projection_token_replacement_omit(self):
        error = self.refused(b"Package\tPRIVATE\n")
        token = H._chrome_parser_current_token
        class ChangingHost:
            Refusal = H.Refusal
            def __init__(self):
                self.reads = 0
            @property
            def _chrome_parser_current_token(self):
                self.reads += 1
                return token if self.reads == 1 else object()
        host = ChangingHost()
        with mock.patch.object(Q, "H", host):
            self.assertIsNone(Q.chrome_parser_check_diagnostic(error))
        self.assertEqual(host.reads, 2)
        for fault in (MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with mock.patch.object(Q, "chrome_parser_check_diagnostic", side_effect=fault):
                record = Q.capture_refusal_diagnostic(error, self.PHASE)
            self.assertEqual(record["refusal_code"], self.CODE)
            self.assertNotIn("chrome_parser_check", record)

    def test_nonkeyword_and_valid_inventory_never_call_context_classifier(self):
        case = ActiveChromePackageVersionTests()
        with mock.patch.object(H, "_chrome_keyword_context", side_effect=AssertionError("context")) as classifier:
            for header, kind in ChromeHeaderKindDiagnosticTests.ROWS:
                if kind == "keyword-prefix":
                    continue
                error = self.refused(header + b"\n")
                self.assertNotIn("keyword_context", self.projected(error))
            adb = case.inventory(case.dump(hidden=("98.0", "789")))
            with mock.patch.object(H.subprocess, "Popen") as native, mock.patch.object(H.socket, "create_connection") as provider:
                result = H.package_inventory(adb, "com.android.chrome")
            self.assertEqual(result["version"], "123.0")
            self.assertEqual(result["version_code"], "456")
            self.assertEqual(adb.shell.call_args_list, [mock.call(case.FIXED), mock.call("pm path com.android.chrome"),
                mock.call("sha256sum " + case.APK), mock.call("stat -c %s " + case.APK)])
            native.assert_not_called()
            provider.assert_not_called()
        classifier.assert_not_called()

    def test_wrong_phase_type_args_and_error_identity_never_project_context(self):
        error = self.refused(b"Package\tPRIVATE\n")
        good = dict(error.chrome_parser_check)
        for phase in ("sdk-observation", "owned-api36-emulator", "PRIVATE"):
            self.assertNotIn("chrome_parser_check", Q.capture_refusal_diagnostic(error, phase))
        for selected in (H.Refusal("adb-output-bound"), H.Refusal(self.CODE, "PRIVATE"), RuntimeError(self.CODE)):
            selected.chrome_parser_check = {**good, "selected_error": selected}
            self.assertIsNone(Q.chrome_parser_check_diagnostic(selected))

    def test_closed_serialization_bound_and_private_data_never_published(self):
        error = self.refused(b"Package\tPRIVATE\n")
        token = H._chrome_parser_current_token
        error.chrome_version_shape = dict.fromkeys(ChromeVersionShapeDiagnosticTests.KEYS, 2)
        good = dict(error.chrome_parser_check)
        maximum = 0
        for context in H.CHROME_KEYWORD_CONTEXTS:
            for scope in ("unobserved", "active", "hidden"):
                if scope != "unobserved" and context.startswith("before-active-"):
                    continue
                error.chrome_parser_check = {**good, "scope": scope, "keyword_context": context}
                self.assertIs(error.chrome_parser_check["attempt_token"], token)
                line = json.dumps(Q.capture_refusal_diagnostic(error, self.PHASE), ensure_ascii=True, separators=(",", ":")) + "\n"
                maximum = max(maximum, len(line.encode("ascii")))
                self.assertLessEqual(len(line.encode("ascii")), 439)
                for secret in ("attempt_token", "selected_error", "PRIVATE", "com.android.chrome", "Package"):
                    self.assertNotIn(secret, line)
        self.assertGreater(maximum, 386)
        self.assertLessEqual(maximum, 439)
        for header, _form in self.FORMS:
            selected = self.refused(header + b"\n")
            line = json.dumps(Q.capture_refusal_diagnostic(selected, self.PHASE))
            self.assertNotIn("PRIVATE", line)

    def test_actual_capture_keeps_primary_cleanup_and_publication_faults(self):
        case = ChromeVersionShapeDiagnosticTests()
        original_wire = ChromeDumpWireBudgetTests.wire
        def wire(raw):
            return original_wire(b"Package\tPRIVATE\n" if raw == b"PRIVATE\n" else raw)
        for fault in (None, MemoryError(), KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(kind=type(fault).__name__), mock.patch.object(ChromeDumpWireBudgetTests, "wire", side_effect=wire):
                error, stream = case.capture_bad_dump(publication_error=fault)
            self.assertIs(type(error), H.Refusal)
            self.assertEqual(error.args, (self.CODE,))
            self.assertIsNone(error.__context__)
            if fault is None:
                line = stream.getvalue()
                self.assertLessEqual(len(line.encode("ascii")), 512)
                self.assertEqual(json.loads(line)["chrome_parser_check"], {"check": "package-header", "scope": "unobserved",
                    "header_kind": "keyword-prefix", "keyword_context": "before-active-horizontal-word"})
                self.assertNotIn("PRIVATE", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Focused pure PR/event/workflow/NPM-order fixtures; no native/download activity."""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

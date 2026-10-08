"""Pure synthetic metadata/refusal fixtures; no native tool or package execution."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import plistlib
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "row_metadata_draft_under_test", HERE.parent / "scripts/observe_macos_previous_pkg.py"
)
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)
P = M


def package(entries, *, trailing=b"", algorithm=3):
    """Synthetic flat XAR with actual TOC, span and extracted checksum bytes."""
    checksum_name = "sha1" if algorithm == 1 else "sha256"
    digest_size = hashlib.new(checksum_name).digest_size
    tree = ET.Element("xar")
    toc = ET.SubElement(tree, "toc")
    checksum = ET.SubElement(toc, "checksum", style=checksum_name)
    ET.SubElement(checksum, "offset").text = "0"
    ET.SubElement(checksum, "size").text = str(digest_size)
    components = []
    offset = digest_size
    for entry in entries:
        name, content = entry[0:2]
        options = entry[2] if len(entry) == 3 else {}
        codec = options.get("codec", "application/octet-stream")
        stored = options.get("stored", content)
        file = ET.SubElement(toc, "file")
        ET.SubElement(file, "name").text = name
        ET.SubElement(file, "type").text = options.get("type", "file")
        data = ET.SubElement(file, "data")
        for field, value in {
            "offset": options.get("offset", offset),
            "length": len(stored),
            "size": options.get("size", len(content)),
        }.items():
            ET.SubElement(data, field).text = str(value)
        ET.SubElement(data, "encoding", style=codec)
        ET.SubElement(data, "extracted-checksum", style="sha256").text = options.get(
            "digest", M.sha(content)
        )
        components.append(stored)
        offset += len(stored)
    raw = ET.tostring(tree)
    compressed = zlib.compress(raw)
    heap = hashlib.new(checksum_name, compressed).digest() + b"".join(components) + trailing
    return (
        struct.pack("!4sHHQQI", b"xar!", 28, 1, len(compressed), len(raw), algorithm)
        + compressed
        + heap
    )


def info(**extra):
    return plistlib.dumps({"volume": "/", "install-location": "/", **extra})


@contextlib.contextmanager
def owned_fixture():
    # Sandbox fixture bytes stay under this ignored draft. Validate the resolved
    # absolute generated target immediately before stdlib recursive cleanup.
    with tempfile.TemporaryDirectory(dir=HERE, prefix="synthetic-fixture-") as directory:
        path = Path(directory)
        if path.is_symlink() or path.resolve().parent != HERE:
            raise AssertionError("fixture containment")
        try:
            yield path
        finally:
            if path.is_symlink() or path.resolve().parent != HERE:
                raise AssertionError("fixture cleanup containment")


class MetadataTests(unittest.TestCase):
    def refusal(self, callable, *args, **kwargs):
        with self.assertRaises((M.Refusal, P.Refusal)):
            callable(*args, **kwargs)

    def test_flat_xar_and_only_metadata_extraction(self):
        raw = package(
            [
                ("Bom", b"BOMStore fixture"),
                ("PackageInfo", b"<pkg-info/>"),
                ("Payload", b"opaque fixture"),
            ]
        )
        result, material = M.package_projection(raw, P)
        self.assertEqual(set(material), {"Bom", "PackageInfo"})
        self.assertEqual(result["whole_pkg_sha256"], M.sha(raw))
        self.assertEqual(result["unaccounted_heap_bytes"], 0)
        self.assertFalse(result["payload_expanded"])

    def test_sha1_toc_is_exactly_observed(self):
        result, _ = M.package_projection(package([("Payload", b"fixture")], algorithm=1), P)
        self.assertEqual(result["checksum_algorithm"], "sha1")

    def test_toc_checksum_refuses(self):
        raw = bytearray(package([("Payload", b"fixture")]))
        compressed = struct.unpack("!4sHHQQI", raw[:28])[3]
        raw[28 + compressed] ^= 1
        self.refusal(M.package_projection, bytes(raw), P)

    def test_whole_byte_bound_refuses_before_parser(self):
        with patch.object(M, "MAX_PKG", 28):
            self.refusal(M.package_projection, b"x" * 29, P)

    def test_component_overlap_refuses(self):
        self.refusal(M.package_projection, package([("Payload", b"fixture", {"offset": 0})]), P)

    def test_component_outside_heap_refuses(self):
        self.refusal(M.package_projection, package([("Payload", b"fixture", {"offset": 500})]), P)

    def test_unaccounted_tail_is_an_explicit_gap(self):
        result, _ = M.package_projection(package([("Payload", b"fixture")], trailing=b"hidden"), P)
        self.assertEqual(result["unaccounted_heap_bytes"], 6)
        self.assertFalse(result["payload_expanded"])

    def test_unknown_names_are_hashed_only(self):
        result, _ = M.package_projection(package([("fixture-private-name", b"opaque")]), P)
        self.assertNotIn("fixture-private-name", json.dumps(result))
        self.assertEqual(result["components"][0]["name_sha256"], M.sha(b"fixture-private-name"))

    def test_unknown_codec_never_becomes_decoded_material(self):
        result, material = M.package_projection(
            package([("Bom", b"opaque", {"codec": "fixture-private-codec"})]), P
        )
        self.assertFalse(material)
        self.assertEqual(result["components"][0]["data_status"], "metadata-codec-unobserved")
        self.assertNotIn("fixture-private-codec", json.dumps(result))

    def test_metadata_extracted_digest_refuses(self):
        self.refusal(
            M.package_projection,
            package([("PackageInfo", b"<pkg-info/>", {"digest": "0" * 64})]),
            P,
        )

    def test_metadata_declared_expansion_refuses_before_decode(self):
        self.refusal(
            M.package_projection, package([("PackageInfo", b"x", {"size": P.MAX_XML + 1})]), P
        )

    def test_observed_zlib_and_gzip_metadata_wrappers(self):
        raw = b"<pkg-info/>"
        gzip = zlib.compressobj(wbits=31)
        compressed_gzip = gzip.compress(raw) + gzip.flush()
        for stored in (zlib.compress(raw), compressed_gzip):
            with self.subTest(wrapper=stored[:2].hex()):
                _, material = M.package_projection(
                    package(
                        [("PackageInfo", raw, {"codec": "application/x-gzip", "stored": stored})]
                    ),
                    P,
                )
                self.assertEqual(material["PackageInfo"], raw)

    def test_compressed_metadata_tail_refuses(self):
        raw = b"<pkg-info/>"
        self.refusal(
            M.package_projection,
            package(
                [
                    (
                        "PackageInfo",
                        raw,
                        {"codec": "application/x-gzip", "stored": zlib.compress(raw) + b"tail"},
                    )
                ]
            ),
            P,
        )

    def test_component_case_alias_refuses(self):
        self.refusal(M.package_projection, package([("Payload", b"a"), ("payload", b"b")]), P)

    def test_component_count_bound_refuses(self):
        self.refusal(M.package_projection, package([(f"fixture{i}", b"a") for i in range(65)]), P)

    def test_package_info_projects_only_public_facts(self):
        raw = f'<pkg-info identifier="{M.APP_ID}" version="1.0.24" install-location="/" auth="root" private="fixture-secret"><scripts><postinstall file="fixture-secret"/></scripts></pkg-info>'.encode()
        result = M.package_info_projection(raw, P)
        self.assertTrue(result["identifier_is_expected"])
        self.assertEqual(result["script_element_count"], 2)
        self.assertEqual(result["unprojected_root_attribute_count"], 1)
        self.assertNotIn("fixture-secret", json.dumps(result))
        self.assertFalse(result["package_identity_approval"])

    def test_xml_utf16_declaration_refuses(self):
        self.refusal(
            M.package_info_projection,
            '<!DOCTYPE pkg-info [<!ENTITY x "x">]><pkg-info>&x;</pkg-info>'.encode("utf-16"),
            P,
        )

    def test_bom_requested_columns_remain_unqualified(self):
        result = M.bom_projection(f"{M.APP_REL}\t40755\t0\t80\t0\n".encode(), P)
        self.assertEqual(
            result["rows"][0]["requested_columns_as_strings"], ["40755", "0", "80", "0"]
        )
        self.assertFalse(result["native_ownership_proof"])
        self.assertEqual(result["bom_payload_agreement"], "not-checked")

    def test_bom_private_paths_are_not_retained(self):
        result = M.bom_projection(b"fixture-private-path\t100644\t0\t0\t9\n", P)
        self.assertEqual(result["unprojected_path_count"], 1)
        self.assertNotIn("fixture-private-path", json.dumps(result))

    def test_bom_alias_duplicates_refuse(self):
        self.refusal(
            M.bom_projection,
            b"Applications/Caf\xc3\xa9\t40755\t0\t0\t0\nApplications/Cafe\xcc\x81\t40755\t0\t0\t0\n",
            P,
        )

    def test_bom_unsafe_paths_or_unqualified_columns_refuse(self):
        for raw in (
            b"../x\t40755\t0\t0\t0\n",
            b"x\t40758\t0\t0\t0\n",
            b"x 40755 0 0 0\n",
            b"x\t40755\t-1\t0\t0\n",
        ):
            with self.subTest(raw=raw):
                self.refusal(M.bom_projection, raw, P)

    def test_bom_row_and_byte_bounds_refuse(self):
        with patch.object(M, "MAX_ROWS", 1):
            self.refusal(M.bom_projection, b"a\t40755\t0\t0\t0\nb\t40755\t0\t0\t0\n", P)
        with patch.object(M, "MAX_PUBLIC", 1):
            self.refusal(M.bom_projection, b"xx", P)

    def test_receipt_unknown_values_are_not_retained(self):
        result = M.receipt_projection(info(private="fixture-secret"), b"fixture-private-path\n", P)
        self.assertNotIn("fixture-secret", json.dumps(result))
        self.assertNotIn("fixture-private-path", json.dumps(result))
        self.assertFalse(result["receipt_ownership_approval"])
        self.assertEqual(result["physical_namespace_identity"], "unobserved")

    def test_receipt_app_and_data_alias_claims_are_observed_not_approved(self):
        raw = b"applications/remote ops workspace.app\nSystem/Volumes/Data/Applications/Remote Ops Workspace.app\n"
        result = M.receipt_projection(info(), raw, P)
        self.assertEqual(result["app_alias_claim_count"], 1)
        self.assertEqual(result["data_namespace_claim_count"], 1)
        self.assertFalse(result["receipt_ownership_approval"])

    def test_receipt_unicode_duplicate_refuses(self):
        self.refusal(M.receipt_projection, info(), "Caf\u00e9\nCafe\u0301\n".encode(), P)

    def test_receipt_bad_layout_or_bound_refuses(self):
        for raw in (
            plistlib.dumps({"volume": "/"}),
            plistlib.dumps({"volume": 1, "install-location": "/"}),
            info(**{"install-location": "/../escape"}),
            b"malformed",
            b"x" * 65537,
        ):
            with self.subTest(size=len(raw)):
                self.refusal(M.receipt_projection, raw, b"x\n", P)

    def test_capabilities_matching_valid_mask_only(self):
        for caps, valid, sensitive, preserving in (
            (0x300, 0x300, True, True),
            (0, 0x300, False, False),
            (0x300, 0, None, None),
            (0x300, 0x100, True, None),
        ):
            with self.subTest(valid=valid):
                result = M.capabilities_projection(
                    struct.pack("<9I", 36, caps, 0, 0, 0, valid, 0, 0, 0)
                )
                self.assertIs(result["declared_case_sensitive"], sensitive)
                self.assertIs(result["declared_case_preserving"], preserving)
                self.assertEqual(result["unicode_equivalence"], "not-empirically-observed")

    def test_capabilities_bad_length_refuses(self):
        for raw in (b"x" * 35, b"x" * 37, struct.pack("<9I", 32, *([0] * 8))):
            with self.subTest(length=len(raw)):
                self.refusal(M.capabilities_projection, raw)

    def test_installed_manual_projection_is_unqualified(self):
        raw = b"Private fixture section not retained\n f file name\n m file mode\n u user ID\n g group ID\n s file size\n"
        result = M.manual_projection(raw)
        self.assertTrue(result["all_requested_descriptions_observed"])
        self.assertFalse(result["output_schema_independently_qualified"])
        self.assertNotIn("Private fixture section", json.dumps(result))

    def test_manual_overstrike_and_missing_fields(self):
        result = M.manual_projection(b"m m\bmode\n")
        self.assertEqual(result["requested_parameter_descriptions"], {"m": "mode"})
        self.assertFalse(result["all_requested_descriptions_observed"])

    def test_manual_ambiguity_controls_or_bound_refuse(self):
        for raw in (
            b"m mode\nm changed\n",
            b"\b",
            b"\n\b",
            b"m mode\x1b",
            b"x" * (512 * 1024 + 1),
            b"\xff",
        ):
            with self.subTest(size=len(raw)):
                self.refusal(M.manual_projection, raw)

    def test_regular_file_bounds_and_identity(self):
        with owned_fixture() as directory:
            path = Path(directory) / "fixture"
            path.write_bytes(b"fixture")
            self.assertEqual(M.regular(path, 7), b"fixture")
            self.refusal(M.regular, path, 6)
            self.refusal(M.regular, Path(directory), 20)

    def test_regular_file_declared_hardlink_refuses_before_open(self):
        metadata = SimpleNamespace(st_mode=0o100644, st_nlink=2, st_size=7)
        with (
            patch.object(Path, "lstat", return_value=metadata),
            patch.object(M.os, "open", side_effect=AssertionError("must not open linked input")),
        ):
            self.refusal(M.regular, Path("synthetic-not-opened"), 20)

    def test_regular_path_ctime_change_refuses(self):
        with owned_fixture() as directory:
            path = Path(directory) / "fixture"
            path.write_bytes(b"fixture")
            before = path.lstat()
            after = SimpleNamespace(
                **{
                    key: getattr(before, key)
                    for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
                }
            )
            after.st_ctime_ns += 1
            with patch.object(Path, "lstat", side_effect=[before, after]):
                self.refusal(M.regular, path, 20)

    def test_regular_fd_identity_change_refuses(self):
        with owned_fixture() as directory:
            path = Path(directory) / "fixture"
            path.write_bytes(b"fixture")
            real_fstat = M.os.fstat
            calls = []

            def changed(fd):
                actual = real_fstat(fd)
                row = SimpleNamespace(
                    **{
                        key: getattr(actual, key)
                        for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
                    }
                )
                calls.append(fd)
                if len(calls) == 2:
                    row.st_ctime_ns += 1
                return row

            with patch.object(M.os, "fstat", side_effect=changed):
                self.refusal(M.regular, path, 20)

    def test_output_is_bounded_and_exclusive(self):
        with owned_fixture() as directory:
            path = Path(directory) / "result.json"
            M.public_save(path, {"fixture": True})
            self.assertEqual(json.loads(path.read_bytes()), {"fixture": True})
            self.refusal(M.public_save, path, {"overwrite": True})
            with patch.object(M, "MAX_PUBLIC", 1):
                self.refusal(M.public_save, Path(directory) / "oversized.json", {"too_big": True})

    def test_plan_and_disabled_run_load_no_helper(self):
        with (
            patch.object(M, "observe", side_effect=AssertionError("capture must remain disabled")),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(M.main(["plan"]), 0)
        self.assertEqual(json.loads(out.getvalue())["readiness_credit"], 0)
        with (
            patch.object(M, "observe", side_effect=AssertionError("capture must remain disabled")),
            contextlib.redirect_stderr(io.StringIO()) as error,
        ):
            self.assertEqual(M.main(["run"]), 1)
        self.assertEqual(error.getvalue().strip(), "privileged-run-disabled")

    def test_local_capture_refuses_before_any_native_or_network_activity(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                M.platform, "system", side_effect=AssertionError("platform must remain unread")
            ),
            patch.object(M.subprocess, "Popen", side_effect=AssertionError("no native child")),
            patch.object(
                M.urllib.request, "build_opener", side_effect=AssertionError("no network")
            ),
            patch.object(M.ctypes, "CDLL", side_effect=AssertionError("no native library")),
            contextlib.redirect_stderr(io.StringIO()) as error,
        ):
            self.assertEqual(M.main(["capture"]), 1)
        self.assertEqual(
            error.getvalue().strip(),
            "macos-previous-pkg-metadata-refused:official-public-hosted-event-required",
        )
        self.assertIsNone(M.REFUSAL_CONTEXT)


def event_fixture():
    values = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "macOS",
        "RUNNER_ARCH": "X64",
        "GITHUB_REPOSITORY": M.REPO,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_API_URL": "https://api.github.com",
        "ROW_EXPECTED_SOURCE_SHA": "a" * 40,
        "GITHUB_SHA": "b" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_SHA": "b" * 40,
        "GITHUB_WORKFLOW_REF": M.REPO
        + "/.github/workflows/macos-previous-pkg-metadata.yml@refs/pull/12/merge",
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REF": "refs/pull/12/merge",
    }
    repository = {"full_name": M.REPO, "private": False}
    event = {
        "repository": repository,
        "number": 12,
        "action": "synchronize",
        "pull_request": {
            "head": {"sha": "a" * 40, "repo": repository},
            "base": {"sha": "c" * 40, "ref": "main", "repo": repository},
        },
    }
    return values, json.loads(json.dumps(event))


def publication_fixture():
    pin = M.PREVIOUS
    asset = {
        "id": pin["asset_id"],
        "name": pin["asset_name"],
        "size": pin["size"],
        "digest": "sha256:" + pin["sha256"],
        "browser_download_url": pin["browser_download_url"],
        "state": "uploaded",
    }
    release = {
        "id": pin["release_id"],
        "tag_name": pin["tag"],
        "published_at": pin["published_at"],
        "draft": False,
        "prerelease": pin["prerelease"],
        "assets": [dict(asset)],
    }
    tag = {
        "ref": "refs/tags/" + pin["tag"],
        "object": {
            "sha": pin["tag_commit"],
            "type": "commit",
            "url": "https://api.github.com/repos/" + M.REPO + "/git/commits/" + pin["tag_commit"],
        },
    }
    return release, tag, asset


class FakeBudget:
    def remaining(self):
        return 100


class FakeResponse:
    def __init__(self, raw, url, headers=None):
        self.raw, self.url, self.headers, self.status = io.BytesIO(raw), url, headers or {}, 200
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read1(self, size):
        self.requests.append(size)
        return self.raw.read(size)


class IntegrationGuardTests(unittest.TestCase):
    def refusal(self, function, *args, **kwargs):
        with self.assertRaises(M.Refusal):
            function(*args, **kwargs)

    def test_same_public_pr_and_source_bound_dispatch(self):
        values, event = event_fixture()
        record = M.validate_event(values, event)
        self.assertEqual(record["source_sha"], "a" * 40)
        self.assertNotIn("ref", record)
        values.update(
            GITHUB_EVENT_NAME="workflow_dispatch",
            GITHUB_SHA="a" * 40,
            GITHUB_REF="refs/heads/codex/qualification",
        )
        values["GITHUB_WORKFLOW_REF"] = (
            M.REPO + "/.github/workflows/macos-previous-pkg-metadata.yml@" + values["GITHUB_REF"]
        )
        self.assertEqual(
            M.validate_event(values, {"repository": event["repository"]})["event"],
            "workflow_dispatch",
        )

    def test_env_run_source_and_host_claim_refusals(self):
        for key, bad in {
            "GITHUB_ACTIONS": "false",
            "RUNNER_ENVIRONMENT": "self-hosted",
            "RUNNER_OS": "Windows",
            "RUNNER_ARCH": "ARM64",
            "GITHUB_REPOSITORY": "another/repo",
            "GITHUB_SERVER_URL": "https://attacker.invalid",
            "GITHUB_API_URL": "https://attacker.invalid",
            "ROW_EXPECTED_SOURCE_SHA": "a" * 39,
            "GITHUB_SHA": "B" * 40,
            "GITHUB_RUN_ID": "0",
            "GITHUB_RUN_ATTEMPT": True,
        }.items():
            values, event = event_fixture()
            values[key] = bad
            with self.subTest(key=key):
                self.refusal(M.validate_event, values, event)
        values, event = event_fixture()
        values["GITHUB_WORKFLOW_REF"] = M.REPO + "/.github/workflows/another.yml@refs/pull/12/merge"
        self.refusal(M.validate_event, values, event)
        values, event = event_fixture()
        values["GITHUB_WORKFLOW_SHA"] = "not-a-commit"
        self.refusal(M.validate_event, values, event)

    def test_private_fork_malformed_pr_source_and_ref_refuse(self):
        variants = [
            lambda e: e["repository"].update(private=True),
            lambda e: e.update(action="closed"),
            lambda e: e.update(number=True),
            lambda e: e["pull_request"]["head"]["repo"].update(full_name="attacker/fork"),
            lambda e: e["pull_request"]["head"].update(sha="d" * 40),
            lambda e: e["pull_request"]["base"].update(ref="production"),
            lambda e: e["pull_request"].update(head=[]),
            lambda e: e["pull_request"]["base"]["repo"].update(private=True),
        ]
        for index, mutate in enumerate(variants):
            values, event = event_fixture()
            mutate(event)
            with self.subTest(index=index):
                self.refusal(M.validate_event, values, event)
        values, event = event_fixture()
        values["GITHUB_REF"] = "refs/pull/12/head"
        self.refusal(M.validate_event, values, event)

    def test_dispatch_mismatch_and_aliases_refuse(self):
        values, event = event_fixture()
        values.update(GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_SHA="a" * 40)
        for ref in (
            "refs/tags/v1",
            "refs/heads/a/../b",
            "refs/heads/a//b",
            "refs/heads/a/",
            "refs/heads/a.",
        ):
            with self.subTest(ref=ref):
                self.refusal(
                    M.validate_event,
                    {**values, "GITHUB_REF": ref},
                    {"repository": event["repository"]},
                )
        values.update(GITHUB_REF="refs/heads/main", GITHUB_SHA="d" * 40)
        self.refusal(M.validate_event, values, {"repository": event["repository"]})

    def test_strict_json_duplicate_layout_and_bounds(self):
        self.assertEqual(M.strict_json(b'{"id":1}'), {"id": 1})
        for raw in (b'{"id":1,"id":2}', b'{"outer":{"id":1,"id":2}}', b"\xff", b"not-json"):
            self.refusal(M.strict_json, raw)
        self.refusal(M.strict_json, b"{}", 1)

    def test_readonly_command_allowlist_never_installer_or_app(self):
        private = Path("synthetic-private")
        self.assertTrue(
            M.command_allowed(["/usr/bin/lsbom", "-p", "fmugs", str(private / "Bom")], private)
        )
        self.assertTrue(
            M.command_allowed(["/usr/sbin/pkgutil", "--files", "io.example.package"], private)
        )
        for command in (
            ["/usr/sbin/installer", "-pkg", "old.pkg", "-target", "/"],
            ["/usr/bin/sudo", "true"],
            ["/usr/bin/open", "app"],
            ["/usr/sbin/pkgutil", "--forget", "io.example"],
            ["/usr/sbin/pkgutil", "--files", "--pkgs"],
            ["/usr/bin/git", "checkout", "main"],
            ["/usr/bin/lsbom", "-p", "fmugs", "unowned/Bom"],
            [True],
        ):
            with self.subTest(command=command):
                self.assertFalse(M.command_allowed(command, None))

    def test_command_bound_refuses_before_popen(self):
        commands = M.MetadataCommands()
        with patch.object(M.subprocess, "Popen", side_effect=AssertionError("no child")):
            self.refusal(commands.capture, ["/usr/sbin/installer"])
            self.refusal(
                commands.capture, ["/usr/sbin/pkgutil", "--pkgs"], environment={"TOKEN": "secret"}
            )
            commands.calls = [{}] * 4050
            self.refusal(commands.capture, ["/usr/sbin/pkgutil", "--pkgs"])

    def test_first_owned_git_timeout_cleans_retained_leader_before_source_binding(self):
        # No native child exists: checked fixture helper and fake Popen methods
        # prove bootstrap loading, leader-only termination/wait and refusal.
        with owned_fixture() as directory:
            helper = directory / "src/remote_ops_workspace/process_status.py"
            helper.parent.mkdir(parents=True)
            raw = b"def terminate_owned_process(process, timeout_seconds=5):\n    process.terminate()\n    process.wait(timeout=timeout_seconds)\n"
            helper.write_bytes(raw)
            clock = SimpleNamespace(value=0.0)

            class Child:
                def __init__(self):
                    self.stdout, self.stderr, self.stdin = io.BytesIO(), io.BytesIO(), None
                    self.returncode, self.terminated, self.wait_calls = None, False, []

                def wait(self, timeout):
                    self.wait_calls.append(timeout)
                    if self.terminated:
                        self.returncode = -15
                        return -15
                    clock.value = 0.02
                    raise M.subprocess.TimeoutExpired("fixed-owned-git", timeout)

                def terminate(self):
                    self.terminated = True

            child = Child()
            with (
                patch.object(M, "ROOT", directory),
                patch.object(M, "SOURCE_BINDING", None),
                patch.object(M, "BOOTSTRAP_CLEANUP_SHA", M.sha(raw)),
                patch.object(M, "time", SimpleNamespace(monotonic=lambda: clock.value)),
                patch.object(M.subprocess, "Popen", return_value=child),
            ):
                commands = M.MetadataCommands()
                with self.assertRaisesRegex(M.Refusal, "command-timeout"):
                    commands.capture(["/usr/bin/git", "rev-parse", "HEAD"], timeout=0.01)
            self.assertTrue(child.terminated)
            self.assertEqual(child.wait_calls, [0.01, 5])
            self.assertEqual(child.returncode, -15)
            self.assertTrue(commands.uncertain)
            self.assertTrue(commands.calls[0]["leader_cleanup_attempted"])
            self.assertIsNone(commands.calls[0]["leader_cleanup_error_type"])
            self.assertEqual(commands.calls[0]["process_tree_cleanup"], "not-proven")

    def test_bootstrap_helper_modified_bytes_refuse_import(self):
        with owned_fixture() as directory:
            helper = directory / "src/remote_ops_workspace/process_status.py"
            helper.parent.mkdir(parents=True)
            helper.write_bytes(b"raise AssertionError('changed source must not execute')\n")
            with (
                patch.object(M, "ROOT", directory),
                patch.object(M, "SOURCE_BINDING", None),
                patch.object(M, "BOOTSTRAP_CLEANUP_SHA", "0" * 64),
            ):
                self.refusal(M.load_module, helper, "changed-bootstrap-must-not-import")

    def test_redirects_pins_credentials_and_wrong_hosts(self):
        api = "https://api.github.com/repos/" + M.REPO + "/releases/382583184"
        self.assertTrue(M.redirect_allowed(api, False))
        self.assertTrue(M.redirect_allowed(M.PREVIOUS["browser_download_url"], True))
        self.assertTrue(
            M.redirect_allowed(
                "https://release-assets.githubusercontent.com/github-production-release-asset/1/2?sig=public-fixture",
                True,
            )
        )
        for url in (
            "http://api.github.com/repos/" + M.REPO + "/releases/1",
            api + "?token=secret",
            api + "#anchor",
            api.replace("api.github.com", "user:secret@api.github.com"),
            api.replace("api.github.com", "api.github.com.attacker.invalid"),
            api.replace("api.github.com", "api.github.com:not-a-port"),
            "https://api.github.com/repos/another/repo/releases/1",
        ):
            with self.subTest(url=url):
                self.assertFalse(M.redirect_allowed(url, False))
        self.assertFalse(
            M.redirect_allowed("https://github.com/other/repo/releases/download/v1/file.pkg", True)
        )
        self.assertFalse(
            M.redirect_allowed("https://release-assets.githubusercontent.com/other/path", True)
        )
        redirects = M.RestrictedRedirect(False)
        self.refusal(
            redirects.redirect_request, None, None, 302, "", {}, M.PREVIOUS["browser_download_url"]
        )

    def test_network_bounded_chunks_exact_asset_and_no_auth(self):
        with owned_fixture() as directory:
            destination = directory / "pinned.pkg"
            response = FakeResponse(
                b"fixture", M.PREVIOUS["browser_download_url"], {"Content-Length": "7"}
            )
            opener = SimpleNamespace(open=lambda request, timeout, fixture=response: fixture)
            with patch.object(M.urllib.request, "build_opener", return_value=opener):
                raw, facts = M.fetch(
                    M.PREVIOUS["browser_download_url"], 7, FakeBudget(), destination
                )
            self.assertEqual(raw, b"")
            self.assertEqual(destination.read_bytes(), b"fixture")
            self.assertEqual(facts["sha256"], M.sha(b"fixture"))
            self.assertFalse(facts["authenticated_request"])
            self.assertLessEqual(max(response.requests), 8)

    def test_network_wrong_encoding_length_status_and_overrun_refuse(self):
        api = "https://api.github.com/repos/" + M.REPO + "/releases/382583184"
        for raw, headers, status in (
            (b"fixture!", {}, 200),
            (b"fixture", {"Content-Encoding": "gzip"}, 200),
            (b"fixture", {"Content-Length": "8"}, 200),
            (b"fixture", {}, 206),
        ):
            response = FakeResponse(raw, api, headers)
            response.status = status
            opener = SimpleNamespace(open=lambda request, timeout, fixture=response: fixture)
            with (
                self.subTest(size=len(raw), status=status),
                patch.object(M.urllib.request, "build_opener", return_value=opener),
            ):
                self.refusal(M.fetch, api, 7, FakeBudget())

    def test_network_late_return_remains_refusal(self):
        api = "https://api.github.com/repos/" + M.REPO + "/releases/382583184"
        response = FakeResponse(b"fixture", api)
        budget = SimpleNamespace(
            remaining=unittest.mock.Mock(
                side_effect=[100, 100, M.Refusal("metadata-overall-deadline")]
            )
        )
        with patch.object(
            M.urllib.request,
            "build_opener",
            return_value=SimpleNamespace(open=lambda request, timeout: response),
        ):
            self.refusal(M.fetch, api, 7, budget)

    def test_publication_all_exact_pins_and_types(self):
        release, tag, asset = publication_fixture()
        self.assertEqual(
            M.validate_previous_identity(release, tag, asset)["sha256"], M.PREVIOUS["sha256"]
        )
        for index, field, value in (
            (0, "id", True),
            (0, "draft", True),
            (0, "prerelease", False),
            (0, "published_at", "changed"),
            (0, "assets", []),
            (0, "assets", {}),
            (1, "ref", "refs/tags/v9"),
            (1, "object", {}),
            (2, "id", 1),
            (2, "size", True),
            (2, "digest", "sha256:" + "0" * 64),
            (2, "browser_download_url", "https://attacker.invalid/file"),
            (2, "state", "new"),
        ):
            fixtures = list(publication_fixture())
            fixtures[index][field] = value
            with self.subTest(index=index, field=field):
                self.refusal(M.validate_previous_identity, *fixtures)
        release["assets"].append(dict(asset))
        self.refusal(M.validate_previous_identity, release, tag, asset)

    def test_pinned_prerelease_is_literal_true_and_returned(self):
        self.assertIs(M.PREVIOUS["prerelease"], True)
        release, tag, asset = publication_fixture()
        identity = M.validate_previous_identity(release, tag, asset)
        self.assertIs(identity["prerelease"], True)
        for value in (False, None, "true", "True", 1, 0, 1.0, [], {}):
            release, tag, asset = publication_fixture()
            release["prerelease"] = value
            with self.subTest(value_type=type(value).__name__, value=value):
                self.refusal(M.validate_previous_identity, release, tag, asset)
        release, tag, asset = publication_fixture()
        del release["prerelease"]
        self.refusal(M.validate_previous_identity, release, tag, asset)

    def test_prerelease_flag_drift_refuses_before_and_after_readback(self):
        release, tag, asset = publication_fixture()
        identity = M.validate_previous_identity(release, tag, asset)
        before = {**identity, "metadata_sha256": ["a" * 64] * 3}
        after = {**identity, "metadata_sha256": ["b" * 64] * 3}
        self.assertTrue(M.publication_recheck(before, after)["immutable_identity_equal"])
        for side in (0, 1):
            for value in (False, None, "true", 1, 0):
                observations = [dict(before), dict(after)]
                observations[side]["prerelease"] = value
                with self.subTest(side=side, value_type=type(value).__name__, value=value):
                    self.refusal(M.publication_recheck, *observations)
            observations = [dict(before), dict(after)]
            del observations[side]["prerelease"]
            self.refusal(M.publication_recheck, *observations)

    def test_mutable_public_download_count_does_not_weaken_identity_readback(self):
        release, tag, asset = publication_fixture()
        before = {
            **M.validate_previous_identity(release, tag, asset),
            "metadata_sha256": ["a" * 64] * 3,
        }
        release["download_count"], asset["download_count"] = 1, 2
        after = {
            **M.validate_previous_identity(release, tag, asset),
            "metadata_sha256": ["b" * 64] * 3,
        }
        result = M.publication_recheck(before, after)
        self.assertTrue(result["immutable_identity_equal"])
        self.assertNotEqual(result["before_metadata_sha256"], result["after_metadata_sha256"])
        self.refusal(M.publication_recheck, before, {**after, "sha256": "0" * 64})

    def test_executed_workflow_bytes_bound_without_equating_head_and_merge(self):
        values, event = event_fixture()
        run = M.validate_event(values, event)
        raw = b"public workflow fixture"
        source = {"head": run["source_sha"], "contracts": {run["workflow_path"]: M.sha(raw)}}
        facts = {"size": len(raw), "sha256": M.sha(raw)}
        self.assertNotEqual(run["workflow_sha"], run["source_sha"])
        with patch.object(M, "fetch", return_value=(raw, facts)) as fetch:
            self.assertEqual(M.executed_workflow_binding(FakeBudget(), source, run), facts)
        url = fetch.call_args.args[0]
        self.assertIn("/" + run["workflow_sha"] + "/", url)
        self.assertTrue(M.redirect_allowed(url, False))
        with patch.object(M, "fetch", return_value=(b"another workflow", {})):
            self.refusal(M.executed_workflow_binding, FakeBudget(), source, run)

    def test_source_bytes_contracts_clean_state_and_empty_typing_marker(self):
        with owned_fixture() as directory:
            files = [*M.CONTRACTS, "src/remote_ops_workspace/py.typed"]
            for name in files:
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"" if name.endswith("py.typed") else name.encode())
            table = {
                ("rev-parse", "HEAD"): b"a" * 40 + b"\n",
                ("rev-parse", "HEAD^{tree}"): b"c" * 40 + b"\n",
                ("config", "--get", "remote.origin.url"): (
                    "https://github.com/" + M.REPO + ".git\n"
                ).encode(),
                ("status", "--porcelain", "--untracked-files=no"): b"",
                ("ls-files", "-z"): ("\0".join(files) + "\0").encode(),
            }
            commands = SimpleNamespace(
                capture=lambda command, **_kw: table[tuple(command[1:])], remaining=lambda: 100
            )
            result = M.source_binding(directory, commands, "a" * 40)
            self.assertEqual(result["tracked_file_count"], 5)
            self.assertEqual(set(result["contracts"]), set(M.CONTRACTS))
            (directory / files[0]).write_bytes(b"changed")
            self.assertNotEqual(M.source_binding(directory, commands, "a" * 40), result)
            self.refusal(M.source_binding, directory, commands, "d" * 40)
            table[("status", "--porcelain", "--untracked-files=no")] = b" M source.py\n"
            self.refusal(M.source_binding, directory, commands, "a" * 40)

    def test_source_path_alias_missing_contract_and_aggregate_bounds(self):
        with owned_fixture() as directory:
            files = list(M.CONTRACTS)
            for name in files:
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            table = {
                ("rev-parse", "HEAD"): b"a" * 40,
                ("rev-parse", "HEAD^{tree}"): b"c" * 40,
                ("config", "--get", "remote.origin.url"): ("https://github.com/" + M.REPO).encode(),
                ("status", "--porcelain", "--untracked-files=no"): b"",
            }
            commands = SimpleNamespace(
                capture=lambda command, **_kw: table[tuple(command[1:])], remaining=lambda: 100
            )
            for names in (
                files[:-1],
                files + [files[0]],
                files + ["../escape"],
                files + ["./alias"],
            ):
                table[("ls-files", "-z")] = ("\0".join(names) + "\0").encode()
                self.refusal(M.source_binding, directory, commands, "a" * 40)
            table[("ls-files", "-z")] = ("\0".join(files) + "\0").encode()
            with patch.object(M, "MAX_SOURCE_TOTAL", 1):
                self.refusal(M.source_binding, directory, commands, "a" * 40)

    def test_regular_tiny_read_is_observed_size_plus_one_and_empty_only_explicit(self):
        with owned_fixture() as directory:
            path = directory / "tiny"
            path.write_bytes(b"x")
            real_fdopen = M.os.fdopen
            sizes = []

            class Reader:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    self.stream.close()

                def fileno(self):
                    return self.stream.fileno()

                def read(self, size):
                    sizes.append(size)
                    if size != 2:
                        raise AssertionError("allocation is not source-size bounded")
                    return self.stream.read(size)

            with patch.object(
                M.os, "fdopen", side_effect=lambda fd, mode: Reader(real_fdopen(fd, mode))
            ):
                self.assertEqual(M.regular(path, 150 * 1024 * 1024), b"x")
            self.assertEqual(sizes, [2])
            path.write_bytes(b"")
            self.refusal(M.regular, path, 10)
            self.assertEqual(M.regular(path, 10, allow_empty=True), b"")

    def test_regular_oversize_refuses_before_open(self):
        with owned_fixture() as directory:
            path = directory / "oversized"
            path.write_bytes(b"oversized")
            with patch.object(M.os, "open", side_effect=AssertionError("must not open")):
                self.refusal(M.regular, path, 1)

    def test_regular_growth_shrink_and_same_size_changes_refuse(self):
        with owned_fixture() as directory:
            path = directory / "changing"
            real_fdopen = M.os.fdopen
            for new_bytes in (b"longer", b"x", b"changed"):
                path.write_bytes(b"fixture")
                replacement = new_bytes

                class Reader:
                    def __init__(self, stream):
                        self.stream = stream

                    def __enter__(self):
                        return self

                    def __exit__(self, *_args):
                        self.stream.close()

                    def fileno(self):
                        return self.stream.fileno()

                    def read(self, size, content=replacement):
                        before = path.stat()
                        path.write_bytes(content)
                        # Deterministic identity change; NTFS can defer its
                        # automatic timestamp update until all handles close.
                        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000000))
                        return self.stream.read(size)

                with (
                    self.subTest(size=len(new_bytes)),
                    patch.object(
                        M.os, "fdopen", side_effect=lambda fd, mode: Reader(real_fdopen(fd, mode))
                    ),
                ):
                    self.refusal(M.regular, path, 10)

    def test_xml_construction_limits_and_all_declarations_remain_refusals(self):
        for raw in (
            b'<!DOCTYPE x [<!ENTITY y "z">]><x>&y;</x>',
            '<!DOCTYPE x [<!ENTITY y "z">]><x>&y;</x>'.encode("utf-16"),
            b"<x><!--hidden--></x>",
            b"<x><?hidden value?></x>",
        ):
            self.refusal(M.public_xml, raw)
        with patch.object(M, "MAX_NODES", 1):
            self.refusal(M.public_xml, b"<x><y/></x>")
        with patch.object(M, "MAX_XML_TEXT", 1):
            self.refusal(M.public_xml, b"<x>too long</x>")
        with patch.object(M, "MAX_XML_DEPTH", 0):
            self.refusal(M.public_xml, b"<x><y/></x>")

    def test_failure_receipt_safe_phase_exact_identity_nonzero_and_no_metadata(self):
        with owned_fixture() as directory:
            output = directory / "runner-output"
            output.write_bytes(b"")
            source = {
                "head": "a" * 40,
                "tree": "c" * 40,
                "checkout_bytes_sha256": "d" * 64,
                "contracts": {},
            }
            run = {"source_sha": "a" * 40, "run_id": "123", "run_attempt": "1"}

            def fail(_root):
                M.diagnostic_phase(
                    "installed-bom-reader",
                    bom_output_sha256=M.sha(b"raw-private-bom-value"),
                    receipt_files_sha256="raw-private-url",
                    argv="raw-private-argv",
                    receipt_namespace_count=2,
                )
                raise M.Refusal("bom-requested-column-layout-unobserved")

            context = {"source": source, "run": run, "phase": "previous-toc", "observed": {}}
            with (
                patch.object(M, "ROOT", directory),
                patch.object(M, "SOURCE_BINDING", source),
                patch.object(M, "REFUSAL_CONTEXT", context),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}),
                patch.object(M, "observe", side_effect=fail),
                contextlib.redirect_stderr(io.StringIO()) as stderr,
            ):
                self.assertEqual(M.main(["capture"]), 1)
                data = (directory / M.REPORT).read_bytes()
            receipt = json.loads(data)
            self.assertEqual(receipt["status"], "refused")
            self.assertEqual(receipt["phase"], "installed-bom-reader")
            self.assertEqual(receipt["source"], source)
            self.assertEqual(receipt["reason_code"], "bom-requested-column-layout-unobserved")
            self.assertFalse(receipt["approval"])
            self.assertEqual(receipt["source_unchanged"], "not-established")
            self.assertNotIn(b"raw-private", data)
            self.assertNotIn(b"argv", data)
            self.assertEqual(output.read_bytes(), b"public_receipt=saved\n")
            self.assertEqual(
                stderr.getvalue().strip(),
                "macos-previous-pkg-metadata-refused:bom-requested-column-layout-unobserved",
            )

    def test_unknown_failure_and_unbound_refusal_cannot_claim_a_safe_receipt(self):
        with (
            patch.object(M, "SOURCE_BINDING", None),
            patch.object(M, "REFUSAL_CONTEXT", None),
            patch.object(M, "public_save", side_effect=AssertionError("no unbound output")),
            patch.object(M, "observe", side_effect=M.Refusal("raw-private-url")),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(M.main(["capture"]), 1)
        self.assertEqual(
            stderr.getvalue().strip(),
            "macos-previous-pkg-metadata-refused:metadata-input-or-runtime-refusal",
        )

    def test_unowned_directory_and_existing_output_refuse(self):
        with owned_fixture() as directory:
            self.refusal(M.safe_directory, directory.parent, directory)
            self.refusal(M.safe_directory, directory / ".." / "escape", directory)
            target = directory / "report.json"
            target.write_bytes(b"private preexisting bytes")
            with (
                patch.object(M, "ROOT", directory),
                patch.object(M, "REPORT", "report.json"),
                patch.object(M, "SOURCE_BINDING", {}),
                patch.object(
                    M,
                    "REFUSAL_CONTEXT",
                    {"source": {}, "run": {}, "phase": "public-output", "observed": {}},
                ),
                patch.object(
                    M,
                    "emit_receipt_marker",
                    side_effect=AssertionError("must not mark existing file"),
                ),
            ):
                self.refusal(M.public_refusal, "public-output-bound-or-existing")
            self.assertEqual(target.read_bytes(), b"private preexisting bytes")


class SystemToolReaderTests(unittest.TestCase):
    def fixture(self, **changes):
        values = {
            "st_dev": 3, "st_ino": 9, "st_mode": M.stat.S_IFREG | 0o555,
            "st_uid": 0, "st_gid": 0, "st_nlink": 78, "st_size": 3,
            "st_mtime_ns": 11, "st_ctime_ns": 12, "st_flags": 0,
        }
        values.update(changes)
        state = SimpleNamespace(
            before=SimpleNamespace(**values),
            opened=SimpleNamespace(**values),
            after=SimpleNamespace(**values),
            after_path=SimpleNamespace(**values),
            raw=b"abc", paths=[], open_calls=[], read_requests=[], closed=False,
            closed_fds=[], read_error=None, fdopen_error=None, path_calls=0,
        )

        class FakePath:
            def __init__(self, value):
                state.paths.append(value)
                self.value = value

            def lstat(self):
                state.path_calls += 1
                return state.before if state.path_calls == 1 else state.after_path

            def __str__(self):
                return self.value

        class Stream:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                state.closed = True

            def fileno(self):
                return 97

            def read(self, maximum):
                state.read_requests.append(maximum)
                if state.read_error is not None:
                    raise state.read_error
                return state.raw

        stats = iter((state.opened, state.after))

        def opened(path, flags):
            state.open_calls.append((str(path), flags))
            return 97

        def fdopen(fd, mode):
            self.assertEqual((fd, mode), (97, "rb"))
            if state.fdopen_error is not None:
                raise state.fdopen_error
            return Stream()

        def fstat(fd):
            self.assertEqual(fd, 97)
            return next(stats)

        state.path = FakePath
        state.os = SimpleNamespace(
            O_RDONLY=0, O_NOFOLLOW=256, open=opened, fdopen=fdopen, fstat=fstat,
            close=lambda fd: state.closed_fds.append(fd),
        )
        return state

    def read(self, state, index=0):
        with patch.object(M, "Path", state.path), patch.object(M, "os", state.os):
            return M.readonly_system_tool_bytes(index)

    def test_fixed_paths_allow_stable_root_owned_system_hardlinks(self):
        expected = ("/usr/bin/git", "/usr/bin/man", "/bin/cat", "/usr/bin/lsbom", "/usr/sbin/pkgutil")
        self.assertEqual(M.READONLY_SYSTEM_TOOLS, expected)
        for index, path in enumerate(expected):
            for nlink in (1, 78):
                with self.subTest(index=index, nlink=nlink):
                    state = self.fixture(st_nlink=nlink)
                    self.assertEqual(self.read(state, index), b"abc")
                    self.assertEqual(state.paths, [path])
                    self.assertEqual(state.open_calls, [(path, 256)])
                    self.assertEqual(state.read_requests, [4])
                    self.assertTrue(state.closed)
                    self.assertEqual(state.path_calls, 2)

    def test_index_and_nofollow_guards_refuse_before_path_or_open(self):
        for index in (-1, 5, True, False, "0", None):
            with self.subTest(index=index):
                state = self.fixture()
                with self.assertRaisesRegex(M.Refusal, "^system-tool-index-refused$"):
                    self.read(state, index)
                self.assertEqual(state.paths, [])
                self.assertEqual(state.open_calls, [])
        for flag in (0, None, True):
            with self.subTest(flag=flag):
                state = self.fixture()
                state.os.O_NOFOLLOW = flag
                with self.assertRaisesRegex(M.Refusal, "^system-tool-nofollow-unavailable$"):
                    self.read(state)
                self.assertEqual(state.paths, [])
                self.assertEqual(state.open_calls, [])
        state = self.fixture()
        del state.os.O_NOFOLLOW
        with self.assertRaisesRegex(M.Refusal, "^system-tool-nofollow-unavailable$"):
            self.read(state)
        self.assertEqual(state.paths, [])

    def test_type_owner_permissions_and_byte_bounds_refuse_before_open(self):
        cases = (
            {"st_mode": M.stat.S_IFLNK | 0o555}, {"st_mode": M.stat.S_IFDIR | 0o555},
            {"st_mode": M.stat.S_IFREG | 0o575}, {"st_mode": M.stat.S_IFREG | 0o557},
            {"st_mode": True}, {"st_uid": 1}, {"st_uid": False},
            {"st_gid": -1}, {"st_gid": 1 << 32}, {"st_gid": False},
            {"st_nlink": 0}, {"st_nlink": M.MAX_ROWS + 1}, {"st_nlink": True},
            {"st_size": 0}, {"st_size": 16 * 1024 * 1024 + 1}, {"st_size": True},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                state = self.fixture(**changes)
                with self.assertRaisesRegex(M.Refusal, "^system-tool-bound-type-or-ownership-refused$"):
                    self.read(state)
                self.assertEqual(state.open_calls, [])
                self.assertEqual(state.read_requests, [])

    def test_each_full_identity_field_is_bound_before_read_and_after_fd_path(self):
        changes = {
            "st_dev": 4, "st_ino": 10, "st_mode": M.stat.S_IFREG | 0o554,
            "st_uid": 1, "st_gid": 1, "st_nlink": 79, "st_size": 4,
            "st_mtime_ns": 12, "st_ctime_ns": 13, "st_flags": 1,
        }
        for stage in ("opened", "after", "after_path"):
            for field, value in changes.items():
                with self.subTest(stage=stage, field=field):
                    state = self.fixture()
                    setattr(getattr(state, stage), field, value)
                    with self.assertRaisesRegex(M.Refusal, "^input-changed-during-read$"):
                        self.read(state)
                    self.assertTrue(state.closed)
                    self.assertEqual(state.read_requests, [] if stage == "opened" else [4])

    def test_growing_and_shrinking_bytes_refuse_with_only_one_sentinel(self):
        for raw in (b"ab", b"abcd"):
            with self.subTest(size=len(raw)):
                state = self.fixture()
                state.raw = raw
                with self.assertRaisesRegex(M.Refusal, "^input-changed-during-read$"):
                    self.read(state)
                self.assertEqual(state.read_requests, [4])
                self.assertTrue(state.closed)

    def test_fdopen_and_read_errors_keep_failure_and_close_owned_fd(self):
        state = self.fixture()
        state.fdopen_error = OSError("synthetic fdopen failure")
        with self.assertRaises(OSError):
            self.read(state)
        self.assertEqual(state.closed_fds, [97])
        self.assertEqual(state.read_requests, [])
        state = self.fixture()
        state.read_error = OSError("synthetic read failure")
        with self.assertRaises(OSError):
            self.read(state)
        self.assertTrue(state.closed)
        self.assertEqual(state.closed_fds, [])

    def test_shared_regular_reader_keeps_single_link_guard(self):
        state = self.fixture(st_nlink=78)
        with patch.object(M, "os", state.os):
            with self.assertRaisesRegex(M.Refusal, "^regular-input-bound-or-link$"):
                M.regular(state.path("owned-synthetic-input"), 16 * 1024 * 1024)
        self.assertEqual(state.open_calls, [])


class StrictUtf8ManualTests(unittest.TestCase):
    def test_utf8_documentation_keeps_ascii_projection_without_raw_text(self):
        preamble = "Synthetic café documentation — “quoted” ©\n"
        fields = " f file name\n m file mode\n u user ID\n g group ID\n s file size\n"
        raw = (preamble + fields).encode("utf-8")
        result = M.manual_projection(raw)
        self.assertEqual(result["raw_sha256"], M.sha(raw))
        self.assertEqual(result["requested_parameter_descriptions"], {
            "f": "file name", "m": "file mode", "u": "user ID", "g": "group ID", "s": "file size",
        })
        self.assertTrue(result["all_requested_descriptions_observed"])
        self.assertFalse(result["output_schema_independently_qualified"])
        self.assertNotIn("café", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("quoted", json.dumps(result))

    def test_unicode_whitespace_and_descriptions_do_not_expand_ascii_field_grammar(self):
        for line in ("\u00a0m mode", "m café", "m mode\u00a0", "\u2003m mode", "m mode\u2003"):
            with self.subTest(line_kind=M.sha(line.encode())):
                result = M.manual_projection((line + "\n").encode("utf-8"))
                self.assertEqual(result["requested_parameter_descriptions"], {})
                self.assertFalse(result["all_requested_descriptions_observed"])

    def test_utf8_preamble_retains_ascii_overstrike_and_formatting(self):
        raw = "Synthetic café — manual\n\tf f\bfile name\r\nm m\bmode\f".encode()
        result = M.manual_projection(raw)
        self.assertEqual(result["requested_parameter_descriptions"], {"f": "file name", "m": "mode"})
        self.assertFalse(result["all_requested_descriptions_observed"])

    def test_duplicate_ascii_fields_still_refuse_after_utf8_preamble(self):
        raw = "Synthetic café\nm mode\nm changed\n".encode()
        with self.assertRaisesRegex(M.Refusal, "^installed-manual-field-ambiguity$"):
            M.manual_projection(raw)

    def test_invalid_utf8_remains_refused_with_only_bounded_decoder_facts(self):
        for raw in (b"\xff", b"\xc2", b"ok \xe2\x82", b"\xc0\xaf", b"\xed\xa0\x80", b"\xff\xfe"):
            context = {"phase": "installed-lsbom-manual", "observed": {}}
            with self.subTest(raw_digest=M.sha(raw)), patch.object(M, "REFUSAL_CONTEXT", context):
                with self.assertRaisesRegex(M.Refusal, "^installed-manual-encoding-unobserved$"):
                    M.manual_projection(raw)
                facts = context["observed"]
                self.assertEqual(set(facts), {"manual_raw_sha256", "manual_size_bytes", "manual_decoder", "manual_utf8_valid", "manual_decode_error_offset", "manual_decode_error_width"})
                self.assertEqual(facts["manual_raw_sha256"], M.sha(raw))
                self.assertEqual(facts["manual_size_bytes"], len(raw))
                self.assertEqual(facts["manual_decoder"], "strict-utf8")
                self.assertIs(facts["manual_utf8_valid"], False)
                self.assertTrue(0 <= facts["manual_decode_error_offset"] < len(raw))
                self.assertTrue(1 <= facts["manual_decode_error_width"] <= 4)
                self.assertLess(len(json.dumps(facts)), 400)

    def test_unicode_controls_formats_and_separators_refuse_before_overstrike(self):
        controls = "\u0085\u00ad\u061c\u200b\u200e\u200f\u2028\u2029\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff"
        for char in controls:
            for suffix in ("", "\b"):
                with self.subTest(codepoint=ord(char), overstrike=bool(suffix)):
                    raw = ("Synthetic manual\nm mode\n" + char + suffix).encode("utf-8")
                    with self.assertRaisesRegex(M.Refusal, "^installed-manual-controls$"):
                        M.manual_projection(raw)

    def test_decoder_diagnostics_are_phase_scoped_typed_bounded_and_text_free(self):
        context = {"phase": "installed-lsbom-manual", "observed": {}}
        with patch.object(M, "REFUSAL_CONTEXT", context):
            M.diagnostic_phase("installed-bom-reader", manual_raw_sha256="a" * 64, manual_decoder="strict-utf8")
            self.assertEqual(context["observed"], {})
            M.diagnostic_phase("installed-lsbom-manual", manual_raw_sha256="private raw manual",
                manual_size_bytes=True, manual_decoder="private/encoding/path", manual_utf8_valid=1,
                manual_decode_error_offset=-1, manual_decode_error_width=0, raw_text="private raw manual",
                argv="private args", exception_message="private message")
            self.assertEqual(context["observed"], {})
            M.diagnostic_phase("installed-lsbom-manual", manual_raw_sha256="a" * 64,
                manual_size_bytes=512 * 1024, manual_decoder="strict-utf8", manual_utf8_valid=False,
                manual_decode_error_offset=512 * 1024 - 1, manual_decode_error_width=1)
            self.assertEqual(len(context["observed"]), 6)
            M.manual_projection("Synthetic café\nm mode\n".encode())
            self.assertIs(context["observed"]["manual_utf8_valid"], True)
            self.assertNotIn("manual_decode_error_offset", context["observed"])
            self.assertNotIn("manual_decode_error_width", context["observed"])
            self.assertNotIn("café", json.dumps(context["observed"], ensure_ascii=False))
            for invalid in ({"manual_size_bytes": 512 * 1024 + 1}, {"manual_size_bytes": -1},
                {"manual_decode_error_offset": True}, {"manual_decode_error_offset": 512 * 1024 + 1},
                {"manual_decode_error_width": 5}, {"manual_decode_error_width": False}):
                M.diagnostic_phase("installed-lsbom-manual", **invalid)
                self.assertEqual(context["observed"], {})

    def test_manual_byte_bound_precedes_decoding_and_diagnostics(self):
        with patch.object(M, "diagnostic_phase", side_effect=AssertionError("no oversized diagnostics")):
            with self.assertRaisesRegex(M.Refusal, "^installed-manual-bound$"):
                M.manual_projection(b"x" * (512 * 1024 + 1))
        raw = b"\xc3\xa9" * (256 * 1024)
        self.assertEqual(len(raw), 512 * 1024)
        result = M.manual_projection(raw)
        self.assertEqual(result["requested_parameter_descriptions"], {})
        self.assertEqual(result["raw_sha256"], M.sha(raw))


class BomDiagnosticTests(unittest.TestCase):
    def rejected(self, raw, code="bom-requested-column-layout-unobserved"):
        context = {"phase": "installed-bom-reader", "observed": {}}
        with patch.object(M, "REFUSAL_CONTEXT", context):
            with self.assertRaisesRegex(M.Refusal, "^" + code + "$"):
                M.bom_projection(raw, P)
        return context["observed"]

    def test_first_failed_row_has_only_bounded_shape_facts(self):
        first = "fixture-valid-path\t40755\t0\t80\t0\n"
        second = "private/user/name\t100644\t501\t20\n"
        later = "later-secret\tbad\n"
        raw = (first + second + later).encode()
        facts = self.rejected(raw)
        self.assertEqual(facts["bom_output_sha256"], M.sha(raw))
        self.assertEqual(facts["bom_size_bytes"], len(raw))
        self.assertEqual(facts["bom_row_count"], 3)
        self.assertEqual(facts["bom_failed_row_index"], 2)
        self.assertEqual(facts["bom_failed_column_count"], 4)
        self.assertEqual(facts["bom_failed_layout_class"], "column-count")
        self.assertEqual(facts["bom_failed_line_sha256"], M.sha(second.rstrip("\n").encode()))
        self.assertEqual(facts["bom_failed_column_4_class"], "absent")
        self.assertEqual(facts["bom_failed_column_4_size_bytes"], 0)
        text = json.dumps(facts)
        for private in ("private/user/name", "later-secret", '"100644"', '"501"'):
            self.assertNotIn(private, text)
        self.assertLess(len(text), 1500)

    def test_mode_and_decimal_rejections_keep_unchanged_grammar(self):
        cases = (
            (b"private\t-rw-r--r--\t0\t0\t9\n", "mode-field", 1, "ascii-other", 10),
            (b"private\t999\t0\t0\t9\n", "mode-field", 1, "ascii-decimal-digits", 3),
            (b"private\t40755\t-1\t0\t9\n", "numeric-field", 2, "ascii-other", 2),
            (b"private\t40755\t1234567890123\t0\t9\n", "numeric-field", 2, "ascii-decimal-digits", 13),
        )
        for raw, reason, column, category, length in cases:
            with self.subTest(digest=M.sha(raw)):
                facts = self.rejected(raw)
                self.assertEqual(facts["bom_failed_layout_class"], reason)
                self.assertEqual(facts[f"bom_failed_column_{column}_class"], category)
                self.assertEqual(facts[f"bom_failed_column_{column}_characters"], length)

    def test_unicode_empty_and_extra_columns_are_classified_not_accepted(self):
        raw = "private\t40755\t٣\t\t9\textra-private\n".encode()
        facts = self.rejected(raw)
        self.assertEqual(facts["bom_failed_column_count"], 6)
        self.assertEqual(facts["bom_failed_column_2_class"], "non-ascii")
        self.assertEqual(facts["bom_failed_column_2_characters"], 1)
        self.assertEqual(facts["bom_failed_column_2_size_bytes"], 2)
        self.assertEqual(facts["bom_failed_column_3_class"], "empty")
        self.assertNotIn("extra-private", json.dumps(facts, ensure_ascii=False))
        self.assertNotIn("٣", json.dumps(facts, ensure_ascii=False))

    def test_bad_utf8_has_bounded_decoder_facts_without_exception_text(self):
        for raw in (b"private\xff", b"\xc2", b"\xed\xa0\x80"):
            with self.subTest(digest=M.sha(raw)):
                facts = self.rejected(raw, "bom-output-encoding")
                self.assertEqual(set(facts), {"bom_output_sha256", "bom_size_bytes", "bom_decoder", "bom_utf8_valid", "bom_decode_error_offset", "bom_decode_error_width"})
                self.assertEqual(facts["bom_decoder"], "strict-utf8")
                self.assertIs(facts["bom_utf8_valid"], False)
                self.assertTrue(0 <= facts["bom_decode_error_offset"] < len(raw))
                self.assertTrue(1 <= facts["bom_decode_error_width"] <= 4)
                self.assertNotIn("private", json.dumps(facts))

    def test_success_clears_previous_failure_and_stays_unqualified(self):
        context = {"phase": "installed-bom-reader", "observed": {}}
        with patch.object(M, "REFUSAL_CONTEXT", context):
            with self.assertRaises(M.Refusal):
                M.bom_projection(b"private\tbad\n", P)
            self.assertIn("bom_failed_line_sha256", context["observed"])
            raw = (M.APP_REL + "\t40755\t0\t80\t0\n").encode()
            result = M.bom_projection(raw, P)
            self.assertEqual(set(context["observed"]), {"bom_output_sha256", "bom_size_bytes", "bom_decoder", "bom_utf8_valid", "bom_row_count"})
            self.assertEqual(result["rows"][0]["requested_columns_as_strings"], ["40755", "0", "80", "0"])
            self.assertFalse(result["native_ownership_proof"])
            self.assertEqual(result["bom_payload_agreement"], "not-checked")
            M.diagnostic_phase("installed-bom-reader")
            self.assertEqual(context["observed"], {})

    def test_new_fact_keys_are_phase_scoped_typed_and_private_extensions_refused(self):
        context = {"phase": "installed-bom-reader", "observed": {}}
        with patch.object(M, "REFUSAL_CONTEXT", context):
            M.diagnostic_phase("receipt-namespace", bom_row_count=3, bom_failed_layout_class="column-count")
            self.assertEqual(context["observed"], {})
            invalids = ({"bom_size_bytes": True}, {"bom_size_bytes": M.MAX_PUBLIC + 1},
                {"bom_row_count": False}, {"bom_row_count": -1}, {"bom_row_count": M.MAX_PUBLIC + 2},
                {"bom_failed_row_index": 0}, {"bom_failed_row_index": M.MAX_ROWS + 1},
                {"bom_failed_column_count": True}, {"bom_failed_column_count": M.MAX_PUBLIC + 2},
                {"bom_failed_line_sha256": "private/path"}, {"bom_failed_layout_class": []},
                {"bom_failed_column_1_class": ["ascii-other"]}, {"bom_failed_column_5_class": "empty"},
                {"bom_failed_column_2_characters": True}, {"bom_failed_column_3_size_bytes": M.MAX_PUBLIC + 1},
                {"bom_decoder": "private/decoder"}, {"bom_utf8_valid": 1},
                {"bom_decode_error_offset": M.MAX_PUBLIC + 1}, {"bom_decode_error_width": 5},
                {"raw_bom": "private text", "path": "private/path", "argv": "private args", "exception_message": "private message"})
            for facts in invalids:
                M.diagnostic_phase("installed-bom-reader", **facts)
                self.assertEqual(context["observed"], {})

    def test_byte_and_row_bounds_keep_existing_refusal_and_do_not_project_paths(self):
        with patch.object(M, "diagnostic_phase", side_effect=AssertionError("no oversized diagnostics")):
            with patch.object(M, "MAX_PUBLIC", 1):
                with self.assertRaisesRegex(M.Refusal, "^bom-output-byte-bound$"):
                    M.bom_projection(b"xx", P)
        raw = b"private-a\t40755\t0\t0\t0\nprivate-b\t40755\t0\t0\t0\n"
        with patch.object(M, "MAX_ROWS", 1):
            facts = self.rejected(raw, "bom-output-row-bound")
        self.assertEqual(facts["bom_row_count"], 2)
        self.assertNotIn("bom_failed_row_index", facts)
        self.assertNotIn("private", json.dumps(facts))

    def test_long_numeric_field_is_counted_without_integer_conversion(self):
        field = "9" * 5000
        raw = ("private\t40755\t" + field + "\t0\t0\n").encode()
        facts = self.rejected(raw)
        self.assertEqual(facts["bom_failed_column_2_class"], "ascii-decimal-digits")
        self.assertEqual(facts["bom_failed_column_2_characters"], 5000)
        self.assertLess(len(json.dumps(facts)), 1500)


class BomDirectorySizeGrammarTests(unittest.TestCase):
    def rejected(self, raw):
        context = {"phase": "installed-bom-reader", "observed": {}}
        with patch.object(M, "REFUSAL_CONTEXT", context):
            with self.assertRaisesRegex(M.Refusal, "^bom-requested-column-layout-unobserved$"):
                M.bom_projection(raw, P)
        return context["observed"]

    def test_empty_size_directory_is_retained_as_absent_string(self):
        raw = (M.APP_REL + "\t40755\t0\t80\t\n").encode()
        result = M.bom_projection(raw, P)
        self.assertEqual(result["rows"][0]["requested_columns_as_strings"], ["40755", "0", "80", ""])
        self.assertIs(result["all_rows_parsed"], True)
        self.assertFalse(result["native_ownership_proof"])
        self.assertEqual(result["ownership_mode_size_semantics"], "unqualified-until-installed-manual-and-output-review")
        self.assertEqual(result["bom_payload_agreement"], "not-checked")

    def test_directory_type_mask_handles_permissions_and_bounded_padding(self):
        for mode in ("40000", "040755", "00040755", "47777"):
            with self.subTest(mode=mode):
                result = M.bom_projection((M.APP_REL + "\t" + mode + "\t0\t0\t\n").encode(), P)
                self.assertEqual(result["rows"][0]["requested_columns_as_strings"], [mode, "0", "0", ""])

    def test_non_directory_types_cannot_omit_size(self):
        for mode in ("100644", "120777", "20666", "60666", "10666", "140777", "160000", "0", "755"):
            with self.subTest(mode=mode):
                facts = self.rejected(("private-fixture\t" + mode + "\t0\t0\t\n").encode())
                self.assertEqual(facts["bom_failed_layout_class"], "numeric-field")
                self.assertEqual(facts["bom_failed_column_4_class"], "empty")
                self.assertNotIn("private-fixture", json.dumps(facts))

    def test_directory_requires_exactly_five_columns(self):
        for raw in (b"fixture\t40755\t0\t0\n", b"fixture\t40755\t0\t0\t\t\n"):
            with self.subTest(raw=raw):
                self.assertEqual(self.rejected(raw)["bom_failed_layout_class"], "column-count")

    def test_empty_size_requires_valid_bounded_ascii_octal_mode(self):
        for mode in ("", "40758", " 40755", "+40755", "40755 ", "000040755", "４０７５５"):
            with self.subTest(mode=mode):
                self.assertEqual(self.rejected(("fixture\t" + mode + "\t0\t0\t\n").encode())["bom_failed_layout_class"], "mode-field")

    def test_uid_and_gid_remain_required_bounded_ascii_decimal(self):
        for uid, gid in (("", "0"), ("0", ""), ("-1", "0"), ("0", "+1"), ("0", " 0"),
                         ("１", "0"), ("9" * 13, "0"), ("0", "9" * 13)):
            with self.subTest(uid=uid, gid=gid):
                self.assertEqual(self.rejected(("fixture\t40755\t" + uid + "\t" + gid + "\t\n").encode())["bom_failed_layout_class"], "numeric-field")

    def test_nonempty_directory_size_remains_strict_decimal(self):
        for size in (" ", "+0", "-0", "1.0", "１", "9" * 13):
            with self.subTest(size=size):
                self.assertEqual(self.rejected(("fixture\t40755\t0\t0\t" + size + "\n").encode())["bom_failed_layout_class"], "numeric-field")

    def test_numeric_sizes_remain_unmodified_for_directory_regular_and_symlink(self):
        for mode in ("40755", "100644", "120777"):
            for size in ("0", "12", "999999999999"):
                with self.subTest(mode=mode, size=size):
                    result = M.bom_projection((M.APP_REL + "\t" + mode + "\t0\t0\t" + size + "\n").encode(), P)
                    self.assertEqual(result["rows"][0]["requested_columns_as_strings"], [mode, "0", "0", size])

    def test_empty_directory_size_does_not_bypass_path_or_alias_refusals(self):
        with self.assertRaisesRegex(M.Refusal, "^unsafe-member-name-component$"):
            M.bom_projection(b"../fixture\t40755\t0\t0\t\n", P)
        with self.assertRaisesRegex(M.Refusal, "^bom-path-alias-or-duplicate$"):
            M.bom_projection(b"Applications/Caf\xc3\xa9\t40755\t0\t0\t\nApplications/Cafe\xcc\x81\t40755\t0\t0\t\n", P)

    def test_private_directory_path_is_unprojected_and_size_not_invented(self):
        result = M.bom_projection(b"private-fixture-directory\t40755\t0\t0\t\n", P)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["unprojected_path_count"], 1)
        self.assertNotIn("private-fixture-directory", json.dumps(result))

    def test_mixed_rows_keep_directory_absence_and_regular_value_distinct(self):
        raw = (M.APP_REL + "\t40755\t0\t0\t\n" + M.APP_REL + "/Contents/Info.plist\t100644\t0\t0\t123\n").encode()
        result = M.bom_projection(raw, P)
        self.assertEqual([row["requested_columns_as_strings"][-1] for row in result["rows"]], ["", "123"])


class ReceiptCommandDiagnosticTests(unittest.TestCase):
    @staticmethod
    def context(operation="info", phase="receipt-info-and-files"):
        return {"phase": phase, "observed": {"receipt_operation": operation}}

    def test_separate_retained_hash_counts_never_project_raw_bytes(self):
        facts = M.command_stream_facts((b"private-stdout", b"private-stderr"), 64,
            (False, False, False, False, False), 0)
        self.assertEqual(facts["command_stdout_bytes"], 14)
        self.assertEqual(facts["command_stderr_bytes"], 14)
        self.assertEqual(facts["command_stdout_sha256"], M.sha(b"private-stdout"))
        self.assertEqual(facts["command_stderr_sha256"], M.sha(b"private-stderr"))
        self.assertNotIn("private-stdout", json.dumps(facts))
        self.assertNotIn("private-stderr", json.dumps(facts))

    def test_stream_conditions_are_independent_observations(self):
        keys = ("command_stdout_overflow_observed", "command_stderr_overflow_observed",
            "command_stdout_read_error_observed", "command_stderr_read_error_observed",
            "command_stdin_write_error_observed")
        for selected in range(5):
            with self.subTest(selected=selected):
                flags = tuple(index == selected for index in range(5))
                facts = M.command_stream_facts((b"", b""), 64, flags, 0)
                self.assertEqual([facts[key] for key in keys], list(flags))

    def test_live_pipe_count_and_multiple_flags_do_not_claim_cleanup(self):
        facts = M.command_stream_facts((b"", b""), 64, (True, True, True, True, True), 3)
        self.assertEqual(facts["command_live_pipe_threads"], 3)
        self.assertNotIn("cleanup_complete", facts)
        self.assertNotIn("approval", facts)

    def test_projection_bounds_and_plain_types_are_strict(self):
        valid = ((b"", b""), 64, (False,) * 5, 0)
        for index, replacement in ((0, [b"", b""]), (0, (b"", "text")), (0, (b"x" * 65, b"")),
            (0, (b"", b"x" * (1024 * 1024 + 1))), (1, True), (1, 0),
            (1, 4 * 1024 * 1024 + 1), (2, (False,) * 4), (2, (0,) * 5),
            (3, True), (3, -1), (3, 4)):
            with self.subTest(index=index, type_name=type(replacement).__name__):
                args = list(valid)
                args[index] = replacement
                with self.assertRaises(M.Refusal):
                    M.command_stream_facts(*args)

    def test_fixed_operation_stage_and_ordinal_project_without_identifier(self):
        context = self.context()
        with patch.object(M, "REFUSAL_CONTEXT", context):
            for operation in sorted(M.RECEIPT_OPERATIONS):
                M.diagnostic_phase("receipt-info-and-files", receipt_operation=operation, receipt_query_index=5)
                self.assertEqual(context["observed"]["receipt_operation"], operation)
                self.assertEqual(context["observed"]["receipt_query_index"], 5)
            M.diagnostic_phase("receipt-info-and-files", receipt_operation="info")
            for stage in sorted(M.COMMAND_DIAGNOSTIC_STAGES):
                M.receipt_command_checkpoint(stage)
                self.assertEqual(context["observed"]["command_stage"], stage)
        self.assertNotIn("identifier", context["observed"])

    def test_raw_fields_wrong_types_and_unknown_enums_are_not_retained(self):
        context = self.context()
        with patch.object(M, "REFUSAL_CONTEXT", context):
            M.diagnostic_phase("receipt-info-and-files", receipt_identifier="private.receipt",
                argv=["private"], stderr="private", exception="private", command_stage="/private/path",
                receipt_query_index=True, command_stdout_bytes=True, command_stdout_sha256="private",
                command_stdout_read_error_observed=1, command_live_pipe_threads=True)
        self.assertEqual(context["observed"], {"receipt_operation": "info"})

    def test_operation_transition_clears_command_facts_new_receipt_clears_old_hashes(self):
        context = self.context()
        with patch.object(M, "REFUSAL_CONTEXT", context):
            M.receipt_command_checkpoint("wait", streams=(b"old", b""), limit=64,
                flags=(False,) * 5, live_threads=0)
            M.diagnostic_phase("receipt-info-and-files", receipt_info_sha256="a" * 64,
                receipt_files_sha256="b" * 64, receipts_queried=4)
            M.diagnostic_phase("receipt-info-and-files", receipt_operation="files")
            self.assertFalse(set(M.COMMAND_DIAGNOSTIC_KEYS) & set(context["observed"]))
            self.assertIn("receipt_info_sha256", context["observed"])
            M.diagnostic_phase("receipt-info-and-files", receipt_operation="info", receipt_query_index=5)
        self.assertNotIn("receipt_info_sha256", context["observed"])
        self.assertNotIn("receipt_files_sha256", context["observed"])
        self.assertEqual(context["observed"]["receipts_queried"], 4)

    def test_no_command_diagnostics_outside_current_receipt_capture(self):
        for phase, operation in (("receipt-namespace", "info"), ("installed-bom-reader", "files"),
            ("receipt-info-and-files", "projection"), ("receipt-info-and-files", "relevance")):
            with self.subTest(phase=phase, operation=operation):
                context = self.context(operation, phase)
                with patch.object(M, "REFUSAL_CONTEXT", context):
                    M.receipt_command_checkpoint("wait", streams=None)
                self.assertNotIn("command_stage", context["observed"])
        with patch.object(M, "REFUSAL_CONTEXT", None):
            M.receipt_command_checkpoint("wait")

    def test_capture_actual_wait_refusal_distinguishes_each_stream_condition(self):
        # All child/thread/cleanup operations are synthetic. No observer main,
        # native process, tool, file helper, ctypes or network is invoked.
        class Thread:
            def __init__(self, *, target, args=(), daemon=False):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)
            def join(self, _timeout):
                pass
            def is_alive(self):
                return False
        class ReadError:
            def read(self, _amount):
                raise OSError("private-error-message")
            def close(self):
                pass
        class Child:
            def __init__(self, stdout, stderr):
                self.stdout, self.stderr, self.stdin = stdout, stderr, None
                self.returncode = None
            def wait(self, **_kwargs):
                raise AssertionError("the observed pipe failure must refuse before wait")
        for stream, condition in (("stdout", "overflow"), ("stderr", "overflow"),
            ("stdout", "read_error"), ("stderr", "read_error")):
            with self.subTest(stream=stream, condition=condition):
                stdout, stderr = io.BytesIO(), io.BytesIO()
                value = (io.BytesIO(b"x" * (3 if stream == "stdout" else 1024 * 1024 + 1))
                    if condition == "overflow" else ReadError())
                child = Child(value if stream == "stdout" else stdout,
                    value if stream == "stderr" else stderr)
                context = self.context()
                context["observed"].update(receipt_query_index=5, receipts_queried=4)
                def terminate_owned_process(process, timeout_seconds, *, expected_child=child):
                    self.assertIs(process, expected_child)
                    self.assertEqual(timeout_seconds, 5)
                    process.returncode = -15
                with patch.object(M, "REFUSAL_CONTEXT", context), patch.object(M.os, "name", "nt"),                     patch.object(M.time, "monotonic", return_value=100),                     patch.object(M.threading, "Thread", Thread),                     patch.object(M.subprocess, "Popen", return_value=child),                     patch.object(M, "load_module", return_value=SimpleNamespace(terminate_owned_process=terminate_owned_process)):
                    commands = M.Commands()
                    with self.assertRaisesRegex(M.EvidenceError, "^command-output-bound-or-read$"):
                        commands.capture(["fixed-private-argv"], timeout=30, limit=2)
                facts = context["observed"]
                self.assertEqual(facts["command_stage"], "wait")
                self.assertTrue(facts["command_" + stream + "_" + condition + "_observed"])
                self.assertEqual(facts["receipt_query_index"], 5)
                self.assertEqual(facts["receipts_queried"], 4)
                self.assertTrue(commands.uncertain)
                self.assertTrue(commands.calls[0]["leader_cleanup_attempted"])
                self.assertEqual(commands.calls[0]["process_tree_cleanup"], "not-proven")
                self.assertNotIn("private-error-message", json.dumps(facts))
                self.assertNotIn("fixed-private-argv", json.dumps(facts))

    def test_new_operation_without_capture_has_no_stream_or_partial_success_claim(self):
        context = self.context()
        with patch.object(M, "REFUSAL_CONTEXT", context):
            M.diagnostic_phase("receipt-info-and-files", receipt_query_index=5, receipt_operation="info",
                receipts_queried=4)
        self.assertEqual(context["observed"], {"receipt_operation": "info", "receipt_query_index": 5,
            "receipts_queried": 4})
        for key in ("approval", "signing_trust", "all_listed_receipts_queried", "complete"):
            self.assertNotIn(key, context["observed"])


class ReceiptFilesStreamingTests(unittest.TestCase):
    def projection(self, raw, *, width=65536, metadata=None, maximum=None):
        kwargs = {} if maximum is None else {"maximum": maximum}
        value = M.ReceiptFilesProjection(info() if metadata is None else metadata, P, **kwargs)
        for start in range(0, len(raw), width):
            value.feed(raw[start:start + width])
        value.finish()
        return value

    def test_receipt_location_fixed_causes_match_whole_and_stream_without_private_text(self):
        cases = (("", "receipt-location-empty"),
                 ("PRIVATE-relative", "receipt-location-relative"),
                 (".", "receipt-location-relative"),
                 ("PRIVATE-" + "x" * 1100, "receipt-location-relative"),
                 ("/" + "x" * 1024, "receipt-location-byte-bound"),
                 ("/" + "\u00e9" * 512, "receipt-location-byte-bound"))
        for location, code in cases:
            metadata = info(**{"install-location": location})
            for streaming in (False, True):
                with self.subTest(code=code, streaming=streaming):
                    with self.assertRaisesRegex(M.Refusal, "^" + code + "$") as failure:
                        if streaming:
                            M.ReceiptFilesProjection(metadata, P)
                        else:
                            M.receipt_projection(metadata, b".\n", P)
                    self.assertEqual(failure.exception.args, (code,))
                    self.assertIn(code, M.REFUSAL_CODES)
                    self.assertNotIn("PRIVATE", str(failure.exception))

    def test_receipt_location_byte_boundary_stays_accepted_without_ownership_claim(self):
        for location in ("/", "/" + "x" * 1023, "/" + "\u00e9" * 511 + "x"):
            with self.subTest(location_bytes=len(location.encode())):
                metadata = info(**{"install-location": location})
                expected = M.receipt_projection(metadata, b".\n", P)
                stream = self.projection(b".\n", width=1, metadata=metadata)
                self.assertEqual(stream.result(), expected)
                self.assertEqual(expected["install_location_is_root"], location == "/")
                self.assertFalse(expected["receipt_ownership_approval"])
                self.assertEqual(expected["physical_namespace_identity"], "unobserved")

    def test_every_chunk_boundary_matches_whole_reference_splitlines(self):
        raw = (".\r\nCaf\u00e9\vother\fthird\x1cfourth\x1dfifth\x1esixth\x85seventh"
            "\u2028eighth\u2029" + M.APP_REL + "\rfinal").encode()
        expected = M.receipt_projection(info(), raw, P)
        for boundary in range(len(raw) + 1):
            with self.subTest(boundary=boundary):
                value = M.ReceiptFilesProjection(info(), P)
                value.feed(raw[:boundary])
                value.feed(raw[boundary:])
                value.finish()
                self.assertEqual(value.result(), expected)
                self.assertEqual(value.line, [])
                self.assertLessEqual(len(value.decoder.getstate()[0]), 3)

    def test_empty_terminal_separator_and_unterminated_rows_match_reference(self):
        for raw in (b"", b"a", b"a\n", b"a\r", b"a\r\n", b"a\r\nb"):
            with self.subTest(raw=raw):
                self.assertEqual(self.projection(raw, width=1).result(), M.receipt_projection(info(), raw, P))
        with self.assertRaisesRegex(M.Refusal, "^unsafe-member-name-type-or-empty$"):
            self.projection(b"\n")

    def test_valid_above_old_buffer_bound_checks_unrelated_rows_and_final_app(self):
        raw = b"".join((f"private-unrelated-{index:05d}-" + "x" * 140 + "\n").encode()
            for index in range(29999)) + M.APP_REL.encode() + b"\n"
        self.assertGreater(len(raw), M.MAX_PUBLIC)
        self.assertLess(len(raw), M.MAX_RECEIPT_FILE_BYTES)
        value = self.projection(raw)
        row = value.result()
        self.assertEqual(row["path_count"], M.MAX_ROWS)
        self.assertEqual(row["lexical_app_claim_count"], 1)
        self.assertEqual(row["files_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(value.raw_bytes, len(raw))
        self.assertEqual(len(value.keys), M.MAX_ROWS)
        self.assertNotIn("private-unrelated", json.dumps(row))
        self.assertFalse(any(isinstance(item, bytearray) for item in vars(value).values()))

    def test_aliases_anywhere_after_relevance_remain_refused(self):
        for tail in ("Caf\u00e9\nCafe\u0301\n", "unrelated\nUNRELATED\n", M.APP_REL + "\n"):
            with self.subTest(tail=tail):
                with self.assertRaisesRegex(M.Refusal, "^receipt-path-alias-or-duplicate$"):
                    self.projection((M.APP_REL + "\n" + tail).encode(), width=1)

    def test_base_root_alias_and_data_projection_match_unchanged_reference(self):
        for location, raw in (("/Applications", b"Remote Ops Workspace.app\nother"),
            ("/", (M.APP_REL.lower() + "\nSystem/Volumes/Data/" + M.APP_REL + "\n").encode()),
            ("/fixture-base/", b".\nchild\n")):
            with self.subTest(location=location):
                metadata = info(**{"install-location": location})
                self.assertEqual(self.projection(raw, metadata=metadata, width=3).result(),
                    M.receipt_projection(metadata, raw, P))

    def test_bad_utf8_line_names_and_row_bound_fail_before_result(self):
        cases = (b"\xff", b"a\n\xc3", b"a\n../bad\n", b"a\n/absolute\n", b"x" * 1025,
            b"a\n\n", b"a\x00\n")
        for raw in cases:
            with self.subTest(raw=raw[:16]):
                with self.assertRaises(M.Refusal):
                    self.projection(raw, width=1)
        raw = b"".join(f"row-{index}\n".encode() for index in range(M.MAX_RECEIPT_FILE_ROWS + 1))
        with self.assertRaisesRegex(M.Refusal, "^receipt-files-row-bound$"):
            self.projection(raw)

    def test_derived_limit_and_remaining_budget_exact_eof_and_sentinel(self):
        self.assertEqual(M.MAX_RECEIPT_FILE_BYTES, 30810000)
        self.assertEqual(M.MAX_RECEIPT_FILE_BYTES, M.MAX_ROWS * (1024 + 3))
        value = self.projection(b"a\nb\n", maximum=4)
        self.assertEqual(value.result()["path_count"], 2)
        self.assertEqual(value.raw_bytes, 4)
        charged = []
        stream = M.ReceiptCommandStream(M.ReceiptFilesProjection(info(), P, maximum=4), charged.append)
        stream.consume(0, b"a\nb\n")
        self.assertEqual(stream.read_limit(0), 1)
        with self.assertRaisesRegex(M.EvidenceError, "^command-output-bound-or-read$"):
            stream.consume(0, b"x")
        self.assertEqual(charged, [4, 1])
        facts = stream.snapshot()
        self.assertEqual(facts["receipt_stream_stdout_bytes"], 5)
        self.assertTrue(facts["receipt_stream_hashes_partial"])
        self.assertFalse(facts["receipt_stream_complete"])

    def mock_capture(self, raw, *, stderr=b"", mode="ok", prior_bytes=0, private=None):
        clock, cleanup = [100], []
        class Thread:
            def __init__(self, *, target, args=(), daemon=False):
                self.target, self.args = target, args
                self.live = mode == "live-pipe" and args[1] == 0
            def start(self):
                if not self.live:
                    self.target(*self.args)
            def join(self, _timeout):
                pass
            def is_alive(self):
                return self.live
        class ReadError:
            def read(self, _maximum):
                raise OSError("PRIVATE read error")
            def close(self):
                pass
        class Child:
            def __init__(self):
                self.stdout = ReadError() if mode == "read-error" else io.BytesIO(raw)
                self.stderr, self.stdin, self.returncode = io.BytesIO(stderr), None, None
            def wait(self, **_kwargs):
                if mode == "timeout":
                    clock[0] = 131
                    raise M.subprocess.TimeoutExpired("PRIVATE argv", 1)
                if mode == "late-exit":
                    clock[0] = 131
                self.returncode = 1 if mode == "nonzero" else 0
                return self.returncode
        child = Child()
        def terminate_owned_process(process, timeout_seconds):
            self.assertIs(process, child)
            self.assertEqual(timeout_seconds, 5)
            cleanup.append(process)
            process.returncode = -15
        context = {"phase": "receipt-info-and-files", "observed": {
            "receipt_operation": "files", "receipt_query_index": 5, "receipts_queried": 4}}
        with patch.object(M.os, "name", "nt"), patch.object(M.time, "monotonic", side_effect=lambda: clock[0]), \
            patch.object(M.threading, "Thread", Thread), patch.object(M.subprocess, "Popen", return_value=child) as popen, \
            patch.object(M, "load_module", return_value=SimpleNamespace(terminate_owned_process=terminate_owned_process)), \
            patch.object(M, "REFUSAL_CONTEXT", context):
            commands = M.MetadataCommands()
            commands.private = private
            commands.retained_output_bytes = prior_bytes
            result, refusal = None, None
            try:
                result = commands.receipt_files("fixture.receipt", info(), P)
            except M.Refusal as error:
                refusal = str(error)
        return result, refusal, commands, child, cleanup, context["observed"], popen

    def test_actual_capture_streams_hashes_after_zero_exit_without_stdout_retention(self):
        raw = ("Caf\u00e9\n" + M.APP_REL + "\n").encode()
        result, refusal, commands, child, cleanup, facts, popen = self.mock_capture(raw)
        self.assertIsNone(refusal)
        self.assertEqual(result, M.receipt_projection(info(), raw, P))
        self.assertEqual(commands.retained_output_bytes, len(raw))
        self.assertEqual(child.returncode, 0)
        self.assertEqual(cleanup, [])
        self.assertTrue(facts["receipt_stream_complete"])
        self.assertFalse(facts["receipt_stream_hashes_partial"])
        self.assertEqual(facts["receipt_stream_stdout_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(facts["command_stdout_bytes"], 0)
        self.assertEqual(facts["receipts_queried"], 4)
        self.assertNotIn("all_listed_receipts_queried", facts)
        self.assertEqual(popen.call_args.args[0], ["/usr/sbin/pkgutil", "--files", "fixture.receipt"])
        self.assertEqual(popen.call_args.kwargs["env"]["LC_ALL"], "en_US.UTF-8")

    def test_parser_stderr_exit_read_and_pipe_failures_clean_only_retained_child(self):
        cases = ((b"a\na\n", b"", "ok", "receipt-path-alias-or-duplicate"),
            (b"a\n\xc3", b"", "ok", "receipt-metadata-layout-unobserved"),
            (b"a\n", b"PRIVATE warning", "ok", "receipt-files-stderr-unobserved"),
            (b"a\n", b"", "nonzero", "command-unexpected-exit"),
            (b"a\n", b"", "read-error", "command-output-bound-or-read"),
            (b"a\n", b"", "live-pipe", "command-pipe-lifetime-or-bound"),
            (b"a\n", b"", "late-exit", "command-late-completed-exit"),
            (b"a\n", b"", "timeout", "command-timeout"))
        for raw, stderr, mode, expected in cases:
            with self.subTest(mode=mode, expected=expected):
                result, refusal, commands, child, cleanup, facts, _popen = self.mock_capture(raw, stderr=stderr, mode=mode)
                self.assertIsNone(result)
                self.assertEqual(refusal, expected)
                self.assertTrue(commands.uncertain)
                self.assertEqual(cleanup, [child])
                self.assertTrue(commands.calls[0]["leader_cleanup_attempted"])
                self.assertFalse(facts["receipt_stream_complete"])
                self.assertTrue(facts["receipt_stream_hashes_partial"])
                self.assertEqual(facts["receipts_queried"], 4)
                self.assertNotIn("receipt_files_sha256", facts)
                self.assertNotIn("PRIVATE", json.dumps(facts))

    def test_aggregate_charges_stdout_stderr_and_blocks_resuming_partial_query(self):
        result, refusal, commands, _child, _cleanup, facts, _popen = self.mock_capture(
            b"a\n", stderr=b"xy", prior_bytes=M.MAX_PRIVATE_COMMAND_BYTES - 3)
        self.assertIsNone(result)
        self.assertEqual(refusal, "metadata-command-or-aggregate-bound")
        self.assertEqual(commands.retained_output_bytes, M.MAX_PRIVATE_COMMAND_BYTES + 1)
        self.assertTrue(commands.uncertain)
        self.assertEqual(facts["receipt_stream_stdout_bound_bytes"], 3)
        self.assertEqual(facts["receipt_stream_stdout_bytes"], 2)
        self.assertEqual(facts["receipt_stream_stderr_bytes"], 2)
        with self.assertRaisesRegex(M.Refusal, "^metadata-overall-deadline$"):
            commands.remaining()

    def test_invalid_info_identifier_and_command_budget_refuse_before_launch(self):
        with patch.object(M.subprocess, "Popen", side_effect=AssertionError("no launch")) as popen:
            for identifier, metadata in (("../private", info()), ("fixture.receipt", b"not a plist"),
                ("fixture.receipt", info(**{"install-location": "relative"})),
                ("fixture.receipt", info(**{"install-location": "/../escape"}))):
                with self.subTest(identifier=identifier):
                    with self.assertRaises(M.Refusal):
                        M.MetadataCommands().receipt_files(identifier, metadata, P)
            commands = M.MetadataCommands()
            commands.calls = [{}] * 4050
            with self.assertRaisesRegex(M.Refusal, "^metadata-command-or-aggregate-bound$"):
                commands.receipt_files("fixture.receipt", info(), P)
            popen.assert_not_called()

    def test_stream_diagnostics_are_typed_partial_scoped_and_operation_cleared(self):
        context = {"phase": "receipt-info-and-files", "observed": {"receipt_operation": "files"}}
        stream = M.ReceiptCommandStream(M.ReceiptFilesProjection(info(), P), lambda _count: None)
        stream.consume(0, b"a\n")
        with patch.object(M, "REFUSAL_CONTEXT", context):
            M.receipt_stream_checkpoint("wait", stream)
            self.assertTrue(context["observed"]["receipt_stream_hashes_partial"])
            M.diagnostic_phase("receipt-info-and-files", receipt_stream_stdout_bytes=True,
                receipt_stream_complete=1, receipt_stream_private_path="PRIVATE")
            self.assertEqual(context["observed"]["receipt_stream_stdout_bytes"], 2)
            self.assertFalse(context["observed"]["receipt_stream_complete"])
            self.assertNotIn("receipt_stream_private_path", context["observed"])
            M.diagnostic_phase("receipt-info-and-files", receipt_operation="info", receipt_query_index=6)
            self.assertFalse(any(key.startswith("receipt_stream_") for key in context["observed"]))


    def test_actual_private_workspace_streams_without_stdout_or_stderr_artifact(self):
        raw = ("private-unrelated\n" + M.APP_REL + "\n").encode()
        private = M.ROOT / "fixture-private-no-write"
        with patch.object(M.Path, "write_bytes", side_effect=AssertionError("no raw artifact"), create=True) as write:
            result, refusal, commands, child, cleanup, facts, _popen = self.mock_capture(raw, private=private)
        self.assertIsNone(refusal)
        self.assertIs(commands.private, private)
        self.assertEqual(result, M.receipt_projection(info(), raw, P))
        self.assertEqual(child.returncode, 0)
        self.assertEqual(cleanup, [])
        self.assertTrue(facts["receipt_stream_complete"])
        self.assertEqual(facts["command_stdout_bytes"], 0)
        self.assertEqual(facts["command_stderr_bytes"], 0)
        write.assert_not_called()

    def test_row_bound_fixed_code_precedes_excess_row_name_parser(self):
        with patch.object(M, "MAX_RECEIPT_FILE_ROWS", 2), patch.object(P, "member_name", wraps=P.member_name) as member:
            value = M.ReceiptFilesProjection(info(), P)
            value.feed(b"a\nb\n")
            self.assertEqual(value.rows, 2)
            self.assertEqual(len(value.keys), 2)
            with self.assertRaisesRegex(M.Refusal, "^receipt-files-row-bound$"):
                value.feed(b"../PRIVATE-overflow\n")
            self.assertEqual([call.args for call in member.call_args_list], [("a",), ("b",)])
            self.assertEqual([call.kwargs for call in member.call_args_list], [{"root": True, "receipt": True}, {"root": True, "receipt": True}])
            self.assertEqual(value.rows, 3)
            self.assertEqual(len(value.keys), 2)
            self.assertFalse(value.finished)
            with self.assertRaisesRegex(M.Refusal, "^receipt-metadata-layout-unobserved$"):
                value.result()

    def test_unterminated_excess_row_uses_fixed_code_without_eof(self):
        raw = b"a\nb\nPRIVATE-unterminated"
        with patch.object(M, "MAX_RECEIPT_FILE_ROWS", 2):
            value = M.ReceiptFilesProjection(info(), P)
            stream = M.ReceiptCommandStream(value, lambda _count: None)
            stream.consume(0, raw)
            with self.assertRaisesRegex(M.Refusal, "^receipt-files-row-bound$") as failure:
                stream.eof(0)
            stream.fail(failure.exception)
            self.assertEqual(stream.failure_code, "receipt-files-row-bound")
            self.assertIn(stream.failure_code, M.REFUSAL_CODES)
            with self.assertRaisesRegex(M.EvidenceError, "^command-pipe-lifetime-or-bound$"):
                stream.ready()
        facts = stream.snapshot()
        self.assertEqual(facts["receipt_stream_stdout_bytes"], len(raw))
        self.assertEqual(facts["receipt_stream_stdout_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(facts["receipt_stream_stdout_eof"])
        self.assertFalse(facts["receipt_stream_complete"])
        self.assertTrue(facts["receipt_stream_hashes_partial"])
        self.assertFalse(value.finished)
        self.assertNotIn("PRIVATE", json.dumps(facts))

    def test_row_bound_capture_refuses_and_reaps_only_retained_child(self):
        raw = b"a\nb\nPRIVATE-third-row\n"
        with patch.object(M, "MAX_RECEIPT_FILE_ROWS", 2):
            result, refusal, commands, child, cleanup, facts, _popen = self.mock_capture(raw)
        self.assertIsNone(result)
        self.assertEqual(refusal, "receipt-files-row-bound")
        self.assertTrue(commands.uncertain)
        self.assertEqual(cleanup, [child])
        self.assertTrue(commands.calls[0]["leader_cleanup_attempted"])
        self.assertEqual(commands.calls[0]["process_tree_cleanup"], "not-proven")
        self.assertEqual(facts["receipt_query_index"], 5)
        self.assertEqual(facts["receipts_queried"], 4)
        self.assertEqual(facts["receipt_stream_stdout_bytes"], len(raw))
        self.assertEqual(facts["receipt_stream_stdout_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(facts["receipt_stream_stdout_eof"])
        self.assertFalse(facts["receipt_stream_complete"])
        self.assertTrue(facts["receipt_stream_hashes_partial"])
        self.assertNotIn("receipt_files_sha256", facts)
        self.assertNotIn("PRIVATE", json.dumps(facts))

    def test_receipt_cardinality_limits_are_separate_from_package_and_byte_limits(self):
        self.assertEqual(M.MAX_ROWS, 30000)
        self.assertEqual(M.MAX_RECEIPT_FILE_ROWS, 200000)
        self.assertEqual(M.MAX_RECEIPT_FILE_BYTES, 30810000)
        self.assertEqual(M.MAX_RECEIPT_ALIAS_BYTES, 32 * 1024 * 1024)

    def test_more_than_package_row_limit_preserves_full_receipt_projection(self):
        raw = b"".join(f"private-file-{index:05d}\n".encode() for index in range(M.MAX_ROWS))
        raw += M.APP_REL.encode() + b"\n"
        value = self.projection(raw)
        result = value.result()
        self.assertEqual(result, M.receipt_projection(info(), raw, P))
        self.assertEqual(result["path_count"], 30001)
        self.assertEqual(result["lexical_app_claim_count"], 1)
        self.assertEqual(result["files_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(value.keys), 30001)
        self.assertEqual(value.key_bytes, sum(len(key.encode("utf-8")) for key in value.keys))
        self.assertEqual(value.line, [])
        self.assertNotIn("private-file", json.dumps(result))

    def test_invalid_or_duplicate_tail_after_old_row_limit_still_refuses(self):
        prefix = b"".join(f"private-file-{index:05d}\n".encode() for index in range(M.MAX_ROWS))
        prefix += M.APP_REL.encode() + b"\n"
        for tail, code in (
            (M.APP_REL.upper().encode() + b"\n", "receipt-path-alias-or-duplicate"),
            (b"../PRIVATE-invalid-tail\n", "unsafe-member-name-component"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(M.Refusal, "^" + code + "$"):
                    self.projection(prefix + tail)

    def test_alias_payload_budget_uses_utf8_and_refuses_before_retention(self):
        raw = "caf\u00e9\nbeta\n".encode()
        with patch.object(M, "MAX_RECEIPT_ALIAS_BYTES", 9):
            value = self.projection(raw)
            self.assertEqual(value.result(), M.receipt_projection(info(), raw, P))
            self.assertEqual(value.key_bytes, 9)
            limited = M.ReceiptFilesProjection(info(), P)
            limited.feed(raw)
            with self.assertRaisesRegex(M.Refusal, "^receipt-alias-memory-bound$"):
                limited.feed(b"z\n")
            self.assertEqual(limited.key_bytes, 9)
            self.assertEqual(len(limited.keys), 2)
            self.assertFalse(limited.finished)
            self.assertNotIn("z", limited.keys)
        with patch.object(M, "MAX_RECEIPT_ALIAS_BYTES", 8):
            with self.assertRaisesRegex(M.Refusal, "^receipt-alias-memory-bound$"):
                self.projection(raw)
            with self.assertRaisesRegex(M.Refusal, "^receipt-alias-memory-bound$"):
                M.receipt_projection(info(), raw, P)

    def test_alias_memory_capture_refuses_and_reaps_retained_child(self):
        raw = b"a\nPRIVATE-second-row\n"
        with patch.object(M, "MAX_RECEIPT_ALIAS_BYTES", 1):
            result, refusal, commands, child, cleanup, facts, _popen = self.mock_capture(raw)
        self.assertIsNone(result)
        self.assertEqual(refusal, "receipt-alias-memory-bound")
        self.assertIn(refusal, M.REFUSAL_CODES)
        self.assertTrue(commands.uncertain)
        self.assertEqual(cleanup, [child])
        self.assertTrue(commands.calls[0]["leader_cleanup_attempted"])
        self.assertEqual(commands.calls[0]["process_tree_cleanup"], "not-proven")
        self.assertFalse(facts["receipt_stream_stdout_eof"])
        self.assertFalse(facts["receipt_stream_complete"])
        self.assertTrue(facts["receipt_stream_hashes_partial"])
        self.assertNotIn("receipt_files_sha256", facts)
        self.assertNotIn("PRIVATE", json.dumps(facts))


class MemberNamePredicateDiagnosticTests(unittest.TestCase):
    def test_fixed_name_predicates_do_not_disclose_input(self):
        cases = (
            (None, "type-or-empty"), ("", "type-or-empty"),
            ("PRIVATE" + "x" * 1024, "utf8-bound"),
            ("PRIVATE\\name", "backslash"), ("PRIVATE:name", "colon"),
            ("/PRIVATE/name", "absolute"), ("PRIVATE\x00name", "control"),
            ("PRIVATE\x7fname", "control"), ("../PRIVATE/name", "component"),
            ("PRIVATE//name", "component"), ("./PRIVATE/./name", "component"),
        )
        for value, suffix in cases:
            with self.subTest(suffix=suffix):
                code = "unsafe-member-name-" + suffix
                with self.assertRaisesRegex(M.Refusal, "^" + code + "$") as failure:
                    M.member_name(value)
                self.assertIn(code, M.REFUSAL_CODES)
                self.assertEqual(failure.exception.args, (code,))
                self.assertNotIn("PRIVATE", str(failure.exception))

    def test_accepted_name_normalization_and_root_semantics_unchanged(self):
        for value, expected in (("alpha", "alpha"), ("./alpha/", "alpha"),
                ("a b/Caf\u00e9", "a b/Caf\u00e9"), ("x" * 1024, "x" * 1024)):
            with self.subTest(value=value):
                self.assertEqual(M.member_name(value), expected)
        for value in (".", "./"):
            self.assertEqual(M.member_name(value, root=True), ".")
            with self.assertRaisesRegex(M.Refusal, "^unsafe-member-name-component$"):
                M.member_name(value)

    def test_stream_and_reference_emit_same_fixed_predicates_without_private_names(self):
        cases = ((b"\n", "type-or-empty"),
            (b"PRIVATE\\name\n", "backslash"), (b"/PRIVATE/name\n", "absolute"),
            (b"PRIVATE\x00name\n", "control"), (b"../PRIVATE/name\n", "component"),
            (("PRIVATE" + "\u00e9" * 510 + "\n").encode(), "utf8-bound"))
        for raw, suffix in cases:
            with self.subTest(suffix=suffix):
                code = "unsafe-member-name-" + suffix
                with self.assertRaisesRegex(M.Refusal, "^" + code + "$"):
                    M.receipt_projection(info(), raw, P)
                stream = M.ReceiptFilesProjection(info(), P)
                with self.assertRaisesRegex(M.Refusal, "^" + code + "$") as failure:
                    for start in range(0, len(raw), 3):
                        stream.feed(raw[start:start + 3])
                    stream.finish()
                self.assertEqual(failure.exception.args, (code,))
                self.assertFalse(stream.finished)

    def test_receipt_colons_are_literal_without_expanding_archive_names(self):
        for value, expected in (("PRIVATE:name", "PRIVATE:name"),
                ("./PRIVATE:name/", "PRIVATE:name"), ("a:b/c:d", "a:b/c:d")):
            with self.subTest(value=value):
                self.assertEqual(M.member_name(value, receipt=True), expected)
                with self.assertRaisesRegex(M.Refusal, "^unsafe-member-name-colon$"):
                    M.member_name(value)
                for context in (False, None, 1, "true"):
                    with self.assertRaisesRegex(M.Refusal, "^unsafe-member-name-colon$"):
                        M.member_name(value, receipt=context)

    def test_receipt_colons_match_reference_at_every_chunk_boundary(self):
        raw = (".\nPRIVATE:name\n" + M.APP_REL + "\n" + M.APP_REL
            + "/Contents/x:y\n" + M.APP_REL + ":other\n").encode()
        expected = M.receipt_projection(info(), raw, P)
        self.assertEqual(expected["path_count"], 5)
        self.assertEqual(expected["lexical_app_claim_count"], 2)
        self.assertEqual(expected["app_alias_claim_count"], 0)
        self.assertEqual(expected["data_namespace_claim_count"], 0)
        self.assertEqual(expected["files_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn("PRIVATE", json.dumps(expected))
        self.assertFalse(expected["receipt_ownership_approval"])
        for boundary in range(len(raw) + 1):
            with self.subTest(boundary=boundary):
                stream = M.ReceiptFilesProjection(info(), P)
                stream.feed(raw[:boundary])
                stream.feed(raw[boundary:])
                stream.finish()
                self.assertEqual(stream.result(), expected)
        metadata = info(**{"install-location": "/PRIVATE:base/"})
        stream = M.ReceiptFilesProjection(metadata, P)
        stream.feed(b".\nchild:name\n")
        stream.finish()
        self.assertEqual(stream.result(), M.receipt_projection(metadata, b".\nchild:name\n", P))
        self.assertEqual(stream.result()["lexical_app_claim_count"], 0)

    def test_receipt_colons_keep_other_path_refusals_before_result(self):
        cases = ((b"../PRIVATE:name\n", "component"),
            (b"/PRIVATE:name\n", "absolute"), (b"PRIVATE:name//x\n", "component"),
            (b"PRIVATE:name\\x\n", "backslash"), (b"PRIVATE:name\x00x\n", "control"),
            (b"PRIVATE:name\x7fx\n", "control"),
            (("PRIVATE:" + "x" * 1017 + "\n").encode(), "utf8-bound"))
        for raw, suffix in cases:
            with self.subTest(suffix=suffix):
                code = "^unsafe-member-name-" + suffix + "$"
                with self.assertRaisesRegex(M.Refusal, code):
                    M.receipt_projection(info(), raw, P)
                stream = M.ReceiptFilesProjection(info(), P)
                with self.assertRaisesRegex(M.Refusal, code):
                    for byte in raw:
                        stream.feed(bytes((byte,)))
                    stream.finish()
                self.assertFalse(stream.finished)

    def test_receipt_colons_keep_case_and_unicode_alias_refusals(self):
        for raw in (b"private:name\nPRIVATE:NAME\n",
                "Caf\u00e9:name\nCafe\u0301:name\n".encode()):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(M.Refusal, "^receipt-path-alias-or-duplicate$"):
                    M.receipt_projection(info(), raw, P)
                stream = M.ReceiptFilesProjection(info(), P)
                with self.assertRaisesRegex(M.Refusal, "^receipt-path-alias-or-duplicate$"):
                    stream.feed(raw)
                    stream.finish()
                self.assertFalse(stream.finished)


if __name__ == "__main__":
    unittest.main(verbosity=2)

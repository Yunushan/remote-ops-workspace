"""Installer-free tests of byte bindings, archive bounds and unsigned evidence."""

from __future__ import annotations

import gzip
import importlib.util
import io
import stat
import struct
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location(
    "unsigned_runtime_observations", ROOT / "scripts/collect_unsigned_runtime.py"
)
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)
checker_spec = importlib.util.spec_from_file_location(
    "runtime_observation_compliance_checker", ROOT / "scripts/check_release_license_compliance.py"
)
checker = importlib.util.module_from_spec(checker_spec)
sys.modules[checker_spec.name] = checker
checker_spec.loader.exec_module(checker)


def tar_bytes(files, *, link=False):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, data in files:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            if link:
                item.type = tarfile.SYMTYPE
                item.linkname = "outside"
                item.size = 0
                archive.addfile(item)
            else:
                archive.addfile(item, io.BytesIO(data))
    return output.getvalue()


def zip_bytes(files, *, mode=stat.S_IFREG | 0o644):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            item = zipfile.ZipInfo(name)
            item.external_attr = mode << 16
            archive.writestr(item, data)
    return output.getvalue()


def ar_bytes(items):
    raw = b"!<arch>\n"
    for name, data in items:
        raw += (
            f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n".encode("ascii")
            + data
        )
        if len(data) % 2:
            raw += b"\n"
    return raw


def carchive(files):
    payload, toc = b"", b""
    for name, data in files:
        encoded = name.encode() + b"\0"
        toc += (
            struct.pack("!iIIIBc", 18 + len(encoded), len(payload), len(data), len(data), 0, b"x")
            + encoded
        )
        payload += data
    cookie = struct.pack(
        "!8sIIII64s",
        c.COOKIE,
        len(payload) + len(toc) + 88,
        len(payload),
        len(toc),
        314,
        b"python314.dll",
    )
    return b"MZharmless-data-only" + payload + toc + cookie


def cpio(files, *, mode=stat.S_IFREG | 0o644, links=1):
    raw = b""
    for name, data in [*files, ("TRAILER!!!", b"")]:
        encoded = name.encode() + b"\0"
        values = [1, mode, 0, 0, links, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
        raw += b"070701" + b"".join(f"{value:08x}".encode() for value in values) + encoded
        raw += b"\0" * (-len(raw) % 4)
        raw += data
        raw += b"\0" * (-len(raw) % 4)
    return raw


def rpm(raw, *, codec=b"gzip"):
    def header(items):
        store, indices = b"", b""
        for tag, value in items:
            indices += struct.pack("!IIII", tag, 6, len(store), 1)
            store += value + b"\0"
        return (
            b"\x8e\xad\xe8\x01"
            + b"\0" * 4
            + struct.pack("!II", len(items), len(store))
            + indices
            + store
        )

    lead = b"\xed\xab\xee\xdb" + b"\0" * 92
    signature = header([])
    return lead + signature + header([(1124, b"cpio"), (1125, codec)]) + gzip.compress(raw)


class RuntimeObservationCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fixture-", dir=HERE)
        self.root = Path(self.temporary.name)
        self.limits = c.Limits(
            input_bytes=1024 * 1024,
            expanded_bytes=4 * 1024 * 1024,
            member_bytes=1024 * 1024,
            retained_license_bytes=8192,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def obs(self):
        return c.Observations(self.limits)

    def refuses(self, code, function, *args):
        with self.assertRaisesRegex(c.Refusal, code):
            function(*args)

    def test_tiny_and_empty_files_do_not_request_the_global_input_limit(self):
        for raw in (b"small tracked source\n", b""):
            with self.subTest(size=len(raw)):
                path = self.root / "source.txt"
                path.write_bytes(raw)
                with path.open("rb") as stream:
                    wrapper = mock.MagicMock()
                    wrapper.__enter__.return_value = wrapper
                    wrapper.fileno.side_effect = stream.fileno

                    read_cap = len(raw) + 1

                    def bounded_read(size, cap=read_cap):
                        self.assertLessEqual(size, cap)
                        return stream.read(size)

                    wrapper.read.side_effect = bounded_read
                    with mock.patch.object(Path, "open", return_value=wrapper):
                        self.assertEqual(c.read(path, c.DEFAULT_LIMITS.input_bytes), raw)

    def test_oversized_input_is_refused_before_opening(self):
        path = self.root / "source.txt"
        path.write_bytes(b"1234")
        with mock.patch.object(Path, "open", side_effect=AssertionError("must not open")):
            self.refuses("input-byte-bound", c.read, path, 3)

    def test_file_growth_and_shrink_during_read_still_refuse(self):
        opening = Path.open
        for changed in (b"12345", b"1"):
            with self.subTest(changed_size=len(changed)):
                path = self.root / "source.txt"
                path.write_bytes(b"1234")
                with opening(path, "rb") as stream:
                    wrapper = mock.MagicMock()
                    wrapper.__enter__.return_value = wrapper
                    wrapper.fileno.side_effect = stream.fileno

                    def changed_read(size, target=path, value=changed):
                        self.assertLessEqual(size, 5)
                        with opening(target, "wb") as writer:
                            writer.write(value)
                        return stream.read(size)

                    wrapper.read.side_effect = changed_read
                    with mock.patch.object(Path, "open", return_value=wrapper):
                        self.refuses("input-changed", c.read, path, c.DEFAULT_LIMITS.input_bytes)

    def test_opened_identity_and_post_read_metadata_changes_still_refuse(self):
        path = self.root / "source.txt"
        path.write_bytes(b"1234")
        before = c.plain(path)
        opened = mock.Mock(st_dev=before.st_dev, st_ino=before.st_ino + 1, st_size=4)
        with mock.patch.object(c.os, "fstat", return_value=opened):
            self.refuses("input-changed", c.read, path, c.DEFAULT_LIMITS.input_bytes)
        changed = mock.Mock(
            st_dev=before.st_dev,
            st_ino=before.st_ino,
            st_size=before.st_size,
            st_mtime_ns=before.st_mtime_ns + 1,
        )
        with mock.patch.object(c, "plain", side_effect=[before, changed]):
            self.refuses("input-changed", c.read, path, c.DEFAULT_LIMITS.input_bytes)

    def fixture(self):
        for name in ("proof", "stage", "site/example-1.2.dist-info", "assets"):
            (self.root / name).mkdir(parents=True)
        metadata = self.root / "site/example-1.2.dist-info"
        (metadata / "METADATA").write_bytes(
            b"Name: example\nVersion: 1.2\nLicense-Expression: UNREVIEWED\n\n"
        )
        (metadata / "LICENSE.txt").write_bytes(b"Actual observed synthetic terms.\n")
        (metadata / "RECORD").write_bytes(
            b"example-1.2.dist-info/METADATA,,\nexample-1.2.dist-info/LICENSE.txt,,\nexample-1.2.dist-info/RECORD,,\n"
        )
        source = self.root / "source.txt"
        source.write_bytes(b"synthetic tracked source\n")
        source_record = {
            "head": "a" * 40,
            "tree": "b" * 40,
            "files": [{"path": "source.txt", "sha256": c.digest(source.read_bytes())}],
        }
        source_record["checkout_bytes_sha256"] = c.digest(
            f"source.txt\0{source_record['files'][0]['sha256']}\n".encode()
        )
        executable = carchive(
            [
                ("LICENSE", b"Actual packaged synthetic terms\n"),
                ("libnative.dll", b"MZharmless-native-data"),
            ]
        )
        (self.root / "stage/row.exe").write_bytes(executable)
        archive_receipt = [
            {"path": "stage/row.exe", "artifact_sha256": c.digest(executable), "toc": []}
        ]
        archive_raw = c.canonical(archive_receipt)
        (self.root / "proof/pyinstaller-archives.json").write_bytes(archive_raw)
        pip = {
            "version": "1",
            "installed": [
                {
                    "metadata": {"name": "example", "version": "1.2"},
                    "metadata_location": str(metadata),
                }
            ],
        }
        pip_raw = c.canonical(pip)
        (self.root / "proof/pip-inspect.json").write_bytes(pip_raw)
        asset = zip_bytes(
            [
                ("docs/LICENSE.txt", b"Actual packaged synthetic terms\n"),
                ("bin/row.exe", executable),
            ]
        )
        (self.root / "assets/native.zip").write_bytes(asset)
        finish = {
            "target": "windows-x64",
            "source": source_record,
            "source_unchanged": True,
            "pip_inspect_returncode": 0,
            "pip_inspect_json_valid": True,
            "pip_inspect_sha256": c.digest(pip_raw),
            "pyinstaller_archive_inventory_sha256": c.digest(archive_raw),
            "assets": [
                {"path": "assets/native.zip", "sha256": c.digest(asset), "size": len(asset)}
            ],
            "repository": "Example/Example",
            "run_id": "12",
            "run_attempt": "1",
        }
        (self.root / "proof/finish.json").write_bytes(c.canonical(finish))
        (self.root / "proof/bind.json").write_bytes(
            c.canonical(
                {
                    "target": "windows-x64",
                    "source": source_record,
                    "python": {"version": "3.14.7 (synthetic fixture)"},
                }
            )
        )
        return finish

    def collect(self):
        return c.collect(
            self.root,
            "windows-x64",
            "a" * 40,
            "proof",
            "stage",
            [self.root / "site"],
            {"version": "3.14.7", "implementation": "CPython", "pointer_bits": 64},
            self.limits,
        )

    def test_actual_windows_receipt_separator_shape_preserves_all_byte_bindings(self):
        finish = self.fixture()
        archive_path = self.root / "proof/pyinstaller-archives.json"
        archives = c.load(archive_path.read_bytes(), array=True)
        archives[0]["path"] = r"stage\row.exe"
        archive_raw = c.canonical(archives)
        archive_path.write_bytes(archive_raw)
        finish["pyinstaller_archive_inventory_sha256"] = c.digest(archive_raw)
        finish["assets"][0]["path"] = r"assets\native.zip"
        (self.root / "proof/finish.json").write_bytes(c.canonical(finish))
        record, _ = self.collect()
        self.assertEqual(record["assets"]["native.zip"]["backend"], "bounded-zip32-deflate")
        self.assertEqual(record["assets"]["native.zip"]["sha256"], finish["assets"][0]["sha256"])
        self.assertIs(record["closed_world_complete"], False)
        bootloader = next(
            row for row in record["components"] if row["origin"] == "pyinstaller-bootloader"
        )
        self.assertEqual(bootloader["carchive_runtime_hints"][0]["reference"], "stage/row.exe")
        self.assertEqual(record["inputs"]["carchive_report_sha256"], c.digest(archive_raw))

    def test_receipt_separator_adaptation_is_typed_and_never_accepts_path_aliases(self):
        self.assertEqual(
            c.receipt_relative(r"native-dist\windows\file.zip", "windows-x64"),
            "native-dist/windows/file.zip",
        )
        for target in ("linux-x86_64", "macos-arm64"):
            self.refuses(
                "receipt-path-separator-invalid", c.receipt_relative, r"assets\native.zip", target
            )
        for value in (
            r"C:\outside.zip",
            r"\\host\share\native.zip",
            r"assets\..\native.zip",
            r"assets/dir\native.zip",
            r"assets\CON.txt",
            r"assets\file.\native.zip",
            r"assets\\native.zip",
            r"\assets\native.zip",
        ):
            with self.subTest(value=value):
                self.refuses(
                    "path-invalid|receipt-path-separator-invalid",
                    c.receipt_relative,
                    value,
                    "windows-x64",
                )
        self.refuses("path-invalid", c.relative, r"assets\native.zip")
        with self.assertRaisesRegex(c.Refusal, "path-invalid"):
            c.relative(r"assets\native.zip", archive=True)

    def test_receipt_source_and_builder_shapes_refuse_public_error_codes(self):
        finish = self.fixture()
        finish_path = self.root / "proof/finish.json"
        bind_path = self.root / "proof/bind.json"
        bind = c.load(bind_path.read_bytes())
        for value in (None, "unrecognized", [], True):
            with self.subTest(value=value):
                finish_path.write_bytes(c.canonical({**finish, "source": value}))
                self.refuses("source-binding-invalid", self.collect)
                finish_path.write_bytes(c.canonical(finish))
                bind_path.write_bytes(c.canonical({**bind, "source": value}))
                self.refuses("source-binding-invalid", self.collect)
                bind_path.write_bytes(c.canonical({**bind, "python": value}))
                self.refuses("actual-builder-runtime-receipt-mismatch", self.collect)
        bind_path.write_bytes(c.canonical(bind))

    def test_nonobject_asset_and_archive_entries_are_refused(self):
        finish = self.fixture()
        finish_path = self.root / "proof/finish.json"
        archive_path = self.root / "proof/pyinstaller-archives.json"
        original_archive = archive_path.read_bytes()
        for value in (None, "unrecognized", [], True):
            with self.subTest(value=value):
                finish_path.write_bytes(c.canonical({**finish, "assets": [value]}))
                self.refuses("asset-binding-invalid", self.collect)
                raw = c.canonical([value])
                archive_path.write_bytes(raw)
                finish_path.write_bytes(
                    c.canonical({**finish, "pyinstaller_archive_inventory_sha256": c.digest(raw)})
                )
                self.refuses("carchive-receipt-shape-invalid", self.collect)
                archive_path.write_bytes(original_archive)
        finish_path.write_bytes(c.canonical(finish))

    def test_archive_receipt_duplicate_fields_are_refused_before_file_read(self):
        finish = self.fixture()
        raw = b'[{"path":"stage/row.exe","path":"outside","artifact_sha256":"' + b"a" * 64 + b'"}]'
        (self.root / "proof/pyinstaller-archives.json").write_bytes(raw)
        finish["pyinstaller_archive_inventory_sha256"] = c.digest(raw)
        (self.root / "proof/finish.json").write_bytes(c.canonical(finish))
        self.refuses("json-duplicate-key", self.collect)

    def test_current_builder_runtime_cannot_impersonate_receipt(self):
        self.fixture()
        self.refuses(
            "actual-builder-runtime-receipt-mismatch",
            c.collect,
            self.root,
            "windows-x64",
            "a" * 40,
            "proof",
            "stage",
            [self.root / "site"],
            {"version": "3.14.4", "implementation": "CPython", "pointer_bits": 64},
            self.limits,
        )

    def test_internal_nul_in_carchive_name_is_rejected(self):
        self.refuses(
            "carchive-name-invalid",
            c.scan_carchive,
            carchive([("LICENSE\0alias", b"terms")]),
            "fixture",
            self.obs(),
        )

    def test_full_fixture_records_own_bytes_and_remains_unapproved(self):
        self.fixture()
        record, blobs = self.collect()
        self.assertEqual(record["decision"], "unapproved")
        for field in (
            "closed_world_complete",
            "classification_complete",
            "artifact_contents_scanned",
            "signed",
        ):
            self.assertIs(record[field], False)
        self.assertTrue(record["all_installed_distributions_recorded"])
        self.assertEqual(
            [row["version"] for row in record["components"] if row["name"] == "example"], ["1.2"]
        )
        self.assertTrue(
            any(
                row["origin"] == "native-component" and row["version"] is None
                for row in record["components"]
            )
        )
        output = self.root / "bundle"
        c.write_new_bundle(output, record, blobs)
        for component in record["components"]:
            for row in component["license_files"]:
                self.assertEqual(checker.check_evidence_file(row, output, "fixture"), [])
                self.assertEqual(checker.valid_license_files([row]), True)
        versions, errors = checker.read_pip_inspect(
            output, record["realized_environment"], "fixture"
        )
        self.assertEqual((versions, errors), ({"example": "1.2"}, []))
        self.assertEqual(len(list((output / "files/licenses").iterdir())), 2)
        errors = checker.check_inventory(
            record,
            manifest_name="fixture",
            profile="secure-cli",
            required_names=[],
            versions={},
            artifact_names={"native.zip"},
            evidence_root=output,
            expected_lock_file="lock.txt",
            expected_lock_sha256="0" * 64,
        )
        self.assertTrue(any("closed_world_complete must be true" in error for error in errors))
        self.assertTrue(any("classification_complete must be true" in error for error in errors))
        self.assertTrue((output / "COMPLETE-OBSERVATIONS-ONLY").is_file())

    def test_exact_asset_digest_required_before_parse(self):
        self.fixture()
        (self.root / "assets/native.zip").write_bytes(b"wrong bytes")
        self.refuses("asset-byte-mismatch", self.collect)

    def test_raw_pip_hash_mismatch_refused(self):
        self.fixture()
        with (self.root / "proof/pip-inspect.json").open("ab") as stream:
            stream.write(b" ")
        self.refuses("pip-inspect-byte-mismatch", self.collect)

    def test_transport_extra_fields_never_enter_retained_public_facts(self):
        finish = self.fixture()
        finish["source"]["private_extra"] = "synthetic-private-marker"
        finish["source"]["files"][0]["private_extra"] = "synthetic-private-marker"
        bind_path = self.root / "proof/bind.json"
        bind = c.load(bind_path.read_bytes())
        bind["source"] = finish["source"]
        bind_path.write_bytes(c.canonical(bind))
        finish_path = self.root / "proof/finish.json"
        finish_path.write_bytes(c.canonical(finish))
        runtime = {
            "version": "3.14.7",
            "implementation": "CPython",
            "pointer_bits": 64,
            "private_extra": "synthetic-private-marker",
        }
        record, blobs = c.collect(
            self.root,
            "windows-x64",
            "a" * 40,
            "proof",
            "stage",
            [self.root / "site"],
            runtime,
            self.limits,
        )
        self.assertNotIn(b"synthetic-private-marker", c.canonical(record))
        self.assertNotIn(b"synthetic-private-marker", b"".join(blobs.values()))
        self.assertEqual(set(record["source_binding"]), {"head", "checkout_bytes_sha256", "files"})
        for field, value in (
            ("repository", "owner/repo?private"),
            ("run_id", True),
            ("run_attempt", "0"),
        ):
            bad = {**finish, field: value}
            finish_path.write_bytes(c.canonical(bad))
            self.refuses("candidate-public-identity-invalid", self.collect)

    def test_current_metadata_inventory_must_match_complete_pip_capture(self):
        self.fixture()
        extra = self.root / "site/extra-2.dist-info"
        extra.mkdir()
        (extra / "METADATA").write_bytes(b"Name: extra\nVersion: 2\n")
        self.refuses("actual-installed-metadata-pip-inventory-mismatch", self.collect)

    def test_source_modified_receipt_refused(self):
        self.fixture()
        (self.root / "source.txt").write_bytes(b"modified")
        self.refuses("source-file-bytes-mismatch", self.collect)

    def test_carchive_executable_changed_refused(self):
        self.fixture()
        (self.root / "stage/row.exe").write_bytes(b"changed executable")
        self.refuses("carchive-executable-byte-mismatch", self.collect)

    def test_existing_output_cannot_be_overwritten(self):
        output = self.root / "bundle"
        output.mkdir()
        (output / "precious.txt").write_bytes(b"preserve")
        self.refuses("output-must-be-new", c.write_new_bundle, output, {}, {})
        self.assertEqual((output / "precious.txt").read_bytes(), b"preserve")

    def test_casefold_duplicate_zip_rejected(self):
        self.refuses(
            "duplicate-member",
            lambda: list(
                c.zip_members(zip_bytes([("LICENSE", b"one"), ("license", b"two")]), self.obs())
            ),
        )

    def test_traversal_and_absolute_zip_rejected(self):
        for name in (
            "../escape",
            "/escape",
            "C:/escape",
            "folder\\escape",
            "CON",
            "folder//escape",
        ):
            with self.subTest(name=name):
                raw = zip_bytes([(name.replace("\\", "/"), b"data")])
                if "\\" in name:
                    raw = raw.replace(name.replace("\\", "/").encode(), name.encode())
                self.refuses("path-invalid", lambda raw=raw: list(c.zip_members(raw, self.obs())))
        self.assertFalse((self.root.parent / "escape").exists())

    def test_symlink_zip_and_tar_never_extract(self):
        self.refuses(
            "link-or-special-member",
            lambda: list(
                c.zip_members(
                    zip_bytes([("LICENSE", b"outside")], mode=stat.S_IFLNK | 0o777), self.obs()
                )
            ),
        )
        self.refuses(
            "link-or-special-member",
            lambda: list(c.tar_members(tar_bytes([("LICENSE", b"")], link=True), self.obs())),
        )

    def test_declared_member_bound_precedes_read(self):
        small = c.Observations(c.Limits(member_bytes=2))
        self.refuses(
            "member-byte-bound", lambda: list(c.zip_members(zip_bytes([("file", b"123")]), small))
        )

    def test_member_count_bound(self):
        small = c.Observations(c.Limits(members=1))
        self.refuses(
            "zip-directory-bound",
            lambda: list(c.zip_members(zip_bytes([("one", b"1"), ("two", b"2")]), small)),
        )

    def test_decompression_bomb_is_bounded(self):
        for method, compressed in (
            ("gzip", gzip.compress(b"x" * 10000)),
            ("xz", __import__("lzma").compress(b"x" * 10000)),
        ):
            with self.subTest(method=method):
                with self.assertRaises(c.Refusal):
                    c.decompressed(compressed, method, 100)

    def test_deb_observes_license_without_execution(self):
        obs = self.obs()
        raw = ar_bytes(
            [
                ("debian-binary", b"2.0\n"),
                (
                    "data.tar.gz",
                    gzip.compress(tar_bytes([("./usr/share/doc/row/LICENSE", b"terms")])),
                ),
            ]
        )
        result = c.scan_package(raw, "row.deb", obs)
        self.assertEqual(result["license_records"][0]["sha256"], c.digest(b"terms"))
        self.assertTrue(result["all_regular_payload_files_observed"])

    def test_rpm_and_cpio_observe_license_without_execution(self):
        obs = self.obs()
        result = c.scan_package(
            rpm(cpio([("./usr/share/doc/row/LICENSE", b"terms")])), "row.rpm", obs
        )
        self.assertEqual(result["license_records"][0]["sha256"], c.digest(b"terms"))
        self.assertEqual(obs.blobs[c.digest(b"terms")], b"terms")

    def test_rpm_zstd_remains_explicit_gap(self):
        self.refuses(
            "rpm-payload-codec-unobserved", c.rpm_payload, rpm(cpio([]), codec=b"zstd"), self.limits
        )

    def test_cpio_links_refused(self):
        self.refuses(
            "link-or-special-member",
            lambda: list(
                c.cpio_members(cpio([("link", b"outside")], mode=stat.S_IFLNK | 0o777), self.obs())
            ),
        )
        self.refuses(
            "cpio-hardlink-unobserved",
            lambda: list(c.cpio_members(cpio([("link", b"data")], links=2), self.obs())),
        )

    def test_carchive_bounds_before_member_decompression(self):
        raw = carchive([("LICENSE", b"terms")])
        corrupted = bytearray(raw)
        cookie = len(raw) - 88
        corrupted[cookie + 8 : cookie + 12] = struct.pack("!I", len(raw) + 100)
        self.refuses(
            "carchive-cookie-invalid", c.scan_carchive, bytes(corrupted), "candidate", self.obs()
        )

    def test_duplicate_pip_distributions_and_bool_size_refused(self):
        item = {"metadata": {"name": "example", "version": "1.2"}}
        self.refuses(
            "distribution-version-or-duplicate-invalid",
            c.inspect_distributions,
            c.canonical({"version": "1", "installed": [item, item]}),
            self.limits,
        )
        self.assertFalse(c.integer(True, 1))

    def test_input_symlink_is_refused(self):
        (self.root / "original").write_bytes(b"terms")
        try:
            (self.root / "link").symlink_to(self.root / "original")
        except OSError:
            self.skipTest("Host cannot create symlink; POSIX run covers this invariant")
        self.refuses("reparse-input", c.read, self.root / "link", 100)

    def test_opaque_installer_never_launches_and_has_no_completion_claim(self):
        for name in (
            "candidate.exe",
            "candidate.msi",
            "candidate.dmg",
            "candidate.pkg",
            "candidate.AppImage",
        ):
            obs = self.obs()
            result = c.scan_package(b"opaque harmless data", name, obs)
            self.assertIs(result["all_regular_payload_files_observed"], False)
            self.assertEqual(obs.gaps[0]["code"], "opaque-package-format-unobserved")

    def test_mandatory_third_party_notices_are_copied(self):
        obs = self.obs()
        obs.observe("docs/THIRD_PARTY_NOTICES.md", b"observed notice", "package", package="package")
        self.assertEqual(obs.licenses["package"][0]["sha256"], c.digest(b"observed notice"))

    def test_concatenated_tar_cannot_hide_second_payload(self):
        raw = tar_bytes([("LICENSE", b"first")]) + tar_bytes([("hidden", b"second")])
        self.refuses(
            "tar-trailing-or-end-block-invalid", lambda: list(c.tar_members(raw, self.obs()))
        )

    def test_gnu_pax_sparse_metadata_are_unobserved(self):
        for format_name in (tarfile.GNU_FORMAT, tarfile.PAX_FORMAT):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w", format=format_name) as archive:
                item = tarfile.TarInfo("a" * 150)
                item.size = 1
                archive.addfile(item, io.BytesIO(b"x"))
            self.refuses(
                "tar-extended-metadata-unobserved",
                lambda output=output: list(c.tar_members(output.getvalue(), self.obs())),
            )
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w", format=tarfile.GNU_FORMAT) as archive:
            item = tarfile.TarInfo("sparse")
            item.type = tarfile.GNUTYPE_SPARSE
            archive.addfile(item)
        self.refuses(
            "tar-extended-metadata-unobserved",
            lambda: list(c.tar_members(output.getvalue(), self.obs())),
        )

    def test_zip_link_with_directory_spelling_is_not_skipped(self):
        raw = zip_bytes([("link/", b"")], mode=stat.S_IFLNK | 0o755)
        self.refuses("link-or-special-member", lambda: list(c.zip_members(raw, self.obs())))

    def test_zip_declared_size_cannot_truncate_actual_payload(self):
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=method) as archive:
                archive.writestr("LICENSE", b"abcde")
            raw = bytearray(output.getvalue())
            central = raw.index(b"PK\x01\x02")
            checksum = __import__("zlib").crc32(b"abc")
            for offset in (14, central + 16):
                struct.pack_into("<I", raw, offset, checksum)
            for offset in (22, central + 24):
                struct.pack_into("<I", raw, offset, 3)
            with self.assertRaises(c.Refusal):
                list(c.zip_members(bytes(raw), self.obs()))

    def test_zip_actual_count_must_match_declared_before_data_reads(self):
        raw = bytearray(zip_bytes([("one", b"1"), ("two", b"2")]))
        end = raw.rindex(b"PK\x05\x06")
        struct.pack_into("<HH", raw, end + 8, 1, 1)
        self.refuses(
            "zip-directory-count-mismatch", lambda: list(c.zip_members(bytes(raw), self.obs()))
        )

    def test_zip_unaccounted_directory_trailer_is_refused(self):
        raw = zip_bytes([("LICENSE", b"terms")])
        end = raw.rindex(b"PK\x05\x06")
        self.refuses(
            "zip-directory-bound-or-zip64-unobserved",
            lambda: list(c.zip_members(raw[:end] + b"hidden" + raw[end:], self.obs())),
        )

    def test_zip_local_only_alias_link_zip64_extras_are_unobserved(self):
        original = zip_bytes([("LICENSE", b"terms")])
        name_size = struct.unpack_from("<H", original, 26)[0]
        insertion = 30 + name_size
        for tag in (0x7075, 0x000D, 0x0001):
            extra = struct.pack("<HH", tag, 1) + b"x"
            raw = bytearray(original[:insertion] + extra + original[insertion:])
            struct.pack_into("<H", raw, 28, len(extra))
            end = raw.rindex(b"PK\x05\x06")
            old_offset = struct.unpack_from("<I", raw, end + 16)[0]
            struct.pack_into("<I", raw, end + 16, old_offset + len(extra))
            self.refuses(
                "zip-extra-semantics-unobserved",
                lambda raw=raw: list(c.zip_members(bytes(raw), self.obs())),
            )

    def test_deb_final_odd_member_requires_padding(self):
        raw = ar_bytes([("debian-binary", b"2.0\n"), ("data.tar", b"x")])
        self.refuses("deb-ar-padding-invalid", c.deb_tar, raw[:-1], self.obs())

    def test_global_node_and_gap_budget_fail_entire_capture(self):
        self.fixture()
        self.refuses(
            "global-inventory-node-bound",
            c.collect,
            self.root,
            "windows-x64",
            "a" * 40,
            "proof",
            "stage",
            [self.root / "site"],
            {"version": "3.14.7", "implementation": "CPython", "pointer_bits": 64},
            c.Limits(members=3),
        )
        obs = c.Observations(c.Limits(gaps=1))
        obs.gap("one", "fixture")
        self.refuses("global-gap-count-bound", obs.gap, "two", "fixture")

    def test_global_stage_byte_budget_is_not_a_partial_success(self):
        self.fixture()
        self.refuses(
            "expanded-byte-bound",
            c.collect,
            self.root,
            "windows-x64",
            "a" * 40,
            "proof",
            "stage",
            [self.root / "site"],
            {"version": "3.14.7", "implementation": "CPython", "pointer_bits": 64},
            c.Limits(expanded_bytes=80),
        )

    def test_unreadable_directory_cannot_be_silently_omitted(self):
        with mock.patch.object(
            c.os, "scandir", side_effect=PermissionError("private-example-data")
        ):
            self.refuses(
                "stage-directory-unreadable",
                lambda: list(c.walk_files(self.root, self.obs(), "fixture", permit_gaps=True)),
            )

    def test_credential_bearing_or_unknown_pip_transport_is_refused(self):
        item = {"metadata": {"name": "example", "version": "1.2"}}
        for url in (
            "https://name:password@example.invalid/archive",
            "https://example.invalid/archive?access_token=value",
            "https://example.invalid/archive?opaque=value",
            "https://example.invalid/archive#opaque",
        ):
            value = {**item, "direct_url": {"url": url}}
            self.refuses(
                "pip-url-credential-refused",
                c.inspect_distributions,
                c.canonical({"version": "1", "installed": [value]}),
                self.limits,
            )
        self.refuses(
            "pip-public-schema-unrecognized",
            c.inspect_distributions,
            c.canonical({"version": "1", "installed": [item], "private_secret": "value"}),
            self.limits,
        )

    def test_direct_source_origin_requires_exact_bound_checkout(self):
        item = {
            "metadata": {"name": "example", "version": "1.2"},
            "direct_url": {"url": self.root.as_uri(), "dir_info": {"editable": False}},
        }
        raw = c.canonical({"version": "1", "installed": [item]})
        self.assertEqual(c.inspect_distributions(raw, self.limits, self.root)[0]["name"], "example")
        self.refuses(
            "pip-direct-url-source-root-mismatch",
            c.inspect_distributions,
            raw,
            self.limits,
            self.root / "other",
        )
        item["direct_url"] = {
            "url": "https://example.invalid/archive",
            "archive_info": {"hashes": {"sha256": "a" * 64}},
        }
        self.refuses(
            "pip-direct-url-origin-unobserved",
            c.inspect_distributions,
            c.canonical({"version": "1", "installed": [item]}),
            self.limits,
            self.root,
        )

    def test_local_capture_cli_is_refused_before_reading_inputs(self):
        with (
            mock.patch.dict(c.os.environ, {"GITHUB_ACTIONS": "false"}, clear=True),
            mock.patch.object(c, "collect") as capture,
        ):
            self.assertEqual(
                c.main(
                    [
                        "--target",
                        "windows-x64",
                        "--sha",
                        "a" * 40,
                        "--proof-dir",
                        "missing",
                        "--stage-dir",
                        "missing",
                        "--output",
                        "missing",
                    ]
                ),
                1,
            )
            capture.assert_not_called()


class ReviewedPublicMetadataAnchorTests(unittest.TestCase):
    # Exact public token from source-bound pip bytes; independently matched to
    # https://pypi.org/pypi/cffi/2.1.1/json, not invented by the fixture.
    KNOWN = "https://groups.google.com/forum/#!forum/python-cffi"

    def test_exact_anchor_is_metadata_only_and_preserves_url(self):
        parsed = c.public_metadata_url(self.KNOWN, "cffi", "2.1.1", "project_url")
        self.assertEqual(parsed.geturl(), self.KNOWN)
        raw = c.canonical(
            {
                "version": "1",
                "installed": [
                    {
                        "metadata": {
                            "name": "cffi",
                            "version": "2.1.1",
                            "project_url": ["Discussion, " + self.KNOWN],
                        }
                    }
                ],
            }
        )
        self.assertEqual(c.inspect_distributions(raw, c.DEFAULT_LIMITS)[0]["name"], "cffi")
        with self.assertRaisesRegex(c.Refusal, "pip-url-credential-refused"):
            c.public_url(self.KNOWN)
        with self.assertRaisesRegex(c.Refusal, "pip-url-credential-refused"):
            c.validate_direct_url({"url": self.KNOWN, "dir_info": {}}, ROOT)

    def test_unknown_context_or_modified_anchor_still_refuses(self):
        cases = [
            (self.KNOWN, "different", "2.1.1", "project_url"),
            (self.KNOWN, "cffi", "2.1.2", "project_url"),
            (self.KNOWN, "cffi", "2.1.1", "home_page"),
            (self.KNOWN + "-different", "cffi", "2.1.1", "project_url"),
            (self.KNOWN.partition("#")[0] + "?secret=value#anchor", "cffi", "2.1.1", "project_url"),
            (self.KNOWN.replace("://", "://user:secret@", 1), "cffi", "2.1.1", "project_url"),
        ]
        for value, name, version, field in cases:
            with self.subTest(name=name, version=version, field=field):
                with self.assertRaisesRegex(c.Refusal, "pip-url-credential-refused"):
                    c.public_metadata_url(value, name, version, field)

    def test_even_an_accidentally_reviewed_credential_url_refuses(self):
        secret = self.KNOWN.replace("://", "://user:secret@", 1)
        with mock.patch.dict(
            c.REVIEWED_METADATA_URL_SHA256,
            {("cffi", "2.1.1", "project_url"): c.digest(secret.encode())},
        ):
            with self.assertRaisesRegex(c.Refusal, "pip-url-credential-refused"):
                c.public_metadata_url(secret, "cffi", "2.1.1", "project_url")


class WindowsCArchiveRepresentationTests(unittest.TestCase):
    # Exact source-bound TOC names only; these fixtures contain harmless synthetic
    # payloads and do not replay downloaded native executables.
    ACTUAL_NAMES = (
        "remote_ops_workspace-1.0.27.dist-info\\INSTALLER",
        "remote_ops_workspace-1.0.27.dist-info\\METADATA",
        "remote_ops_workspace-1.0.27.dist-info\\RECORD",
        "remote_ops_workspace-1.0.27.dist-info\\REQUESTED",
        "remote_ops_workspace-1.0.27.dist-info\\WHEEL",
        "remote_ops_workspace-1.0.27.dist-info\\direct_url.json",
        "remote_ops_workspace-1.0.27.dist-info\\entry_points.txt",
        "remote_ops_workspace-1.0.27.dist-info\\licenses\\LICENSE",
        "remote_ops_workspace-1.0.27.dist-info\\licenses\\NOTICE",
        "remote_ops_workspace-1.0.27.dist-info\\top_level.txt",
        "remote_ops_workspace\\assets\\remote_ops_workspace.ico",
        "remote_ops_workspace\\assets\\remote_ops_workspace.svg",
        "remote_ops_workspace\\assets\\remote_ops_workspace_gui.manifest",
        "remote_ops_workspace\\configs\\feature_manifest.json",
        "remote_ops_workspace\\configs\\gui_parity_criteria.json",
        "remote_ops_workspace\\configs\\gui_visual_metrics.json",
        "remote_ops_workspace\\configs\\gui_visual_reference_overrides.json",
        "remote_ops_workspace\\configs\\mobaxterm_parity_evidence.json",
        "remote_ops_workspace\\configs\\mobile_test_matrix.json",
        "remote_ops_workspace\\configs\\native_installer_smoke.json",
        "remote_ops_workspace\\configs\\native_linux_previous_release_pins.json",
        "remote_ops_workspace\\configs\\native_previous_release_pins.json",
        "remote_ops_workspace\\configs\\platform_parity_promotion.json",
        "remote_ops_workspace\\configs\\platform_targets.json",
        "remote_ops_workspace\\configs\\platform_verified_evidence.json",
        "remote_ops_workspace\\configs\\profiles.example.json",
        "remote_ops_workspace\\configs\\release_compliance_policy.json",
        "remote_ops_workspace\\configs\\release_dependency_locks.json",
        "remote_ops_workspace\\configs\\release_matrix.json",
        "remote_ops_workspace\\configs\\release_toolchain.json",
        "remote_ops_workspace\\configs\\security_baseline.json",
        "remote_ops_workspace\\configs\\settings.example.json",
        "remote_ops_workspace\\configs\\workspace_recovery_fixture.json",
        "remote_ops_workspace\\configs\\xp_native_evidence_contract.json",
        "remote_ops_workspace\\py.typed",
        "remote_ops_workspace\\web\\app.js",
        "remote_ops_workspace\\web\\index.html",
        "remote_ops_workspace\\web\\manifest.json",
        "remote_ops_workspace\\web\\styles.css",
        "remote_ops_workspace\\web\\sw.js",
    )

    def test_actual_names_observed_in_direct_and_nested_windows_carchive(self):
        data = carchive([(name, b"harmless") for name in self.ACTUAL_NAMES])
        for target in ("windows-x86", "windows-x64", "windows-arm64"):
            for backend in ("direct", "zip", "tar"):
                with self.subTest(target=target, backend=backend):
                    observations = c.Observations(c.DEFAULT_LIMITS, target=target)
                    if backend == "direct":
                        c.scan_carchive(data, "row.exe", observations)
                    else:
                        raw = (
                            zip_bytes([("row.exe", data)])
                            if backend == "zip"
                            else tar_bytes([("row.exe", data)])
                        )
                        c.scan_package(raw, "bundle." + backend, observations)
                    observed = {
                        row["path"]
                        for row in observations.files
                        if row["path"].startswith("carchive/")
                    }
                    self.assertEqual(
                        observed,
                        {"carchive/" + name.replace("\\", "/") for name in self.ACTUAL_NAMES},
                    )

    def test_other_targets_and_other_archive_formats_keep_strict_paths(self):
        data = carchive([(self.ACTUAL_NAMES[0], b"harmless")])
        for target in (None, "linux-x86_64", "macos-arm64"):
            with self.subTest(target=target):
                with self.assertRaisesRegex(c.Refusal, "path-invalid"):
                    c.scan_carchive(data, "row", c.Observations(c.DEFAULT_LIMITS, target=target))
        for backend, data in (
            (
                "zip",
                zip_bytes([("folder/license.txt", b"license")]).replace(
                    b"folder/license.txt", b"folder\\license.txt"
                ),
            ),
            ("tar", tar_bytes([(r"folder\license.txt", b"license")])),
        ):
            with self.subTest(backend=backend):
                with self.assertRaisesRegex(c.Refusal, "path-invalid"):
                    c.scan_package(
                        data,
                        "bundle." + backend,
                        c.Observations(c.DEFAULT_LIMITS, target="windows-x64"),
                    )

    def test_windows_traversal_devices_mixed_and_duplicate_aliases_refuse(self):
        invalid = [
            r"dir\..\file",
            r"C:\dir\file",
            r"\server\share\file",
            r"dir\NUL",
            "dir\\name.",
            "dir\\file ",
            r"dir\\file",
        ]
        for name in invalid:
            with self.subTest(name=name):
                with self.assertRaisesRegex(c.Refusal, "path-invalid"):
                    c.scan_carchive(
                        carchive([(name, b"harmless")]),
                        "row.exe",
                        c.Observations(c.DEFAULT_LIMITS, target="windows-x64"),
                    )
        with self.assertRaisesRegex(c.Refusal, "carchive-member-separator-invalid"):
            c.scan_carchive(
                carchive([(r"dir\sub/file", b"harmless")]),
                "row.exe",
                c.Observations(c.DEFAULT_LIMITS, target="windows-x64"),
            )
        with self.assertRaisesRegex(c.Refusal, "duplicate-member"):
            c.scan_carchive(
                carchive([(r"dir\file", b"one"), ("DIR/file", b"two")]),
                "row.exe",
                c.Observations(c.DEFAULT_LIMITS, target="windows-x64"),
            )

    def test_dependency_descriptor_is_gap_and_never_followed_as_file(self):
        raw = bytearray(carchive([("unobserved:dependency", b"")]))
        position = bytes(raw).rfind(c.COOKIE)
        _, length, toc_offset, _, _, _ = struct.unpack("!8sIIII64s", raw[position : position + 88])
        start = position + 88 - length
        raw[start + toc_offset + 17] = ord("d")
        observations = c.Observations(c.DEFAULT_LIMITS, target="windows-x64")
        c.scan_carchive(bytes(raw), "row.exe", observations)
        self.assertEqual(observations.files, [])
        self.assertTrue(
            any(row["code"] == "carchive-indirection-unobserved" for row in observations.gaps)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import copy as _gui_pyz_copy
import importlib.util
import json as _gui_pyz_json
import unittest as _gui_pyz_unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("gui_pyz_checker", Path(__file__).resolve().parents[1] / "scripts/candidate_native_proof.py")
_CHECKER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CHECKER)
_GUI_PYZ_VALIDATE = _CHECKER.validate_gui_pyz_modules
_GUI_PYZ_MODULES = _CHECKER.GUI_PYZ_REQUIRED_MODULES
_GUI_PYZ_PATHS = _CHECKER.GUI_PYZ_ARCHIVE_PATHS
_GUI_PYZ_CLI_PATHS = _CHECKER.GUI_PYZ_CLI_ARCHIVE_PATHS


def _gui_pyz_archive_fixture(target="windows-x64"):
    return {
        "path": _GUI_PYZ_PATHS[target],
        "artifact_sha256": "a" * 64,
        "toc": [{"name": "PYZ.pyz", "toc": [100, 500, 500, 0, "z"], "sha256": "b" * 64}],
        "pyz_toc": {module: [0, 17 + index * 100, 50] for index, module in enumerate(_GUI_PYZ_MODULES)},
    }


class TestRequiredGuiPyzModules(_gui_pyz_unittest.TestCase):
    def test_all_gui_targets_require_the_fixed_four_modules(self):
        self.assertEqual(
            _GUI_PYZ_MODULES,
            (
                "remote_ops_workspace.gui_terminal",
                "remote_ops_workspace.gui_processes",
                "remote_ops_workspace.gui_values",
                "remote_ops_workspace.terminal_output",
            ),
        )
        for target in ("windows-x64", "windows-arm64", "macos-x64", "macos-arm64"):
            with self.subTest(target=target):
                report = _GUI_PYZ_VALIDATE([_gui_pyz_archive_fixture(target)], target)
                self.assertEqual(report["status"], "passed")
                self.assertEqual(report["role"], "gui")
                self.assertEqual(report["path"], _GUI_PYZ_PATHS[target])
                self.assertEqual(report["required_modules"], list(_GUI_PYZ_MODULES))
                self.assertEqual(report["observed_presence"], dict.fromkeys(_GUI_PYZ_MODULES, True))
                self.assertEqual(report["errors"], [])

    def test_cli_only_targets_have_no_new_archive_or_gui_requirement(self):
        for target in ("windows-x86", "linux-x86_64", "linux-aarch64"):
            with self.subTest(target=target):
                report = _GUI_PYZ_VALIDATE(None, target)
                self.assertEqual(report["status"], "not-required")
                self.assertIsNone(report["role"])
                self.assertIsNone(report["path"])
                self.assertEqual(report["required_modules"], [])
                self.assertEqual(report["observed_presence"], {})
                self.assertEqual(report["errors"], [])

    def test_each_missing_module_fails_even_when_the_other_three_are_present(self):
        for module in _GUI_PYZ_MODULES:
            with self.subTest(module=module):
                archive = _gui_pyz_archive_fixture()
                del archive["pyz_toc"][module]
                report = _GUI_PYZ_VALIDATE([archive], "windows-x64")
                self.assertEqual(report["status"], "failed")
                self.assertFalse(report["observed_presence"][module])
                self.assertIn("required-gui-module-missing:" + module, report["errors"])

    def test_cli_or_lookalike_archive_cannot_satisfy_the_gui_role(self):
        paths = (
            "build/native/windows/pyinstaller-dist/row.exe",
            "build/native/old-windows/pyinstaller-dist/row-gui.exe",
            "build/native/windows/pyinstaller-dist/nested/row-gui.exe",
            "build/native/windows/pyinstaller-dist/./row-gui.exe",
            "build/native/macos/pyinstaller-dist/Remote Ops Workspace",
        )
        for path in paths:
            with self.subTest(path=path):
                archive = _gui_pyz_archive_fixture()
                archive["path"] = path
                report = _GUI_PYZ_VALIDATE([archive], "windows-x64")
                self.assertEqual(report["status"], "failed")
                self.assertIn("expected-gui-archive-not-unique", report["errors"])

    def test_canonical_gui_wins_over_unrelated_cli_but_duplicate_gui_fails(self):
        gui = _gui_pyz_archive_fixture()
        cli = _gui_pyz_copy.deepcopy(gui)
        cli["path"] = "build/native/windows/pyinstaller-dist/row.exe"
        cli["pyz_toc"] = {}
        self.assertEqual(_GUI_PYZ_VALIDATE([cli, gui], "windows-x64")["status"], "passed")
        duplicate = _gui_pyz_copy.deepcopy(gui)
        duplicate["path"] = duplicate["path"].replace("/", "\\")
        report = _GUI_PYZ_VALIDATE([gui, duplicate], "windows-x64")
        self.assertEqual(report["status"], "failed")
        self.assertIn("expected-gui-archive-not-unique", report["errors"])
        self.assertEqual(_GUI_PYZ_VALIDATE([duplicate], "windows-x64")["status"], "passed")

    def test_macos_requires_the_app_stage_executable(self):
        archive = _gui_pyz_archive_fixture("macos-arm64")
        archive["path"] = "build/native/macos/pyinstaller-dist/Remote Ops Workspace"
        self.assertEqual(_GUI_PYZ_VALIDATE([archive], "macos-arm64")["status"], "failed")
        archive["path"] = _GUI_PYZ_PATHS["windows-arm64"]
        self.assertEqual(_GUI_PYZ_VALIDATE([archive], "macos-arm64")["status"], "failed")

    def test_malformed_inventory_hash_and_archive_tocs_fail(self):
        for inventory in (None, {}, "archive", [None]):
            with self.subTest(inventory=inventory):
                self.assertEqual(_GUI_PYZ_VALIDATE(inventory, "windows-x64")["status"], "failed")
        mutations = (
            ("inventory_error", "PRIVATE-INVENTORY-PAYLOAD"),
            ("inventory_error", None),
            ("artifact_sha256", "a" * 63),
            ("artifact_sha256", "g" * 64),
            ("artifact_sha256", True),
            ("toc", []),
            ("toc", {}),
            ("toc", [None]),
            ("toc", [{"name": "other"}]),
            ("toc", [{"name": "PYZ.pyz"}, {"name": "PYZ.pyz"}]),
            ("pyz_toc", {}),
            ("pyz_toc", []),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                archive = _gui_pyz_archive_fixture()
                archive[field] = value
                report = _GUI_PYZ_VALIDATE([archive], "windows-x64")
                self.assertEqual(report["status"], "failed")
                self.assertTrue(report["errors"])

    def test_pyz_entries_require_plain_integer_module_position_and_length(self):
        entries = (
            None, {}, (0, 17, 50), [0, 17], [0, 17, 50, 1],
            [False, 17, 50], [0, True, 50], [0, 17, True],
            ["0", 17, 50], [0, "17", 50], [0, 17, "50"],
            [1, 17, 50], [3, 17, 50], [0, 0, 50], [0, -1, 50], [0, 17, 0], [0, 17, -1],
        )
        for module in _GUI_PYZ_MODULES:
            for entry in entries:
                with self.subTest(module=module, entry=entry):
                    archive = _gui_pyz_archive_fixture()
                    archive["pyz_toc"][module] = entry
                    report = _GUI_PYZ_VALIDATE([archive], "windows-x64")
                    self.assertEqual(report["status"], "failed")
                    self.assertTrue(report["observed_presence"][module])
                    self.assertIn("required-gui-pyz-entry-malformed:" + module, report["errors"])

    def test_projection_contains_only_the_bounded_public_fields(self):
        archive = _gui_pyz_archive_fixture()
        archive["artifact_sha256"] = "A" * 64
        archive["pyz_toc"]["unrelated.module"] = "PRIVATE-EXTRA-PAYLOAD"
        archive["private_detail"] = "PRIVATE-ARCHIVE-PAYLOAD"
        report = _GUI_PYZ_VALIDATE([archive], "windows-x64")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["artifact_sha256"], "a" * 64)
        self.assertEqual(set(report), {
            "schema_version", "status", "scope", "role", "path", "artifact_sha256",
            "required_modules", "observed_presence", "errors",
            "cli_observations",
        })
        self.assertNotIn("PRIVATE-", _gui_pyz_json.dumps(report))
        self.assertIn("no compiled/source byte comparison", report["scope"])

    def test_cli_presence_is_observed_without_requiring_gui_modules_or_qt(self):
        for target, path in _GUI_PYZ_CLI_PATHS.items():
            for present in (False, True):
                with self.subTest(target=target, present=present):
                    cli = {"path": path, "artifact_sha256": "d" * 64, "toc": [{"name": "PYZ.pyz"}], "pyz_toc": {module: [0, 1, 1] for module in _GUI_PYZ_MODULES} if present else {}}
                    archives = [cli]
                    if target in _GUI_PYZ_PATHS:
                        archives.append(_gui_pyz_archive_fixture(target))
                    report = _GUI_PYZ_VALIDATE(archives, target)
                    self.assertEqual(report["status"], "passed" if target in _GUI_PYZ_PATHS else "not-required")
                    self.assertEqual(report["cli_observations"], [{"role": "cli", "path": path, "artifact_sha256": "d" * 64, "gui_modules_required": False, "observed_presence": dict.fromkeys(_GUI_PYZ_MODULES, present)}])

    def test_unknown_target_cannot_inherit_a_cli_only_exemption(self):
        for target in ("windows-next", "linux-next", "", None, []):
            with self.subTest(target=target):
                report = _GUI_PYZ_VALIDATE([], target)
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["errors"], ["unsupported-native-target"])


def test_actual_finish_refuses_missing_gui_module_after_other_mock_gates_pass(tmp_path, monkeypatch):
    import sys
    import types

    import pytest

    proof = _CHECKER
    source = {"head": "a" * 40, "tree": "b" * 40, "checkout_bytes_sha256": "c" * 64}
    output = tmp_path / "build/candidate-proof/windows-x64"
    output.mkdir(parents=True)
    proof.save(output / "bind.json", {"source": source})
    project = tmp_path / "src/remote_ops_workspace/__init__.py"
    project.parent.mkdir(parents=True)
    project.write_bytes(b"# never imported source fixture\n")
    stage = tmp_path / "build/native/windows/pyinstaller-dist"
    stage.mkdir(parents=True)
    for name in ("row.exe", "row-gui.exe"):
        (stage / name).write_bytes(b"inert executable bytes; never launched")
    binding_path = tmp_path / "build/native-smoke/windows-x64/candidate-runtime-byte-binding.json"
    binding_path.parent.mkdir(parents=True)
    binding_path.write_bytes(b"{}")

    def archive(path):
        value = _gui_pyz_archive_fixture()
        value["path"] = path.relative_to(tmp_path).as_posix()
        if path.name == "row-gui.exe":
            del value["pyz_toc"][_GUI_PYZ_MODULES[0]]
        return value

    monkeypatch.setattr(proof, "ROOT", tmp_path)
    monkeypatch.setattr(proof, "fingerprint", lambda: source)
    monkeypatch.setattr(proof, "archive_inventory", archive)
    monkeypatch.setattr(proof, "validate_windows_byte_binding", lambda *_args: None)
    monkeypatch.setattr(proof.importlib.util, "find_spec", lambda *_args: types.SimpleNamespace(origin=str(project)))
    monkeypatch.setattr(proof.importlib.metadata, "distributions", lambda: [])
    monkeypatch.setattr(proof.subprocess, "run", lambda *_args, **_kwargs: types.SimpleNamespace(returncode=0, stdout=b'{"installed":[]}', stderr=b""))
    monkeypatch.setattr(sys, "argv", ["proof.py", "finish", "--target", "windows-x64", "--expected-sha", source["head"], "--asset-dir", "native-dist/windows", "--native-build-outcome", "success", "--native-smoke-outcome", "success"])
    with pytest.raises(RuntimeError, match="PyInstaller inventories"):
        proof.main()
    finish = _gui_pyz_json.loads((output / "finish.json").read_text())
    assert finish["native_executable_byte_binding"]["status"] == "bound"
    assert finish["source_unchanged"] is True
    assert finish["installed_project_sources_match_checkout"] is True
    assert finish["native_pyinstaller_inventory_complete"] is False
    assert finish["required_gui_pyz_modules"]["status"] == "failed"
    assert "required-gui-module-missing:" + _GUI_PYZ_MODULES[0] in finish["required_gui_pyz_modules"]["errors"]

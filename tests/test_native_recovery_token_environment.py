"""Pure AST/mock test of the native child environment, without helper imports."""

import ast
import types
import unittest
from pathlib import Path, PurePosixPath


def isolated_clean_environment(parent_environment):
    source = Path(__file__).resolve().parents[1] / "scripts/native_installer_recovery.py"
    tree = ast.parse(source.read_bytes(), filename=str(source))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "clean_environment"
    ]
    if len(functions) != 1:
        raise AssertionError("clean environment definition is ambiguous")
    module = ast.Module(body=functions, type_ignores=[])
    namespace = {"os": types.SimpleNamespace(environ=parent_environment), "Path": Path}
    exec(compile(module, "<native-clean-environment-ast>", "exec"), namespace)
    return namespace["clean_environment"]


class NativeRecoveryTokenEnvironmentTests(unittest.TestCase):
    def test_parent_read_tokens_are_removed_only_from_the_child_environment(self):
        parent = {
            "GITHUB_TOKEN": "synthetic-parent-read-token",
            "github_token": "synthetic-lower-github-token",
            "gItHuB_tOkEn": "synthetic-mixed-github-token",
            "GH_TOKEN": "synthetic-parent-gh-token",
            "gh_token": "synthetic-lower-gh-token",
            "gH_tOkEn": "synthetic-mixed-gh-token",
            "PYTHONPATH": "synthetic-python-path",
            "pythonhome": "synthetic-python-home",
            "rOw_HoMe": "synthetic-inherited-home",
            "ROW_VAULT_PASSWORD": "synthetic-inherited-vault-password",
            "row_recovery_password": "synthetic-inherited-backup-password",
            "qt_qpa_platform": "synthetic-qt-platform",
            "PATH": "synthetic-executable-path",
            "Path": "synthetic-case-preserved-path",
            "UNRELATED_TOKEN": "synthetic-unrelated-value",
            "UNCHANGED_VALUE": "synthetic-preserved-value",
        }
        before = dict(parent)
        clean = isolated_clean_environment(parent)
        home = PurePosixPath("/synthetic-owned-recovery-home")
        child = clean(home, "synthetic-new-vault-password", "synthetic-new-backup-password")
        self.assertEqual(
            child,
            {
                "PATH": "synthetic-executable-path",
                "Path": "synthetic-case-preserved-path",
                "UNRELATED_TOKEN": "synthetic-unrelated-value",
                "UNCHANGED_VALUE": "synthetic-preserved-value",
                "ROW_HOME": str(home),
                "ROW_VAULT_PASSWORD": "synthetic-new-vault-password",
                "ROW_RECOVERY_PASSWORD": "synthetic-new-backup-password",
            },
        )
        self.assertFalse(any(name.upper() in {"GITHUB_TOKEN", "GH_TOKEN"} for name in child))
        self.assertEqual(parent, before)
        self.assertIsNot(child, parent)
        self.assertEqual(parent["GITHUB_TOKEN"], "synthetic-parent-read-token")
        self.assertEqual(parent["GH_TOKEN"], "synthetic-parent-gh-token")


if __name__ == "__main__":
    unittest.main(verbosity=2)

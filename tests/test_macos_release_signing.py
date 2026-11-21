from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASH = shutil.which("bash") if os.name != "nt" else None
pytestmark = pytest.mark.skipif(BASH is None, reason="requires native Bash")


@pytest.fixture
def run_macos_signing(tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    wrapper = scripts / "with_macos_release_signing.sh"
    shutil.copyfile(Path("scripts") / wrapper.name, wrapper)
    tools = tmp_path / "tools"
    tools.mkdir()
    shim = tools / "apple-tool"
    shim.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "tool = Path(sys.argv[0]).name\n"
        "args = sys.argv[1:]\n"
        "operation = tool\n"
        "if tool == 'xcrun':\n"
        "    operation += '/' + '/'.join(args[:2] if args[0] == 'notarytool' else args[:1])\n"
        "elif tool in {'security', 'codesign'}:\n"
        "    operation += '/' + args[0]\n"
        "with open(os.environ['ROW_TEST_LOG'], 'a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps([operation, *args]) + '\\n')\n"
        "if operation == os.environ['ROW_TEST_FAILURE']:\n"
        "    raise SystemExit(7)\n"
        "if operation in {'security/create-keychain', 'xcrun/clang', 'pkgbuild', 'productsign'}:\n"
        "    Path(args[-1]).write_bytes(b'disposable fixture')\n"
        "if operation == 'security/import':\n"
        "    assert Path(args[1]).read_bytes() == b'fixture certificate'\n"
        "if operation == 'xcrun/notarytool/store-credentials':\n"
        "    assert Path(args[args.index('--key') + 1]).read_bytes() == b'fixture notary key'\n"
        "if operation == 'xcrun/notarytool/history':\n"
        "    print('fixture notary history')\n"
        "if tool == 'pkgutil':\n"
        "    assert Path(args[-1]).is_file()\n"
        "if operation == 'security/delete-keychain':\n"
        "    Path(args[1]).unlink()\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    for tool in ("security", "xcrun", "codesign", "pkgbuild", "productsign", "pkgutil"):
        (tools / tool).symlink_to(shim)
    (scripts / "make_macos_native.sh").write_text(
        "set -euo pipefail\n"
        'test "$ROW_REQUIRE_RELEASE_SIGNING" = 1\n'
        'test "$ROW_MACOS_NOTARY_PROFILE" = remote-ops-notary\n'
        'test -f "$ROW_MACOS_SIGNING_KEYCHAIN"\n'
        'test ! -e "$(dirname "$ROW_MACOS_SIGNING_KEYCHAIN")/release.p12"\n'
        'test ! -e "$(dirname "$ROW_MACOS_SIGNING_KEYCHAIN")/AuthKey.p8"\n'
        'test -z "${ROW_MACOS_CERTIFICATE_BASE64:-}${ROW_MACOS_CERTIFICATE_PASSWORD:-}${ROW_MACOS_NOTARY_KEY_BASE64:-}"\n'
        'printf \'["build", "%s"]\\n\' "$ROW_MACOS_SIGNING_KEYCHAIN" >> "$ROW_TEST_LOG"\n'
        'test "$ROW_TEST_FAILURE" != build\n',
        encoding="utf-8",
    )
    scratch = tmp_path / "runner-temp"
    scratch.mkdir()
    log = tmp_path / "commands.jsonl"
    environment = {
        **os.environ,
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(scratch),
        "ROW_TEST_LOG": str(log),
        "ROW_MACOS_CERTIFICATE_BASE64": base64.b64encode(b"fixture certificate").decode(),
        "ROW_MACOS_CERTIFICATE_PASSWORD": 'fixture "password"',
        "ROW_MACOS_SIGN_IDENTITY": "Application fixture",
        "ROW_MACOS_INSTALLER_SIGN_IDENTITY": "Installer fixture",
        "ROW_MACOS_NOTARY_KEY_BASE64": base64.b64encode(b"fixture notary key").decode(),
        "ROW_MACOS_NOTARY_KEY_ID": "FIXTURE",
        "ROW_MACOS_NOTARY_ISSUER": "fixture-issuer",
    }

    def run(mode: str, *, failure: str = "", **overrides: str):
        result = subprocess.run(
            [BASH, str(wrapper), mode], cwd=tmp_path, env=environment | {"ROW_TEST_FAILURE": failure} | overrides,
            capture_output=True, text=True, timeout=30, check=False,
        )
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        assert not list(scratch.iterdir())
        assert environment["ROW_MACOS_CERTIFICATE_PASSWORD"] not in result.stdout + result.stderr
        return result, calls

    return run


def test_macos_rehearsal_signs_both_roles_and_authenticates_without_submitting(run_macos_signing) -> None:
    result, calls = run_macos_signing("--rehearse")

    assert result.returncode == 0, result.stderr
    by_operation = {call[0]: call[1:] for call in calls}
    keychain = by_operation["security/create-keychain"][-1]
    assert by_operation["xcrun/notarytool/history"] == [
        "notarytool", "history", "--keychain", keychain, "--keychain-profile", "remote-ops-notary",
    ]
    assert by_operation["codesign/--force"][:-1] == [
        "--force", "--options", "runtime", "--timestamp", "--sign", "Application fixture", "--keychain", keychain,
    ]
    assert by_operation["codesign/--verify"][-1] == by_operation["codesign/--force"][-1]
    assert by_operation["productsign"][:-2] == ["--sign", "Installer fixture", "--keychain", keychain]
    assert by_operation["pkgutil"] == ["--check-signature", by_operation["productsign"][-1]]
    assert not {"build", "xcrun/notarytool/submit"} & by_operation.keys()
    assert calls[-1] == ["security/delete-keychain", "delete-keychain", keychain]
    assert "credential rehearsal passed" in result.stdout
    assert "fixture notary history" not in result.stdout


@pytest.mark.parametrize("failure", ["security/import", "xcrun/notarytool/history", "productsign", "security/delete-keychain"])
def test_macos_rehearsal_reports_failures_and_removes_credentials(run_macos_signing, failure: str) -> None:
    result, calls = run_macos_signing("--rehearse", failure=failure)
    assert result.returncode != 0
    assert "credential rehearsal passed" not in result.stdout
    operations = [call[0] for call in calls]
    assert operations[-1] == "security/delete-keychain"
    assert failure in operations
    assert "build" not in operations
    if failure == "xcrun/notarytool/history":
        assert "codesign/--force" not in operations


@pytest.mark.parametrize("failure", ["", "build"])
def test_macos_package_build_uses_the_locked_in_profile_and_cleans_up(run_macos_signing, failure: str) -> None:
    result, calls = run_macos_signing("--build", failure=failure)
    assert (result.returncode != 0) == bool(failure), result.stderr
    keychain = calls[0][-1]
    assert calls[-2:] == [["build", keychain], ["security/delete-keychain", "delete-keychain", keychain]]
    assert "xcrun/notarytool/history" not in [call[0] for call in calls]


def test_macos_signing_refuses_invalid_base64_before_import(run_macos_signing) -> None:
    result, calls = run_macos_signing("--rehearse", ROW_MACOS_NOTARY_KEY_BASE64="!invalid!")
    assert result.returncode != 0
    assert calls == []

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TIMESTAMP = "https://timestamp.example.invalid/"
THUMBPRINT = "a123" * 10


@pytest.fixture
def run_signer(tmp_path: Path):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is required to exercise the Windows signing scripts")
    signer = tmp_path / "sign_windows_artifact.ps1"
    shutil.copyfile(Path("scripts") / signer.name, signer)
    (tmp_path / "find_windows_signtool.ps1").write_text(
        'function Find-WindowsSignTool { $env:ROW_TEST_SIGNTOOL_EXE }\n',
        encoding="utf-8",
    )
    for operation in ("sign", "verify"):
        (tmp_path / operation).write_text(
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "if os.environ.get('ROW_TEST_SIGNTOOL_REHEARSE') == '1':\n"
            "    assert Path(sys.argv[-1]).read_bytes().startswith(b'MZ')\n"
            "    assert 'ROW_WINDOWS_CERTIFICATE_BASE64' not in os.environ\n"
            "    if '/f' in sys.argv:\n"
            "        pfx = Path(sys.argv[sys.argv.index('/f') + 1])\n"
            "        assert pfx.parent == Path(sys.argv[-1]).parent and pfx.read_bytes() == b'SYNTHETIC'\n"
            "with open(os.environ['ROW_TEST_SIGNTOOL_CALLS'], 'a', encoding='utf-8') as log:\n"
            f"    log.write(json.dumps([{operation!r}, *sys.argv[1:]]) + '\\n')\n"
            "if '/p' in sys.argv:\n"
            "    print('SDK diagnostic: ' + sys.argv[sys.argv.index('/p') + 1], file=sys.stderr)\n"
            f"raise SystemExit(int(os.environ['ROW_TEST_{operation.upper()}_EXIT']))\n",
            encoding="utf-8",
        )
    xp_builder = tmp_path / "make_windows_xp_legacy.ps1"
    shutil.copyfile(Path("scripts") / xp_builder.name, xp_builder)
    xp_driver = tmp_path / "run-xp-signing.ps1"
    xp_driver.write_text(
        "param([string]$ArtifactPath)\n"
        "$ErrorActionPreference = 'Stop'\n"
        "$ArtifactSigner = Join-Path $PSScriptRoot 'sign_windows_artifact.ps1'\n"
        "$Arch = 'x64'\n"
        "$Tokens = $ParseErrors = $null\n"
        "$Builder = Join-Path $PSScriptRoot 'make_windows_xp_legacy.ps1'\n"
        "$Tree = [System.Management.Automation.Language.Parser]::ParseFile("
        "$Builder, [ref]$Tokens, [ref]$ParseErrors)\n"
        "if ($ParseErrors) { throw 'XP builder could not be parsed' }\n"
        "$Function = $Tree.Find({ param($Node) "
        "$Node -is [System.Management.Automation.Language.FunctionDefinitionAst] "
        "-and $Node.Name -eq 'Sign-XpExecutable' }, $false)\n"
        ". ([scriptblock]::Create($Function.Extent.Text))\n"
        "Sign-XpExecutable $ArtifactPath\n",
        encoding="utf-8",
    )
    artifact = tmp_path / "fixture installer.exe"
    artifact.touch()
    calls = tmp_path / "signtool-calls.jsonl"
    driver = tmp_path / "run-signing.ps1"
    driver.write_text(
        """param([string]$Signer, [string]$ArtifactPath, [switch]$Rehearse)
$ErrorActionPreference = 'Stop'
try {
    if ($Rehearse) { & $Signer -Rehearse }
    else { & $Signer -ArtifactPath $ArtifactPath }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
""",
        encoding="ascii",
    )

    def run(inputs, *, xp=False, sign_exit=0, verify_exit=0, shell=None, rehearse=False):
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("ROW_WINDOWS_")}
        env.update({f"ROW_WINDOWS_{key}": value for key, value in inputs.items()})
        env.update(
            ROW_TEST_SIGNTOOL_EXE=sys.executable, ROW_TEST_SIGNTOOL_CALLS=str(calls), ROW_TEST_SIGN_EXIT=str(sign_exit),
            ROW_TEST_VERIFY_EXIT=str(verify_exit), RUNNER_TEMP=str(tmp_path),
        )
        arguments = ["-ArtifactPath", str(artifact)]
        if rehearse:
            env["ROW_TEST_SIGNTOOL_REHEARSE"] = "1"
            arguments = ["-Rehearse"]
        result = subprocess.run(
            [shell or powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(driver), "-Signer", str(xp_driver if xp else signer), *arguments],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False,
        )
        commands = [json.loads(line) for line in calls.read_text(encoding="utf-8-sig").splitlines()] if calls.exists() else []
        return result, commands, str(artifact)

    return run


@pytest.mark.parametrize("xp", [False, True])
@pytest.mark.parametrize("location", ["", "CurrentUser", "LocalMachine"])
def test_signing_selects_the_exact_certificate_and_verifies_timestamp(run_signer, xp: bool, location: str) -> None:
    result, commands, artifact = run_signer({
        "CERTIFICATE_THUMBPRINT": THUMBPRINT,
        "CERTIFICATE_STORE_LOCATION": location,
        "TIMESTAMP_URL": TIMESTAMP,
    }, xp=xp)
    assert result.returncode == 0, result.stderr
    store = ["/s", "My", "/sha1", THUMBPRINT]
    if location == "LocalMachine":
        store.append("/sm")
    assert commands == [
        ["sign", "/fd", "SHA256", "/tr", TIMESTAMP, "/td", "SHA256", *store, artifact],
        ["verify", "/pa", "/all", "/tw", artifact],
    ]


@pytest.mark.parametrize("xp", [False, True])
def test_pfx_signing_keeps_the_same_verification(run_signer, tmp_path: Path, xp: bool) -> None:
    inputs = {"CERTIFICATE_PASSWORD": "fixture password", "TIMESTAMP_URL": TIMESTAMP}
    if xp:
        inputs["CERTIFICATE_BASE64"] = "U1lOVEhFVElD"
    else:
        inputs["CERTIFICATE_PATH"] = str(tmp_path / "fixture certificate.pfx")
    result, commands, artifact = run_signer(inputs, xp=xp)
    assert result.returncode == 0, result.stderr
    sign, verify = commands
    assert sign[:8] == ["sign", "/fd", "SHA256", "/tr", TIMESTAMP, "/td", "SHA256", "/f"]
    assert sign[9:] == ["/p", "fixture password", artifact]
    assert verify == ["verify", "/pa", "/all", "/tw", artifact]
    if xp:
        temporary_certificate = Path(sign[8])
        assert temporary_certificate.parent == tmp_path
        assert temporary_certificate.name.startswith("row-xp-x64-")
        assert not temporary_certificate.exists()
    else:
        assert sign[8] == inputs["CERTIFICATE_PATH"]


@pytest.mark.parametrize("xp", [False, True])
@pytest.mark.parametrize("shell_name", ["powershell.exe", "pwsh.exe"])
def test_signing_preserves_exact_pfx_password(run_signer, tmp_path: Path, xp: bool, shell_name: str) -> None:
    shell = shutil.which(shell_name)
    if shell is None:
        pytest.skip(f"{shell_name} is required for this Windows argument passing test")
    password = r'prefix \\" quoted " tail' + "\\"
    inputs = {"CERTIFICATE_PASSWORD": password, "TIMESTAMP_URL": TIMESTAMP}
    if xp:
        inputs["CERTIFICATE_BASE64"] = "U1lOVEhFVElD"
    else:
        inputs["CERTIFICATE_PATH"] = str(tmp_path / "fixture certificate.pfx")

    result, commands, artifact = run_signer(inputs, xp=xp, shell=shell)

    assert result.returncode == 0, result.stderr
    sign, verify = commands
    assert sign[9:] == ["/p", password, artifact]
    assert verify == ["verify", "/pa", "/all", "/tw", artifact]
    assert password not in result.stdout + result.stderr
    assert "SDK diagnostic: [redacted]" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows signing rehearsal")
@pytest.mark.parametrize(("sign_exit", "verify_exit", "steps", "error"), [
    (0, 0, ["sign", "verify"], ""),
    (1, 0, ["sign"], "Authenticode signing failed"),
    (0, 2, ["sign", "verify"], "Authenticode signature or timestamp verification failed"),
])
def test_signing_rehearsal_checks_a_disposable_assembly(
    run_signer, tmp_path: Path, sign_exit, verify_exit, steps, error,
) -> None:
    result, commands, original = run_signer({
        "CERTIFICATE_THUMBPRINT": THUMBPRINT,
        "TIMESTAMP_URL": TIMESTAMP,
    }, rehearse=True, sign_exit=sign_exit, verify_exit=verify_exit)

    assert result.returncode == bool(error), result.stderr
    assert [command[0] for command in commands] == steps, result.stderr
    rehearsal = Path(commands[0][-1])
    assert rehearsal.name == "rehearsal.dll"
    assert rehearsal.parent.name.startswith("row-signing-rehearsal-")
    assert not rehearsal.parent.exists()
    assert Path(original).read_bytes() == b""
    assert commands[0][:7] == ["sign", "/fd", "SHA256", "/tr", TIMESTAMP, "/td", "SHA256"]
    if "verify" in steps:
        assert commands[-1] == ["verify", "/pa", "/all", "/tw", str(rehearsal)]
    if error:
        assert error in result.stderr
        assert "rehearsal passed" not in result.stdout
    else:
        assert "signing, timestamp and trust rehearsal passed" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Windows signing rehearsal")
@pytest.mark.parametrize("sign_exit", [0, 1])
def test_signing_rehearsal_cleans_up_the_encoded_pfx(run_signer, sign_exit) -> None:
    result, commands, _ = run_signer({
        "CERTIFICATE_BASE64": "U1lOVEhFVElD",
        "CERTIFICATE_PASSWORD": "fixture password",
        "TIMESTAMP_URL": TIMESTAMP,
    }, rehearse=True, sign_exit=sign_exit)

    assert result.returncode == sign_exit, result.stderr
    assert [command[0] for command in commands] == (["sign"] if sign_exit else ["sign", "verify"])
    temporary_pfx = Path(commands[0][commands[0].index("/f") + 1])
    assert temporary_pfx.name == "rehearsal.pfx"
    assert not temporary_pfx.parent.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows signing rehearsal")
def test_signing_rehearsal_rejects_two_pfx_sources(run_signer) -> None:
    result, commands, _ = run_signer({
        "CERTIFICATE_PATH": "fixture.pfx",
        "CERTIFICATE_BASE64": "U1lOVEhFVElD",
        "CERTIFICATE_PASSWORD": "fixture password",
        "TIMESTAMP_URL": TIMESTAMP,
    }, rehearse=True)

    assert result.returncode == 1
    assert "Choose one PFX source" in result.stderr
    assert commands == []


@pytest.mark.parametrize(("overrides", "error"), [
    ({"CERTIFICATE_THUMBPRINT": "short"}, "40-digit hexadecimal certificate thumbprint"),
    ({"CERTIFICATE_PATH": "fixture.pfx"}, "Choose one Windows signing source"),
    ({"CERTIFICATE_BASE64": "U1lOVEhFVElD"}, "Choose one Windows signing source"),
    ({"CERTIFICATE_PASSWORD": "fixture password"}, "Choose one Windows signing source"),
    ({"CERTIFICATE_STORE_LOCATION": "invalid"}, "must be CurrentUser or LocalMachine"),
    ({"CERTIFICATE_THUMBPRINT": "", "CERTIFICATE_STORE_LOCATION": "CurrentUser"},
     "requires ROW_WINDOWS_CERTIFICATE_THUMBPRINT"),
    ({"CERTIFICATE_THUMBPRINT": ""}, "PFX signing requires a certificate path"),
    ({"TIMESTAMP_URL": "https://user@timestamp.example.invalid/"}, "credential-free"),
    ({"TIMESTAMP_URL": "relative"}, "credential-free"),
])
def test_signer_rejects_ambiguous_or_invalid_inputs_before_calling_signtool(run_signer, overrides, error) -> None:
    inputs = {"CERTIFICATE_THUMBPRINT": THUMBPRINT, "TIMESTAMP_URL": TIMESTAMP} | overrides
    result, commands, _ = run_signer(inputs)
    assert result.returncode != 0
    assert error in result.stderr
    assert commands == []


@pytest.mark.parametrize(("sign_exit", "verify_exit", "steps"), [(2, 0, ["sign"]), (0, 2, ["sign", "verify"])])
def test_signer_refuses_warnings_and_removes_xp_temporary_pfx(run_signer, sign_exit, verify_exit, steps) -> None:
    result, commands, _ = run_signer({
        "CERTIFICATE_BASE64": "U1lOVEhFVElD", "CERTIFICATE_PASSWORD": "fixture password", "TIMESTAMP_URL": TIMESTAMP,
    }, xp=True, sign_exit=sign_exit, verify_exit=verify_exit)
    assert result.returncode != 0
    assert [command[0] for command in commands] == steps
    assert not Path(commands[0][8]).exists()

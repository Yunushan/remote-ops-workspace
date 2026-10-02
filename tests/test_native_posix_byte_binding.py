from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TARGETS = ("macos-x64", "macos-arm64", "linux-x86_64", "linux-aarch64")
BASH = shutil.which("bash") if os.name != "nt" else None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def helpers(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import candidate_native_proof as proof
    import candidate_posix_byte_binding as binding

    # Fixtures exercise binding; no fake CArchive is accepted by production init.
    # Native runner validation of actual PyInstaller inspection remains pending.
    monkeypatch.setattr(
        proof,
        "archive_inventory",
        lambda path: {"artifact_sha256": binding.digest(path), "toc": ["fixture"]},
    )
    return binding, proof


CANARY = r"""#!/usr/bin/env bash
printf 'fixture-probe\n' >> "$NATIVE_BINDING_MARKER"
case "$1" in
  --version) printf 'row 1.0.27\n' ;;
  platforms) printf '%s\n' '{"release_architectures":[1],"windows_legacy_targets":[1]}' ;;
  gui)
    python3 - "$3" <<'PY'
import hashlib, json, sys
from pathlib import Path
p=Path(sys.argv[1]); p.parent.mkdir(parents=True)
image=b'fixture screenshot bytes, no actual Qt proof'
p.with_suffix('.png').write_bytes(image)
p.write_text(json.dumps(dict(success=True,frozen=True,qt_platform='cocoa',version='1.0.27',profile_persisted=True,profile_selected=True,window_visible=True,paint_colour_count=3,screenshot_sha256=hashlib.sha256(image).hexdigest())))
PY
    ;;
esac
"""


def setup_fixture(tmp_path, target, helpers):
    binding, _ = helpers
    originals, _, _ = binding.target_contract(target)
    for relative in originals.values():
        path = tmp_path / relative
        path.parent.mkdir(parents=True)
        path.write_text(CANARY)
        path.chmod(0o755)
    launcher = tmp_path / binding.APPIMAGE_LAUNCHER
    if target.startswith("linux-"):
        launcher.parent.mkdir(parents=True)
        launcher.write_text(
            '#!/usr/bin/env sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/bin/row" "$@"\n'
        )
        launcher.chmod(0o755)
    image = None
    if target.startswith("linux-"):
        image = tmp_path / f"native-dist/linux/remote-ops-workspace-v1.0.27-{target}.AppImage"
        image.parent.mkdir(parents=True)
        image.write_text(
            '#!/usr/bin/env bash\nprintf "extract-fixture\\n" >> "$EXTRACTION_MARKER"\nmkdir -p squashfs-root/usr/bin\ncp "$EXTRACTED_FIXTURE_SOURCE" squashfs-root/usr/bin/row\nchmod +x squashfs-root/usr/bin/row\ncp "$EXTRACTED_LAUNCHER_SOURCE" squashfs-root/AppRun\nchmod +x squashfs-root/AppRun\n'
        )
        image.chmod(0o755)
    report = tmp_path / f"build/native-smoke/{target}/candidate-runtime-byte-binding.json"
    value = binding.initialize(tmp_path, target, report, image)
    return report, value, image


def fill_report(binding, target, root, report, package):
    outputs, paths, probes = binding.target_contract(target)
    for public_path, phase, probe in sorted(probes):
        binding.check(report, target, root / outputs[paths[public_path]], public_path, phase, probe)
    if package:
        for phase in ("install", "reinstall"):
            binding.check(
                report, target, package, "appimage/runtime.AppImage", phase, "extract", True
            )
            for probe in ("version", "platforms"):
                binding.check(
                    report,
                    target,
                    root / binding.APPIMAGE_LAUNCHER,
                    "appimage/AppRun",
                    phase,
                    probe,
                    True,
                )
    binding.complete(report, target)
    return json.loads(report.read_text())


@pytest.mark.parametrize("target", TARGETS)
def test_complete_receipt_matches_real_finish_contract(helpers, tmp_path, target):
    binding, proof = helpers
    report, _, package = setup_fixture(tmp_path, target, helpers)
    value = fill_report(binding, target, tmp_path, report, package)
    outputs, _, _ = binding.target_contract(target)
    archives = [
        dict(path=path, artifact_sha256=binding.digest(tmp_path / path), toc=["fixture"])
        for path in outputs.values()
    ]
    assets = (
        [dict(path=package.relative_to(tmp_path).as_posix(), sha256=binding.digest(package))]
        if package
        else []
    )
    launchers = (
        [
            dict(
                path=binding.APPIMAGE_LAUNCHER,
                sha256=binding.digest(tmp_path / binding.APPIMAGE_LAUNCHER),
            )
        ]
        if package
        else []
    )
    proof.validate_posix_byte_binding(value, archives, target, assets, launchers)
    assert value["status"] == "bound" and value["smoke_complete"] is True
    assert str(tmp_path) not in report.read_text()


@pytest.mark.parametrize(
    "change",
    (
        "target",
        "schema",
        "status",
        "incomplete",
        "required",
        "missing-probe",
        "wrong-stage",
        "wrong-role",
        "wrong-expected",
        "wrong-observed",
        "unmatched",
        "archive-error",
        "archive-bytes",
        "duplicate-archive",
        "package-bytes",
        "package-missing",
        "package-probe-missing",
        "launcher-bytes",
        "launcher-probe-missing",
        "wrong-launcher-path",
        "wrong-runtime-path",
    ),
)
def test_finish_refuses_forged_or_incomplete_receipt(helpers, tmp_path, change):
    binding, proof = helpers
    target = "linux-x86_64"
    report, _, package = setup_fixture(tmp_path, target, helpers)
    value = fill_report(binding, target, tmp_path, report, package)
    archive = dict(
        path="build/native/linux/pyinstaller-dist/row",
        artifact_sha256=value["expected_executables"][0]["sha256"],
        toc=["fixture"],
    )
    archives = [archive]
    assets = [dict(path=package.relative_to(tmp_path).as_posix(), sha256=binding.digest(package))]
    launchers = [
        dict(
            path=binding.APPIMAGE_LAUNCHER,
            sha256=binding.digest(tmp_path / binding.APPIMAGE_LAUNCHER),
        )
    ]
    if change == "target":
        value["target"] = "linux-aarch64"
    elif change == "schema":
        value["schema_version"] = True
    elif change == "status":
        value["status"] = "pending"
    elif change == "incomplete":
        value["smoke_complete"] = False
    elif change == "required":
        value["required_paths"].pop()
    elif change == "missing-probe":
        value["observations"].pop()
    elif change == "wrong-stage":
        value["observations"][0]["phase"] = "arbitrary"
    elif change == "wrong-role":
        value["observations"][0]["role"] = "gui"
    elif change == "wrong-expected":
        value["expected_executables"][0]["sha256"] = "0" * 64
    elif change == "wrong-observed":
        value["observations"][0]["observed_sha256"] = "0" * 64
    elif change == "unmatched":
        value["observations"][0]["matched"] = False
    elif change == "archive-error":
        archive["inventory_error"] = "fixture"
    elif change == "archive-bytes":
        archive["artifact_sha256"] = "0" * 64
    elif change == "duplicate-archive":
        archives.append(copy.deepcopy(archive))
    elif change == "package-bytes":
        assets[0]["sha256"] = "0" * 64
    elif change == "package-missing":
        value["expected_packages"] = []
    elif change == "wrong-launcher-path":
        next(row for row in value["expected_packages"] if row["role"] == "appimage-launcher")[
            "path"
        ] = "build/native/linux/other-AppRun"
        launchers[0]["path"] = "build/native/linux/other-AppRun"
    elif change == "wrong-runtime-path":
        next(row for row in value["expected_packages"] if row["role"] == "appimage-runtime")[
            "path"
        ] = "native-dist/linux/remote-ops-workspace-v1.0.27-linux-aarch64.AppImage"
        assets[0]["path"] = "native-dist/linux/remote-ops-workspace-v1.0.27-linux-aarch64.AppImage"
    elif change == "launcher-bytes":
        launchers[0]["sha256"] = "0" * 64
    elif change == "launcher-probe-missing":
        value["package_observations"] = [
            row for row in value["package_observations"] if row["role"] != "appimage-launcher"
        ]
    else:
        value["package_observations"].pop()
    with pytest.raises(ValueError):
        proof.validate_posix_byte_binding(value, archives, target, assets, launchers)


def test_macos_receipt_cannot_claim_unexpected_wrapper_binding(helpers, tmp_path):
    binding, proof = helpers
    target = "macos-x64"
    report, _, _ = setup_fixture(tmp_path, target, helpers)
    value = fill_report(binding, target, tmp_path, report, None)
    outputs, _, _ = binding.target_contract(target)
    archives = [
        dict(path=path, artifact_sha256=binding.digest(tmp_path / path), toc=["fixture"])
        for path in outputs.values()
    ]
    value["expected_packages"] = [dict(role="appimage-runtime")]
    with pytest.raises(ValueError):
        proof.validate_posix_byte_binding(value, archives, target, [])


@pytest.mark.parametrize("error", ("empty-toc", "wrong-hash"))
def test_initialization_refuses_uninspected_original(helpers, tmp_path, monkeypatch, error):
    binding, proof = helpers
    original = tmp_path / "build/native/linux/pyinstaller-dist/row"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"never launched")
    image = tmp_path / "fixture-linux-x86_64.AppImage"
    image.write_bytes(b"never launched wrapper")
    monkeypatch.setattr(
        proof,
        "archive_inventory",
        lambda path: dict(
            artifact_sha256="0" * 64 if error == "wrong-hash" else binding.digest(path),
            toc=[] if error == "empty-toc" else [1],
        ),
    )
    report = tmp_path / "report.json"
    with pytest.raises(ValueError):
        binding.initialize(tmp_path, "linux-x86_64", report, image)
    assert not report.exists()


def test_mismatch_is_durable_and_cannot_be_completed(helpers, tmp_path):
    binding, _ = helpers
    target = "linux-x86_64"
    report, _, _ = setup_fixture(tmp_path, target, helpers)
    wrong = tmp_path / "private-fixture-row"
    wrong.write_bytes(b"wrong bytes")
    with pytest.raises(ValueError, match="byte mismatch before probe"):
        binding.check(report, target, wrong, "deb/usr/bin/row", "install", "version")
    value = json.loads(report.read_text())
    assert value["status"] == "mismatch" and value["observations"][0][
        "observed_sha256"
    ] == binding.digest(wrong)
    assert str(wrong) not in report.read_text()
    with pytest.raises(ValueError):
        binding.complete(report, target)


def functions(source, names):
    """Load only actual Bash function bodies, never the package installer main."""
    lines = source.read_text().splitlines(keepends=True)
    chunks = []
    for name in names:
        start = next(index for index, line in enumerate(lines) if line.rstrip() == name + "() {")
        end = next(index for index in range(start + 1, len(lines)) if lines[index].rstrip() == "}")
        chunks.append("".join(lines[start : end + 1]))
    return "\n".join(chunks)


def shell_fixture(tmp_path, target, helpers):
    binding, _ = helpers
    report, _, package = setup_fixture(tmp_path, target, helpers)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("candidate_posix_byte_binding.py", "candidate_native_proof.py"):
        shutil.copyfile(SCRIPTS / name, scripts / name)
    original = tmp_path / next(iter(binding.target_contract(target)[0].values()))
    actual = (
        tmp_path / "actual/Remote Ops Workspace.app/Contents/MacOS/Remote Ops Workspace"
        if target.startswith("macos-")
        else tmp_path / "actual/row"
    )
    actual.parent.mkdir(parents=True)
    shutil.copyfile(original, actual)
    actual.chmod(0o755)
    smoke = report.parent
    env = {
        **os.environ,
        "BINDING_TARGET": target,
        "BINDING_REPORT": str(report),
        "SMOKE_ROOT": str(smoke),
        "VERSION": "1.0.27",
        "APP_EXECUTABLE_NAME": "Remote Ops Workspace",
        "NATIVE_BINDING_MARKER": str(tmp_path / "launch-marker"),
        "EXTRACTION_MARKER": str(tmp_path / "extract-marker"),
        "EXTRACTED_FIXTURE_SOURCE": str(actual),
        "EXTRACTED_LAUNCHER_SOURCE": str(tmp_path / binding.APPIMAGE_LAUNCHER),
        "STAGED_APPIMAGE": str(package) if package else "",
    }
    names = (
        ("candidate_check_app", "verify_app_runtime_resources", "verify_app_gui")
        if target.startswith("macos-")
        else (
            "run_row_command",
            "verify_row_runtime_resources",
            "verify_row",
            "prepare_appimage_probe",
        )
    )
    code = functions(
        SCRIPTS
        / ("smoke_macos_native.sh" if target.startswith("macos-") else "smoke_linux_native.sh"),
        names,
    )
    return report, package, actual, env, code


def bash_run(tmp_path, code, env):
    return subprocess.run(
        [BASH, "-c", "set -euo pipefail\n" + code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


PROBES = [
    (target, path, phase, probe)
    for target in ("macos-x64", "linux-x86_64")
    for path, phase, probe in sorted(
        load(SCRIPTS / "candidate_posix_byte_binding.py", "binding_collect").target_contract(
            target
        )[2]
    )
]


@pytest.mark.skipif(BASH is None, reason="actual Bash native fixture requires POSIX host")
@pytest.mark.parametrize("target,path,phase,probe", PROBES)
def test_every_actual_smoke_function_blocks_wrong_bytes_before_zero_launch(
    helpers, tmp_path, target, path, phase, probe
):
    binding, _ = helpers
    report, _, actual, env, code = shell_fixture(tmp_path, target, helpers)
    actual.write_text(CANARY + "\n# changed package executable bytes\n")
    actual.chmod(0o755)
    env.update(ACTUAL=str(actual), PUBLIC_PATH=path, STAGE=phase, PROBE=probe)
    if target.startswith("macos-"):
        env["APP_PATH"] = str(actual.parents[2])
        function = "verify_app_gui" if probe == "gui" else "verify_app_runtime_resources"
        invocation = f'{function} "$APP_PATH" "fixture" "$PUBLIC_PATH" "$STAGE"'
    else:
        arguments = "--version" if probe == "version" else "platforms --json"
        invocation = (
            f'run_row_command "$ACTUAL" direct "$PUBLIC_PATH" "$STAGE" "$PROBE" {arguments}'
        )
    result = bash_run(tmp_path, code + "\n" + invocation, env)
    assert result.returncode != 0
    assert "byte mismatch before probe" in result.stdout + result.stderr
    assert not (tmp_path / "launch-marker").exists()
    value = json.loads(report.read_text())
    assert value["status"] == "mismatch" and value["observations"][-1]["matched"] is False
    assert value["observations"][-1]["observed_sha256"] == binding.digest(actual)


@pytest.mark.skipif(BASH is None, reason="actual Bash native fixture requires POSIX host")
@pytest.mark.parametrize("target,path,phase,probe", PROBES)
def test_every_actual_smoke_function_launches_identical_fixture_bytes(
    helpers, tmp_path, target, path, phase, probe
):
    report, _, actual, env, code = shell_fixture(tmp_path, target, helpers)
    env.update(ACTUAL=str(actual), PUBLIC_PATH=path, STAGE=phase, PROBE=probe)
    if target.startswith("macos-"):
        env["APP_PATH"] = str(actual.parents[2])
        function = "verify_app_gui" if probe == "gui" else "verify_app_runtime_resources"
        invocation = f'{function} "$APP_PATH" "fixture" "$PUBLIC_PATH" "$STAGE"'
    else:
        arguments = "--version" if probe == "version" else "platforms --json"
        invocation = (
            f'run_row_command "$ACTUAL" direct "$PUBLIC_PATH" "$STAGE" "$PROBE" {arguments}'
        )
    result = bash_run(tmp_path, code + "\n" + invocation, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "launch-marker").read_text().splitlines() == ["fixture-probe"]
    assert json.loads(report.read_text())["observations"][-1]["matched"] is True


@pytest.mark.skipif(BASH is None or sys.platform != "linux", reason="actual AppRun fixture requires a Linux shell host")
@pytest.mark.parametrize("wrong", ("wrapper", "extracted-row", "launcher", "none"))
def test_appimage_checks_exact_wrapper_before_extract_and_exact_extracted_row_before_probe(
    helpers, tmp_path, wrong
):
    report, package, actual, env, code = shell_fixture(tmp_path, "linux-x86_64", helpers)
    if wrong == "wrapper":
        package.write_text(package.read_text() + "\n# wrong wrapper\n")
    elif wrong == "extracted-row":
        actual.write_text(CANARY + "\n# wrong extracted row\n")
    elif wrong == "launcher":
        changed = tmp_path / "changed-AppRun"
        changed.write_text(
            (tmp_path / helpers[0].APPIMAGE_LAUNCHER).read_text() + "\n# wrong launcher bytes\n"
        )
        env["EXTRACTED_LAUNCHER_SOURCE"] = str(changed)
    result = bash_run(
        tmp_path,
        code
        + '\nprepare_appimage_probe install\nverify_row "$APPIMAGE_ROW" appimage fixture appimage/usr/bin/row install',
        env,
    )
    if wrong == "none":
        assert result.returncode == 0, result.stdout + result.stderr
        assert len((tmp_path / "launch-marker").read_text().splitlines()) == 2
    else:
        assert result.returncode != 0
        assert "byte mismatch before probe" in result.stdout + result.stderr
        assert not (tmp_path / "launch-marker").exists()
        assert json.loads(report.read_text())["status"] == "mismatch"
    assert (tmp_path / "extract-marker").exists() is (wrong != "wrapper")


@pytest.mark.skipif(BASH is None, reason="actual Bash native fixture requires POSIX host")
def test_zero_launch_canary_detects_a_guard_moved_after_execution(helpers, tmp_path):
    _, _, actual, env, code = shell_fixture(tmp_path, "linux-x86_64", helpers)
    actual.write_text(CANARY + "\n# wrong executable still launches if guard is misplaced\n")
    guard = """    python3 scripts/candidate_posix_byte_binding.py check --target "$BINDING_TARGET" --report "$BINDING_REPORT" \\
      --path "$row_bin" --public-path "$public_path" --stage "$phase" --probe "$probe" || return $?"""
    assert guard in code
    mutant = code.replace(guard, '    "$row_bin" "$@"\n' + guard, 1)
    env["ACTUAL"] = str(actual)
    result = bash_run(
        tmp_path,
        mutant + '\nrun_row_command "$ACTUAL" direct deb/usr/bin/row install version --version',
        env,
    )
    assert result.returncode != 0 and "byte mismatch before probe" in result.stdout + result.stderr
    assert (tmp_path / "launch-marker").read_text().splitlines() == ["fixture-probe"]


@pytest.mark.parametrize("target", ("macos-x64", "linux-x86_64"))
@pytest.mark.parametrize("missing", (False, True))
def test_actual_finish_fails_closed_when_successful_posix_smoke_lacks_binding(
    helpers, tmp_path, monkeypatch, target, missing
):
    binding, proof = helpers
    report, _, package = setup_fixture(tmp_path, target, helpers)
    if missing:
        report.unlink()
    else:
        fill_report(binding, target, tmp_path, report, package)
    source = {"head": "a" * 40, "tree": "b" * 40, "checkout_bytes_sha256": "c" * 64}
    output = tmp_path / "build/candidate-proof" / target
    output.mkdir(parents=True)
    proof.save(output / "bind.json", {"source": source})
    project = tmp_path / "src/remote_ops_workspace/__init__.py"
    project.parent.mkdir(parents=True)
    project.write_bytes(b"never imported source fixture")
    monkeypatch.setattr(proof, "ROOT", tmp_path)
    monkeypatch.setattr(proof, "fingerprint", lambda: source)
    monkeypatch.setattr(
        proof,
        "archive_inventory",
        lambda path: {
            "path": path.relative_to(tmp_path).as_posix(),
            "artifact_sha256": binding.digest(path),
            "toc": ["fixture"],
        },
    )
    monkeypatch.setattr(
        proof.importlib.util, "find_spec", lambda *_args: types.SimpleNamespace(origin=str(project))
    )
    monkeypatch.setattr(proof.importlib.metadata, "distributions", lambda: [])
    monkeypatch.setattr(
        proof.subprocess,
        "run",
        lambda *_args, **_kwargs: types.SimpleNamespace(
            returncode=0, stdout=b'{"installed":[]}', stderr=b""
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "proof.py",
            "finish",
            "--target",
            target,
            "--expected-sha",
            source["head"],
            "--asset-dir",
            "native-dist/linux" if package else "native-dist/macos",
            "--native-build-outcome",
            "success",
            "--native-smoke-outcome",
            "success",
        ],
    )
    if missing:
        with pytest.raises(RuntimeError, match="binding report is missing"):
            proof.main()
    else:
        assert proof.main() == 0
    finish = json.loads((output / "finish.json").read_text())
    assert finish["native_executable_byte_binding"]["status"] == (
        "not-bound" if missing else "bound"
    )
    assert finish["native_pyinstaller_inventory_complete"] is True

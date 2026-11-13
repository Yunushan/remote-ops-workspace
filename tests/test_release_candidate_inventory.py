from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import urllib.error
import zipfile
from email.message import Message
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import release_candidate_inventory as candidate  # noqa: E402


def test_expected_gui_smoke_artifacts_match_the_signed_build_matrix() -> None:
    workflow = (ROOT / candidate.BUILD_WORKFLOW).read_text(encoding="utf-8")
    expected = set()
    for platform, label, condition in (
        ("windows", "Windows", "if: ${{ always() && matrix.arch != 'x86' }}"),
        ("macos", "macOS", "if: always()"),
    ):
        job = re.search(
            rf"(?ms)^  {platform}-native:\n(.*?)(?=^  [\w-]+:\n|\Z)",
            workflow,
        )
        assert job is not None
        matrix, steps = job[1].split("    steps:", 1)
        architectures = re.findall(r"(?m)^          - arch: ([\w-]+)$", matrix)
        marker = f"      - name: Retain installed {label} GUI workflow evidence\n"
        smoke_step = steps.split(marker, 1)[1].split("\n      - ", 1)[0]
        assert condition in smoke_step
        assert f"name: release-{platform}-gui-smoke-${{{{ matrix.arch }}}}" in smoke_step
        expected.update(
            f"release-{platform}-gui-smoke-{arch}"
            for arch in architectures
            if (platform, arch) != ("windows", "x86")
        )
    assert expected == set(candidate.GUI_SMOKE_ARTIFACT_NAMES)


@pytest.mark.parametrize(
    ("condition", "error"),
    [
        ("complete", ""),
        ("missing-installer", "missing=.*release-source-python"),
        ("missing-smoke", "missing=.*release-macos-gui-smoke-x64"),
        ("missing-runtime", "missing=.*release-runtime-windows-x86"),
        ("wrong-runtime-run", "is not bound to the approved build run and SHA"),
        ("bad-runtime-report", "must be a non-empty pip inspect v1 inventory"),
        ("unknown-artifact", "unexpected=.*unexpected-build"),
        ("expired-smoke", "GUI smoke artifact release-macos-gui-smoke-x64 must be unexpired"),
    ],
)
def test_seal_requires_workflow_artifacts_and_keeps_smoke_reports_out_of_release(
    tmp_path: Path,
    condition: str,
    error: str,
) -> None:
    sha = "a" * 40
    tag = "v1.2.3"
    standard = (
        "release-source-python",
        "release-windows-native-x64",
        "release-windows-native-x86",
        "release-windows-native-arm64",
        "release-macos-native-x64",
        "release-macos-native-arm64",
        "release-linux-native-x86_64",
        "release-linux-native-aarch64",
    )
    smoke = (
        "release-windows-gui-smoke-x64",
        "release-windows-gui-smoke-arm64",
        "release-macos-gui-smoke-x64",
        "release-macos-gui-smoke-arm64",
    )
    runtime = tuple(sorted(candidate.RUNTIME_REPORT_ARTIFACT_NAMES.values()))
    names = [*standard, *smoke, *runtime]
    if condition == "missing-installer":
        names.remove("release-source-python")
    if condition == "missing-smoke":
        names.remove("release-macos-gui-smoke-x64")
    if condition == "missing-runtime":
        names.remove("release-runtime-windows-x86")
    if condition == "unknown-artifact":
        names.append("unexpected-build")
    artifacts = []
    archives: dict[int, bytes] = {}
    raw_report = b'{"version":"1","installed":[{"metadata":{"name":"pip","version":"26.3"}}]}'
    for artifact_id, name in enumerate(names, start=1):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            if name in runtime:
                body = b"{}" if condition == "bad-runtime-report" else raw_report
                archive.writestr(candidate.RUNTIME_REPORT_NAME, body)
            else:
                archive.writestr(f"{name}.txt", f"bytes from {name}")
        data = stream.getvalue()
        artifacts.append({
            "id": artifact_id,
            "name": name,
            "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
            "expired": condition == "expired-smoke" and name == "release-macos-gui-smoke-x64",
            "size_in_bytes": len(data),
            "workflow_run": {"id": 99 if condition == "wrong-runtime-run" else 123, "head_sha": sha},
        })
        if name in standard or name in runtime:
            archives[artifact_id] = data
    downloads: list[int] = []

    class BuildRun:
        def json(self, endpoint: str) -> dict:
            if endpoint == "actions/runs/123":
                return {
                    "id": 123,
                    "run_attempt": 1,
                    "event": "push",
                    "head_branch": tag,
                    "head_sha": sha,
                    "path": ".github/workflows/release.yml",
                    "repository": {"full_name": "example/project"},
                }
            assert endpoint == "actions/runs/123/artifacts?per_page=100"
            return {"artifacts": artifacts}

        def download(self, endpoint: str, destination: Path, *, max_bytes: int = candidate.MAX_ARCHIVE_BYTES) -> str:
            artifact_id = int(endpoint.split("/")[2])
            assert endpoint == f"actions/artifacts/{artifact_id}/zip"
            downloads.append(artifact_id)
            data = archives[artifact_id]
            assert len(data) <= max_bytes
            destination.write_bytes(data)
            return f"sha256:{hashlib.sha256(data).hexdigest()}"

    root = tmp_path / "assets"
    output = tmp_path / "inventory.json"

    def seal() -> None:
        candidate.stage(
            BuildRun(),
            release_tag=tag,
            release_sha=sha,
            run_id=123,
            run_attempt=1,
            assets_root=root,
            output=output,
        )

    if error:
        with pytest.raises(ValueError, match=error):
            seal()
        assert len(downloads) == (1 if condition == "bad-runtime-report" else 0)
        assert not output.exists()
        return

    seal()
    inventory = json.loads(output.read_text(encoding="utf-8"))
    records = candidate.validate_inventory(
        inventory, repository="example/project", release_tag=tag, release_sha=sha,
        run_id=123, run_attempt=1,
    )
    assert {record["name"] for record in records} == set(standard)
    assert {path.name for path in root.iterdir()} == {f"{name}.txt" for name in standard}
    assert len(downloads) == len(archives) and set(downloads) == set(archives)
    assert inventory["runtime_reports"].keys() == candidate.RUNTIME_REPORT_ARTIFACT_NAMES.keys()
    for report in inventory["runtime_reports"].values():
        assert report["sha256"] == hashlib.sha256(raw_report).hexdigest()
        assert report["size_bytes"] == len(raw_report)
    inventory["runtime_reports"]["windows-x86"]["artifact_id"] = records[0]["id"]
    with pytest.raises(ValueError, match="runtime report windows-x86 artifact id is duplicated"):
        candidate.validate_inventory(
            inventory, repository="example/project", release_tag=tag, release_sha=sha,
            run_id=123, run_attempt=1,
        )


def redirect_error(url: str, location: str) -> urllib.error.HTTPError:
    headers = Message()
    headers["Location"] = location
    return urllib.error.HTTPError(url, 302, "Found", headers, io.BytesIO(b""))


def test_artifact_download_strips_auth_and_rejects_second_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[object] = []

    class Opener:
        def open(self, request: object, timeout: int) -> object:
            del timeout
            requests.append(request)
            if len(requests) == 1:
                raise redirect_error(
                    "https://api.github.com/repos/acme/project/actions/artifacts/7/zip",
                    "https://objects.githubusercontent.com/candidate.zip",
                )
            raise redirect_error(
                "https://objects.githubusercontent.com/candidate.zip",
                "http://attacker.invalid/candidate.zip",
            )

    opener = Opener()
    monkeypatch.setattr(candidate.urllib.request, "build_opener", lambda *_: opener)
    client = candidate.GitHubClient("acme/project", "top-secret")

    with pytest.raises(RuntimeError, match="unexpected second redirect"):
        client._open("actions/artifacts/7/zip", allow_redirect=True)

    assert len(requests) == 2
    first_headers = dict(requests[0].header_items())  # type: ignore[attr-defined]
    second_headers = dict(requests[1].header_items())  # type: ignore[attr-defined]
    assert first_headers["Authorization"] == "Bearer top-secret"
    assert "Authorization" not in second_headers


@pytest.mark.parametrize(
    "value",
    [
        ".github/workflows/release.yml",
        ".github/workflows/release.yml@v1.2.3",
        ".github/workflows/release.yml@refs/tags/v1.2.3",
    ],
)
def test_workflow_path_accepts_only_exact_tag_suffixes(value: str) -> None:
    assert candidate.workflow_path_matches(value, candidate.BUILD_WORKFLOW, "v1.2.3")


@pytest.mark.parametrize(
    "value",
    [
        ".github/workflows/release.yml@main",
        ".github/workflows/release.yml.evil@refs/tags/v1.2.3",
        "prefix/.github/workflows/release.yml@v1.2.3",
        ".github/workflows/release.yml@refs/tags/v1.2.30",
    ],
)
def test_workflow_path_rejects_branch_and_spoof_suffixes(value: str) -> None:
    assert not candidate.workflow_path_matches(value, candidate.BUILD_WORKFLOW, "v1.2.3")

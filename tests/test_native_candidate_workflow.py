from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40
TREE = "d" * 40
INJECTED_VERSION = "1.0.27\nsha=" + "b" * 40 + "\ntree=" + "c" * 40


@pytest.fixture
def candidate_binding():
    pytest.importorskip(
        "tomllib",
        reason="candidate source-binding runs on the pinned CPython 3.14 builder; tomllib unavailable on Python 3.10",
    )
    workflow = (ROOT / ".github/workflows/native-candidate-validation.yml").read_text()
    lines = workflow.splitlines()
    blocks = []
    for index, line in enumerate(lines):
        if line.strip() != "python - <<'PY'":
            continue
        indent = len(line) - len(line.lstrip())
        selected = []
        for follow in lines[index + 1 :]:
            if follow.strip() == "PY":
                break
            selected.append(follow[indent:])
        block = "\n".join(selected)
        ast.parse(block)
        blocks.append(block)
    assert len(blocks) == 1
    assert "types: [opened, synchronize, reopened, labeled]" in workflow
    assert "contains(github.event.pull_request.labels.*.name, 'native-all-modern')" in workflow
    assert "scope: ${{ steps.bind.outputs.scope }}" in workflow
    assert workflow.count("if: ${{ needs.candidate-source.outputs.scope == 'all-modern' }}") == 2
    return blocks[0]


def _execute_binding(binding, version, scope, tmp_path, monkeypatch):
    output = tmp_path / "github-output.txt"
    output.write_text("")
    (tmp_path / "pyproject.toml").write_text("[project]\nversion=" + json.dumps(version) + "\n")
    monkeypatch.chdir(tmp_path)
    for key, value in {
        "EXPECTED_CANDIDATE_SHA": HEAD,
        "CANDIDATE_SCOPE": scope,
        "GITHUB_OUTPUT": str(output),
        "GITHUB_SHA": "f" * 40,
    }.items():
        monkeypatch.setenv(key, value)
    responses = iter((HEAD.encode(), TREE.encode()))
    monkeypatch.setattr(subprocess, "check_output", lambda _argv: next(responses))
    monkeypatch.setattr(subprocess, "run", lambda _argv: subprocess.CompletedProcess([], 0))
    exec(compile(binding, "<candidate-binding>", "exec"), {})
    return output


@pytest.mark.parametrize("scope,rows", (("windows-x64", 1), ("all-modern", 3)))
def test_candidate_scope_and_commit_outputs(candidate_binding, tmp_path, monkeypatch, scope, rows):
    output = _execute_binding(candidate_binding, "1.0.27", scope, tmp_path, monkeypatch)
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["sha"] == HEAD and values["tree"] == TREE
    assert values["scope"] == scope and values["version_tag"] == "v1.0.27"
    assert len(json.loads(values["windows_matrix"])["include"]) == rows


def test_candidate_rejects_unknown_scope_before_outputs(candidate_binding, tmp_path, monkeypatch):
    with pytest.raises(AssertionError, match="unsupported candidate scope"):
        _execute_binding(candidate_binding, "1.0.27", "unsupported", tmp_path, monkeypatch)
    assert (tmp_path / "github-output.txt").read_bytes() == b""


@pytest.mark.parametrize(
    "version",
    (
        INJECTED_VERSION,
        "1.0.27\r\nsha=" + "b" * 40,
        "1.0.27\t",
        "1.0.27\x01",
        "1.0.27\n",
        "v1.0.27",
        "1.0",
        123,
    ),
)
def test_candidate_rejects_unsafe_version_before_any_output(
    candidate_binding, tmp_path, monkeypatch, version
):
    with pytest.raises(AssertionError, match="project.version must be canonical numeric X.Y.Z"):
        _execute_binding(candidate_binding, version, "all-modern", tmp_path, monkeypatch)
    assert (tmp_path / "github-output.txt").read_bytes() == b""


def test_version_regression_reproduces_previous_sha_and_tree_injection(
    candidate_binding, tmp_path, monkeypatch
):
    unguarded = "\n".join(
        line
        for line in candidate_binding.splitlines()
        if "project.version must be canonical numeric X.Y.Z" not in line
    )
    assert unguarded != candidate_binding
    output = _execute_binding(unguarded, INJECTED_VERSION, "all-modern", tmp_path, monkeypatch)
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["sha"] == "b" * 40 and values["tree"] == "c" * 40

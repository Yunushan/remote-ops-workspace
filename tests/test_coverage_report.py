from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def test_coverage_report_accepts_consistent_totals_at_both_floors() -> None:
    checker = _load_checker()

    assert checker.check_report(_report(), minimum_total=70, minimum_branches=55) == []


def test_coverage_report_rejects_aggregate_or_branch_regression() -> None:
    checker = _load_checker()
    low_total = _report(covered_lines=84, covered_branches=55)
    low_branches = _report(covered_lines=86, covered_branches=54)

    total_errors = checker.check_report(low_total, minimum_total=70, minimum_branches=55)
    branch_errors = checker.check_report(low_branches, minimum_total=70, minimum_branches=55)

    assert any("aggregate coverage 69.50%" in error for error in total_errors)
    assert any("branch coverage 54.00%" in error for error in branch_errors)


def test_coverage_report_rejects_missing_or_inconsistent_evidence() -> None:
    checker = _load_checker()
    inconsistent = _report()
    inconsistent["totals"]["num_branches"] = 99
    inflated = _report()
    inflated["totals"]["percent_covered"] = 99

    assert checker.check_report({}, minimum_total=70, minimum_branches=55) == [
        "JSON must contain a totals object"
    ]
    assert any(
        "covered_branches plus missing_branches" in error
        for error in checker.check_report(
            inconsistent,
            minimum_total=70,
            minimum_branches=55,
        )
    )
    inflated_errors = checker.check_report(
        inflated,
        minimum_total=70,
        minimum_branches=55,
    )
    assert "totals.percent_covered does not match the coverage counts" in inflated_errors


def test_coverage_report_cli_validates_a_json_file(tmp_path: Path, capsys) -> None:
    checker = _load_checker()
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")

    result = checker.main(
        [
            "--report",
            str(report_path),
            "--min-total",
            "70",
            "--min-branches",
            "55",
        ]
    )

    assert result == 0
    assert "aggregate=70.00% >= 70.00%, branches=55.00% >= 55.00%" in capsys.readouterr().out


@pytest.mark.parametrize("count", [True, -1, 0.5])
def test_coverage_report_rejects_invalid_count_types(count) -> None:
    checker = _load_checker()
    report = _report()
    report["totals"]["missing_lines"] = count
    assert "totals.missing_lines must be a non-negative integer" in checker.check_report(
        report, minimum_total=70, minimum_branches=55,
    )


@pytest.mark.parametrize(("condition", "error"), [
    ("complete", ""),
    ("missing", "coverage report is missing source files: pkg/sub/route.py"),
    ("unexpected", "coverage report contains unexpected source files: pkg/untracked.py"),
    ("duplicate", "coverage report contains duplicate source paths"),
    ("wrong-sum", "coverage file summaries do not match the report totals"),
    ("wrong-meta", "coverage metadata must identify a branch coverage report"),
])
def test_coverage_cli_checks_the_module_inventory_and_exact_count_totals(
    tmp_path: Path, monkeypatch, capsys, condition, error,
) -> None:
    checker = _load_checker()
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "pkg"
    (source / "sub").mkdir(parents=True)
    (source / "engine.py").write_text("def engine(): return 42\n", encoding="utf-8")
    (source / "sub" / "route.py").write_text("def route(): return 4\n", encoding="utf-8")
    report = _report(covered_lines=100, covered_branches=100)
    totals = report["totals"]
    half = {field: totals[field] // 2 for field in checker.COUNT_FIELDS}
    report["meta"] = {"branch_coverage": condition != "wrong-meta"}
    report["files"] = {
        r"pkg\engine.py": {"summary": dict(half)},
        "pkg/sub/route.py": {"summary": dict(half)},
    }
    if condition == "missing":
        # A smaller, internally consistent report still shows 100%.
        del report["files"]["pkg/sub/route.py"]
        totals.update(half)
    elif condition == "unexpected":
        report["files"]["pkg/untracked.py"] = report["files"].pop("pkg/sub/route.py")
    elif condition == "duplicate":
        report["files"]["pkg/engine.py"] = report["files"][r"pkg\engine.py"]
    elif condition == "wrong-sum":
        totals["covered_lines"] += 1
        totals["num_statements"] += 1
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    assert checker.main([
        "--report", str(report_path), "--source-root", "pkg", "--min-total", "100", "--min-branches", "100",
    ]) == int(bool(error))
    captured = capsys.readouterr()
    if error:
        assert error in captured.err
    else:
        assert "coverage report passed" in captured.out


def _report(
    *,
    covered_lines: int = 85,
    covered_branches: int = 55,
) -> dict[str, object]:
    missing_lines = 100 - covered_lines
    missing_branches = 100 - covered_branches
    percent_covered = 100 * (covered_lines + covered_branches) / 200
    return {
        "totals": {
            "covered_lines": covered_lines,
            "missing_lines": missing_lines,
            "num_statements": 100,
            "covered_branches": covered_branches,
            "missing_branches": missing_branches,
            "num_branches": 100,
            "percent_covered": percent_covered,
        }
    }


def _load_checker():
    path = Path("scripts/check_coverage_report.py")
    spec = importlib.util.spec_from_file_location("check_coverage_report_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

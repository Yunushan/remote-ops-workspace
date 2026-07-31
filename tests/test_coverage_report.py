from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


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

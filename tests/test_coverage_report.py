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
    low_total = _report(percent_covered=69.99)
    low_branches = _report(percent_branches_covered=54.99)

    total_errors = checker.check_report(low_total, minimum_total=70, minimum_branches=55)
    branch_errors = checker.check_report(low_branches, minimum_total=70, minimum_branches=55)

    assert any("aggregate coverage 69.99%" in error for error in total_errors)
    assert any("branch coverage 54.99%" in error for error in branch_errors)


def test_coverage_report_rejects_missing_or_inconsistent_evidence() -> None:
    checker = _load_checker()
    inconsistent = _report()
    inconsistent["totals"]["num_branches"] = 99
    inflated = _report(percent_covered=99, percent_branches_covered=99)

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
    assert (
        "totals.percent_branches_covered does not match the branch counts" in inflated_errors
    )


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
    percent_covered: float = 70,
    percent_branches_covered: float = 55,
) -> dict[str, object]:
    return {
        "totals": {
            "covered_lines": 85,
            "missing_lines": 15,
            "num_statements": 100,
            "covered_branches": 55,
            "missing_branches": 45,
            "num_branches": 100,
            "percent_covered": percent_covered,
            "percent_branches_covered": percent_branches_covered,
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

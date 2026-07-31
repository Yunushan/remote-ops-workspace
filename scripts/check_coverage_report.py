from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"coverage report: could not read {args.report}: {exc}", file=sys.stderr)
        return 1

    errors = check_report(
        report,
        minimum_total=args.min_total,
        minimum_branches=args.min_branches,
    )
    if errors:
        for error in errors:
            print(f"coverage report: {error}", file=sys.stderr)
        return 1

    totals = report["totals"]
    branch_percent = 100 * totals["covered_branches"] / totals["num_branches"]
    print(
        "coverage report passed: "
        f"aggregate={totals['percent_covered']:.2f}% >= {args.min_total:.2f}%, "
        f"branches={branch_percent:.2f}% >= {args.min_branches:.2f}%"
    )
    return 0


def check_report(
    report: object,
    *,
    minimum_total: float,
    minimum_branches: float,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["top-level JSON value must be an object"]
    totals = report.get("totals")
    if not isinstance(totals, dict):
        return ["JSON must contain a totals object"]

    values: dict[str, float] = {}
    for key in (
        "covered_lines",
        "missing_lines",
        "num_statements",
        "covered_branches",
        "missing_branches",
        "num_branches",
        "percent_covered",
    ):
        value = totals.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"totals.{key} must be a finite number")
            continue
        number = float(value)
        if not math.isfinite(number):
            errors.append(f"totals.{key} must be a finite number")
            continue
        values[key] = number

    if errors:
        return errors

    if values["num_statements"] <= 0:
        errors.append("totals.num_statements must be greater than zero")
    if values["num_branches"] <= 0:
        errors.append("totals.num_branches must be greater than zero")
    if values["covered_lines"] + values["missing_lines"] != values["num_statements"]:
        errors.append("covered_lines plus missing_lines must equal num_statements")
    if values["covered_branches"] + values["missing_branches"] != values["num_branches"]:
        errors.append("covered_branches plus missing_branches must equal num_branches")

    _check_percentage(errors, values, "percent_covered")
    if values["num_statements"] > 0 and values["num_branches"] > 0:
        expected_total = 100 * (
            values["covered_lines"] + values["covered_branches"]
        ) / (values["num_statements"] + values["num_branches"])
        expected_branches = 100 * values["covered_branches"] / values["num_branches"]
        if not math.isclose(values["percent_covered"], expected_total, abs_tol=1e-9):
            errors.append("totals.percent_covered does not match the coverage counts")
    else:
        expected_branches = 0.0
    if values["percent_covered"] < minimum_total:
        errors.append(
            f"aggregate coverage {values['percent_covered']:.2f}% is below "
            f"the required {minimum_total:.2f}%"
        )
    if expected_branches < minimum_branches:
        errors.append(
            f"branch coverage {expected_branches:.2f}% is below "
            f"the required {minimum_branches:.2f}%"
        )
    return errors


def _check_percentage(errors: list[str], values: dict[str, float], key: str) -> None:
    if not 0 <= values[key] <= 100:
        errors.append(f"totals.{key} must be between 0 and 100")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate aggregate and pure branch thresholds in a coverage.py JSON report."
    )
    parser.add_argument("--report", type=Path, required=True, help="coverage.py JSON report")
    parser.add_argument(
        "--min-total",
        type=_percentage,
        required=True,
        help="minimum aggregate line-and-branch coverage percentage",
    )
    parser.add_argument(
        "--min-branches",
        type=_percentage,
        required=True,
        help="minimum pure branch-decision coverage percentage",
    )
    return parser.parse_args(argv)


def _percentage(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number between 0 and 100") from exc
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise argparse.ArgumentTypeError("must be a finite number between 0 and 100")
    return number


if __name__ == "__main__":
    raise SystemExit(main())

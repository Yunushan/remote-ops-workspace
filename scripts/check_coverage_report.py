from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

COUNT_FIELDS = (
    "covered_lines", "missing_lines", "num_statements",
    "covered_branches", "missing_branches", "num_branches",
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        expected_files = (
            source_inventory(args.source_root) if args.source_root is not None else None
        )
    except (OSError, ValueError) as exc:
        print(f"coverage report: {exc}", file=sys.stderr)
        return 1

    errors = check_report(
        report,
        minimum_total=args.min_total,
        minimum_branches=args.min_branches,
        expected_files=expected_files,
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


def source_inventory(source_root: Path) -> set[str]:
    root = source_root.resolve()
    checkout = Path.cwd().resolve()
    if not root.is_relative_to(checkout):
        raise ValueError("coverage source root must be inside the working directory")
    files = {file.relative_to(checkout).as_posix() for file in root.rglob("*.py") if file.is_file()}
    if not files:
        raise ValueError(f"coverage source root contains no Python modules: {source_root}")
    return files


def check_report(
    report: object,
    *,
    minimum_total: float,
    minimum_branches: float,
    expected_files: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["top-level JSON value must be an object"]
    totals = report.get("totals")
    if not isinstance(totals, dict):
        return ["JSON must contain a totals object"]

    values = read_counts(totals, "totals", errors)
    percent = totals.get("percent_covered")
    if isinstance(percent, bool) or not isinstance(percent, (int, float)) or not 0 <= percent <= 100:
        errors.append("totals.percent_covered must be a finite number from 0 to 100")
        return errors
    if values is None:
        return errors
    if values["num_statements"] <= 0:
        errors.append("totals.num_statements must be greater than zero")
    if values["num_branches"] <= 0:
        errors.append("totals.num_branches must be greater than zero")
    if values["num_statements"] > 0 and values["num_branches"] > 0:
        expected_total = 100 * (
            values["covered_lines"] + values["covered_branches"]
        ) / (values["num_statements"] + values["num_branches"])
        expected_branches = 100 * values["covered_branches"] / values["num_branches"]
        if not math.isclose(percent, expected_total, abs_tol=1e-9, rel_tol=0):
            errors.append("totals.percent_covered does not match the coverage counts")
        if expected_total < minimum_total:
            errors.append(
                f"aggregate coverage {expected_total:.2f}% is below the required {minimum_total:.2f}%"
            )
        elif minimum_total == 100 and (values["missing_lines"] or values["missing_branches"]):
            errors.append("100% aggregate coverage requires zero missing lines and branches")
        if expected_branches < minimum_branches:
            errors.append(
                f"branch coverage {expected_branches:.2f}% is below the required {minimum_branches:.2f}%"
            )
        elif minimum_branches == 100 and values["missing_branches"]:
            errors.append("100% branch coverage requires zero missing branches")
    if expected_files is not None:
        check_inventory(report, expected_files, values, errors)
    return errors


def read_counts(summary: object, label: str, errors: list[str]) -> dict[str, int] | None:
    if not isinstance(summary, dict):
        errors.append(f"{label} must be an object")
        return None
    values: dict[str, int] = {}
    for field in COUNT_FIELDS:
        count = summary.get(field)
        if type(count) is not int or count < 0:
            errors.append(f"{label}.{field} must be a non-negative integer")
        else:
            values[field] = count
    if len(values) != len(COUNT_FIELDS):
        return None
    if values["covered_lines"] + values["missing_lines"] != values["num_statements"]:
        errors.append(f"{label}: covered_lines plus missing_lines must equal num_statements")
    if values["covered_branches"] + values["missing_branches"] != values["num_branches"]:
        errors.append(f"{label}: covered_branches plus missing_branches must equal num_branches")
    return values


def check_inventory(
    report: dict, expected_files: set[str], totals: dict[str, int], errors: list[str],
) -> None:
    meta = report.get("meta")
    if not isinstance(meta, dict) or meta.get("branch_coverage") is not True:
        errors.append("coverage metadata must identify a branch coverage report")
    files = report.get("files")
    if not isinstance(files, dict):
        errors.append("JSON must contain a files object for source inventory validation")
        return
    paths = {name.replace("\\", "/") for name in files}
    if len(paths) != len(files):
        errors.append("coverage report contains duplicate source paths")
    if missing := expected_files - paths:
        errors.append(f"coverage report is missing source files: {', '.join(sorted(missing))}")
    if unexpected := paths - expected_files:
        errors.append(f"coverage report contains unexpected source files: {', '.join(sorted(unexpected))}")
    combined = dict.fromkeys(COUNT_FIELDS, 0)
    for name, row in files.items():
        summary = row.get("summary") if isinstance(row, dict) else None
        counts = read_counts(summary, f"{name} summary", errors)
        if counts is not None:
            for field in COUNT_FIELDS:
                combined[field] += counts[field]
    if combined != totals:
        errors.append("coverage file summaries do not match the report totals")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate aggregate and pure branch thresholds in a coverage.py JSON report."
    )
    parser.add_argument("--report", type=Path, required=True, help="coverage.py JSON report")
    parser.add_argument(
        "--source-root", type=Path,
        help="Require every Python module under this directory and reconcile its summary counts",
    )
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

"""Collect complete, counted GitHub REST listings used as release evidence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def collect_evidence_pages(
    fetch_page: Callable[[int], dict[str, Any]], *, key: str, label: str, page_size: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    expected_total: int | None = None
    page = 1
    while True:
        payload = fetch_page(page)
        batch = payload.get(key)
        total = payload.get("total_count")
        if not isinstance(batch, list):
            raise RuntimeError(f"{label} page {page} must contain a list of {key}")
        if type(total) is not int or total < 0:
            raise RuntimeError(f"{label} page {page} must contain a non-negative integer total_count")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise RuntimeError(
                f"{label} pagination total_count changed from {expected_total} to {total} on page {page}"
            )
        if len(batch) > page_size:
            raise RuntimeError(f"{label} page {page} exceeds requested page size {page_size}")
        for row in batch:
            row_id = row.get("id") if isinstance(row, dict) else None
            if type(row_id) is not int or row_id <= 0:
                raise RuntimeError(f"{label} page {page} must contain objects with positive integer ids")
            if row_id in seen_ids:
                raise RuntimeError(f"{label} pagination repeated id {row_id}")
            seen_ids.add(row_id)
            rows.append(row)
        if len(rows) > total:
            raise RuntimeError(f"{label} pagination returned more rows than total_count={total}")
        if len(rows) == total:
            return {"total_count": total, key: rows}
        if len(batch) < page_size:
            raise RuntimeError(
                f"{label} pagination ended before total_count: total_count={total}, received={len(rows)}"
            )
        page += 1

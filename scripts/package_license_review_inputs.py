"""Prepare manifest-bound license observations for independent review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from check_preview_redistribution import file_hash, regular_child
from check_release_license_compliance import (
    expected_native_manifest_names,
    native_manifest_entries,
    normalize_component_name,
    path_is_reparse,
)

LICENSE_RECORD_FIELDS = ("path", "file", "sha256", "size_bytes")


def manifest_review_inputs(
    assets_dir: Path, tag: str, matrix: dict[str, Any], packages: dict[str, Any],
) -> dict[str, Any]:
    review = {}
    assigned = set()
    for name in sorted(expected_native_manifest_names(matrix, tag)):
        manifest = regular_child(assets_dir, name, "native manifest")
        if path_is_reparse(manifest):
            raise ValueError(f"{name} must be a regular unlinked native manifest")
        manifest_digest = file_hash(manifest)
        entries, errors = native_manifest_entries(manifest, assets_dir)
        if errors:
            raise ValueError("; ".join(errors))
        if file_hash(manifest) != manifest_digest:
            raise ValueError(f"{name} changed during license review preparation")
        if duplicates := assigned & entries.keys():
            raise ValueError(f"packages are named by multiple native manifests: {sorted(duplicates)}")
        scans = {}
        for asset, identity in sorted(entries.items()):
            capture = packages.get(asset)
            if capture is None or any(capture[field] != identity[field] for field in ("sha256", "size_bytes")):
                raise ValueError(f"{name} does not match the extracted package identity for {asset}")
            scans[asset] = capture["notice_files"]
        assigned.update(entries)
        review[name] = {
            "sha256": manifest_digest,
            "artifact_license_files": {
                asset: [{key: row[key] for key in LICENSE_RECORD_FIELDS} for row in records]
                for asset, records in scans.items()
            },
            "component_license_files": component_license_files(scans, name),
        }
    if assigned != packages.keys():
        raise ValueError(f"packages are missing from the native manifests: {sorted(packages.keys() - assigned)}")
    return {
        "schema": "row.packaged-license-review-inputs.v1",
        "release_tag": tag,
        "native_manifests": review,
    }


def component_license_files(scans: dict[str, list[dict[str, Any]]], manifest: str) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {}
    shared: dict[tuple[str, str, int], dict[str, list[dict[str, Any]]]] = {}
    for asset, records in scans.items():
        for row in records:
            if "component" not in row:
                continue
            name = normalize_component_name(row["component"])
            component = components.setdefault(name, {"license_files": []})
            if row.get("origin") == "native-component":
                version = row["version"]
                if component.setdefault("version", version) != version:
                    raise ValueError(f"{manifest} has inconsistent Debian notice versions for {name}")
                component.update({"name": row["component"], "origin": "native-component"})
                record = {key: row[key] for key in LICENSE_RECORD_FIELDS}
                if record not in component["license_files"]:
                    component["license_files"].append(record)
            else:
                group = shared.setdefault((name, row["sha256"], row["size_bytes"]), {})
                group.setdefault(asset, []).append(row)

    for (name, _, _), occurrences in sorted(shared.items()):
        if occurrences.keys() != scans.keys() or len({len(rows) for rows in occurrences.values()}) != 1:
            raise ValueError(f"{manifest} has inconsistent packaged license files for {name}")
        assets = sorted(occurrences)
        sorted_rows = [sorted(occurrences[asset], key=lambda row: row["path"]) for asset in assets]
        for rows in zip(*sorted_rows, strict=True):
            record = {key: rows[0][key] for key in LICENSE_RECORD_FIELDS}
            overrides = {
                asset: row["path"] for asset, row in zip(assets, rows, strict=True) if row["path"] != record["path"]
            }
            if overrides:
                record["artifact_paths"] = overrides
            components[name]["license_files"].append(record)
    return dict(sorted(components.items()))

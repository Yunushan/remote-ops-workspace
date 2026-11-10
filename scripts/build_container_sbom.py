"""Generate a CycloneDX 1.5 SBOM for the Web/PWA container image Python environment.

The Web/PWA image is built from `docker/Dockerfile.web` on a digest-pinned base
image. This tool turns the Python distribution inventory collected from inside
the built container (in CI, through `importlib.metadata.distributions()`) into a
CycloneDX document so the image is covered by the same SBOM and provenance
attestation as the source/Python release assets. Distribution packages provided
by the operating-system layer remain covered by the digest-pinned base image and
are deliberately not inferred here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

APPLICATION_NAME = "remote-ops-workspace"
IMAGE_COMPONENT_NAME = "remote-ops-workspace-web"
IMAGE_SCOPE = "container-web-image-python-environment"
DEFAULT_SOURCE_DATE_EPOCH = 1_704_067_200  # 2024-01-01T00:00:00Z
NORMALIZE_RE = re.compile(r"[-_.]+")


def source_date_epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return DEFAULT_SOURCE_DATE_EPOCH
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit("SOURCE_DATE_EPOCH must be an integer Unix timestamp") from exc
    if value < 0:
        raise SystemExit("SOURCE_DATE_EPOCH must not be negative")
    return value


def package_component_ref(name: str, version: str) -> str:
    normalized_name = NORMALIZE_RE.sub("-", name).lower()
    return f"pkg:pypi/{quote(normalized_name, safe='.-')}@{quote(version, safe='.-')}"


def image_component_ref(image_id: str) -> str:
    return f"pkg:oci/{IMAGE_COMPONENT_NAME}@{quote(image_id, safe='.-')}"


def normalize_packages(packages: list[dict[str, object]]) -> list[dict[str, str]]:
    if not packages:
        raise ValueError("container image package inventory must not be empty")
    components: list[dict[str, str]] = []
    seen: set[str] = set()
    for package in packages:
        raw_name = package.get("name")
        raw_version = package.get("version")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        version = raw_version.strip() if isinstance(raw_version, str) else ""
        if not name or not version:
            raise ValueError("container image package entries must have a name and version")
        reference = package_component_ref(name, version)
        if reference in seen:
            continue
        seen.add(reference)
        components.append(
            {
                "type": "library",
                "bom-ref": reference,
                "name": name,
                "version": version,
                "purl": reference,
            }
        )
    components.sort(key=lambda component: (component["name"].casefold(), component["version"]))
    return components


def build_container_image_sbom(
    packages: list[dict[str, object]],
    *,
    application_version: str,
    image_id: str,
    epoch: int | None = None,
) -> dict[str, object]:
    resolved_epoch = source_date_epoch() if epoch is None else epoch
    components = normalize_packages(packages)
    application_versions = [
        component["version"]
        for component in components
        if NORMALIZE_RE.sub("-", component["name"]).lower() == APPLICATION_NAME
    ]
    if application_versions != [application_version]:
        raise ValueError(
            "container inventory must contain exactly the installed application version"
        )
    component_refs = "\n".join(component["bom-ref"] for component in components)
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "https://github.com/Yunushan/remote-ops-workspace/containers/"
        f"{IMAGE_COMPONENT_NAME}\n{image_id}\n{component_refs}",
    )
    timestamp = datetime.fromtimestamp(resolved_epoch, tz=timezone.utc).replace(microsecond=0)
    reference = image_component_ref(image_id)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "component": {
                "type": "container",
                "bom-ref": reference,
                "name": IMAGE_COMPONENT_NAME,
                "version": application_version,
                "purl": reference,
            },
            "properties": [
                {"name": "row:sbom-scope", "value": IMAGE_SCOPE},
                {"name": "row:container-image-id", "value": image_id},
                {"name": "row:application", "value": f"{APPLICATION_NAME}@{application_version}"},
                {"name": "row:source-date-epoch", "value": str(resolved_epoch)},
            ],
        },
        "components": components,
    }


def load_packages(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"container image package inventory is not valid JSON: {exc}") from exc
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise SystemExit("container image package inventory must be a JSON list of objects")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a container image CycloneDX SBOM.")
    parser.add_argument(
        "--packages",
        type=Path,
        required=True,
        help="JSON list of name/version entries collected from the built container image",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="application version installed in the container image",
    )
    parser.add_argument(
        "--image-id",
        required=True,
        help="container image identity the inventory was collected from",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="CycloneDX JSON output path",
    )
    args = parser.parse_args(argv)

    payload = build_container_image_sbom(
        load_packages(args.packages),
        application_version=args.version,
        image_id=args.image_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"container image SBOM written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate a CycloneDX SBOM for the exported Web/PWA image tested in CI."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

APPLICATION_NAME = "remote-ops-workspace"
IMAGE_COMPONENT_NAME = "remote-ops-workspace-web"
IMAGE_SCOPE = "container-web-image-installed-python-and-debian-packages"
DEFAULT_SOURCE_DATE_EPOCH = 1_704_067_200  # 2024-01-01T00:00:00Z
NORMALIZE_RE = re.compile(r"[-_.]+")
SHA256_DIGEST_RE = re.compile(r"sha256:([0-9a-f]{64})")
IMAGE_MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
PLAIN_LAYER_TYPES = {
    "application/vnd.oci.image.layer.v1.tar",
    "application/vnd.docker.image.rootfs.diff.tar",
}
GZIP_LAYER_TYPES = {
    "application/vnd.oci.image.layer.v1.tar+gzip",
    "application/vnd.docker.image.rootfs.diff.tar.gzip",
}
MAX_IMAGE_METADATA_BYTES = 1024 * 1024


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


def debian_components(inventory: str) -> list[dict[str, str]]:
    components: dict[str, dict[str, str]] = {}
    for line_number, line in enumerate(inventory.splitlines(), start=1):
        fields = line.split("\t")
        if len(fields) != 4:
            raise ValueError(f"invalid Debian package inventory line {line_number}")
        status, name, version, architecture = fields
        state = status.split()
        if len(state) != 3 or state[1] != "ok":
            raise ValueError(f"invalid Debian package status on line {line_number}")
        if state[2] in {"not-installed", "config-files"}:
            continue
        if (
            state[2] != "installed"
            or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", name)
            or not re.fullmatch(r"[A-Za-z0-9.+:~-]+", version)
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", architecture)
        ):
            raise ValueError(f"incomplete Debian package record on line {line_number}")
        reference = f"pkg:deb/debian/{quote(name, safe='.-')}@{quote(version, safe='.-')}?arch={architecture}"
        components[reference] = {
            "type": "library",
            "bom-ref": reference,
            "name": name,
            "version": version,
            "purl": reference,
        }
    if not components:
        raise ValueError("container image must contain installed Debian packages")
    return [components[reference] for reference in sorted(components)]


def archive_member(archive: tarfile.TarFile, name: str) -> tarfile.TarInfo:
    matches = [
        member for member in archive.getmembers() if member.name.removeprefix("./") == name
    ]
    if len(matches) != 1 or not matches[0].isfile():
        raise ValueError(f"expected one regular image archive member: {name}")
    return matches[0]


def stream_sha256(stream: BinaryIO) -> str:
    sha256 = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        sha256.update(chunk)
    return sha256.hexdigest()


def verified_blob(
    archive: tarfile.TarFile,
    descriptor: object,
    *,
    read_metadata: bool = False,
    diff_id: str | None = None,
) -> bytes:
    if not isinstance(descriptor, dict):
        raise ValueError("image archive has an invalid content descriptor")
    digest = descriptor.get("digest")
    match = SHA256_DIGEST_RE.fullmatch(digest) if isinstance(digest, str) else None
    size = descriptor.get("size")
    if match is None or type(size) is not int or size < 0:
        raise ValueError("image archive descriptor must contain a SHA-256 digest and byte size")
    member = archive_member(archive, f"blobs/sha256/{match[1]}")
    if member.size != size:
        raise ValueError(f"image archive blob size mismatch: {digest}")
    if read_metadata and size > MAX_IMAGE_METADATA_BYTES:
        raise ValueError("image archive manifest exceeds the metadata size limit")
    stream = archive.extractfile(member)
    assert stream is not None  # archive_member requires a regular file.
    with stream:
        if read_metadata:
            data = stream.read()
            actual_digest = hashlib.sha256(data).hexdigest()
        else:
            data = b""
            actual_digest = stream_sha256(stream)
        if actual_digest != match[1]:
            raise ValueError(f"image archive blob digest mismatch: {digest}")
        if diff_id is not None:
            media_type = descriptor.get("mediaType")
            if media_type in PLAIN_LAYER_TYPES:
                uncompressed_sha256 = actual_digest
            elif media_type in GZIP_LAYER_TYPES:
                stream.seek(0)
                with gzip.GzipFile(fileobj=stream) as uncompressed:
                    uncompressed_sha256 = stream_sha256(uncompressed)
            else:
                raise ValueError(f"unsupported image layer type: {media_type}")
            if f"sha256:{uncompressed_sha256}" != diff_id:
                raise ValueError(f"image layer does not match the tested configuration: {digest}")
    return data


def verified_image_manifest(path: Path, image_id: str) -> bytes:
    with tarfile.open(path, mode="r:") as archive:
        index_member = archive_member(archive, "index.json")
        if index_member.size > MAX_IMAGE_METADATA_BYTES:
            raise ValueError("image archive index exceeds the metadata size limit")
        stream = archive.extractfile(index_member)
        assert stream is not None
        with stream:
            index = json.load(stream)
        entries = index.get("manifests") if isinstance(index, dict) else None
        if not isinstance(entries, list) or len(entries) != 1:
            raise ValueError("image archive must contain one manifest for the tested image")
        entry = entries[0]
        if not isinstance(entry, dict) or entry.get("mediaType") not in IMAGE_MANIFEST_TYPES:
            raise ValueError("image archive index must name a runnable image manifest")
        data = verified_blob(archive, entry, read_metadata=True)
        manifest = json.loads(data)
        if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2:
            raise ValueError("image archive manifest must use schema version 2")
        config = manifest.get("config")
        if not isinstance(config, dict) or config.get("digest") != image_id:
            raise ValueError("image archive config does not match the smoke-tested image ID")
        layers = manifest.get("layers")
        if not isinstance(layers, list) or not layers:
            raise ValueError("image archive manifest must name its layers")
        image_config = json.loads(verified_blob(archive, config, read_metadata=True))
        rootfs = image_config.get("rootfs") if isinstance(image_config, dict) else None
        diff_ids = rootfs.get("diff_ids") if isinstance(rootfs, dict) else None
        if (
            not isinstance(diff_ids, list)
            or len(diff_ids) != len(layers)
            or not all(isinstance(digest, str) and SHA256_DIGEST_RE.fullmatch(digest) for digest in diff_ids)
        ):
            raise ValueError("tested image configuration must name each uncompressed layer")
        for layer, diff_id in zip(layers, diff_ids, strict=True):
            verified_blob(archive, layer, diff_id=diff_id)
    return data


def build_container_image_sbom(
    packages: list[dict[str, object]],
    *,
    debian_packages: str,
    application_version: str,
    image_id: str,
    image_manifest_sha256: str,
    epoch: int | None = None,
) -> dict[str, object]:
    if not SHA256_DIGEST_RE.fullmatch(image_id):
        raise ValueError("container image ID must be a SHA-256 digest")
    if not re.fullmatch(r"[0-9a-f]{64}", image_manifest_sha256):
        raise ValueError("container image manifest must have a SHA-256 digest")
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
    components.extend(debian_components(debian_packages))
    component_refs = "\n".join(component["bom-ref"] for component in components)
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "https://github.com/Yunushan/remote-ops-workspace/containers/"
        f"{IMAGE_COMPONENT_NAME}\n{image_id}\n{image_manifest_sha256}\n{component_refs}",
    )
    timestamp = datetime.fromtimestamp(resolved_epoch, tz=timezone.utc).replace(microsecond=0)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "component": {
                "type": "container",
                "bom-ref": f"sha256:{image_manifest_sha256}",
                "name": IMAGE_COMPONENT_NAME,
                "version": application_version,
                "hashes": [{"alg": "SHA-256", "content": image_manifest_sha256}],
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
        "--debian-packages",
        type=Path,
        required=True,
        help="dpkg status, name, version and architecture inventory from the tested container",
    )
    parser.add_argument(
        "--image-id",
        required=True,
        help="container image identity the inventory was collected from",
    )
    parser.add_argument(
        "--image-archive",
        type=Path,
        required=True,
        help="local Docker archive exported from the tested image ID",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        required=True,
        help="write the exact verified OCI image manifest bytes to this path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="CycloneDX JSON output path",
    )
    args = parser.parse_args(argv)

    manifest = verified_image_manifest(args.image_archive, args.image_id)
    payload = build_container_image_sbom(
        load_packages(args.packages),
        debian_packages=args.debian_packages.read_text(encoding="utf-8"),
        application_version=args.version,
        image_id=args.image_id,
        image_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
    )
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_bytes(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"container image SBOM written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

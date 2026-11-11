from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

DEBIAN_PACKAGES = "install ok installed\tlibc6\t2.41-12\tamd64\n"
IMAGE_ID = "sha256:" + "a" * 64
MANIFEST_SHA256 = "b" * 64


def test_container_image_sbom_inventories_installed_python_and_debian_packages() -> None:
    builder = _load_builder()

    payload = builder.build_container_image_sbom(
        [
            {"name": "wheel", "version": "0.48.0"},
            {"name": "PyQt6_sip", "version": "13.13.0"},
            {"name": "remote-ops-workspace", "version": "1.0.27"},
            {"name": "wheel", "version": "0.48.0"},
        ],
        application_version="1.0.27",
        image_id=IMAGE_ID,
        epoch=1_704_067_200,
        debian_packages=DEBIAN_PACKAGES,
        image_manifest_sha256=MANIFEST_SHA256,
    )

    assert payload["bomFormat"] == "CycloneDX"
    assert payload["specVersion"] == "1.5"
    assert payload["version"] == 1
    assert str(payload["serialNumber"]).startswith("urn:uuid:")
    metadata = payload["metadata"]
    assert metadata["timestamp"] == "2024-01-01T00:00:00Z"
    assert metadata["component"] == {
        "type": "container",
        "bom-ref": f"sha256:{MANIFEST_SHA256}",
        "name": "remote-ops-workspace-web",
        "version": "1.0.27",
        "hashes": [{"alg": "SHA-256", "content": MANIFEST_SHA256}],
    }
    assert metadata["properties"] == [
        {
            "name": "row:sbom-scope",
            "value": "container-web-image-installed-python-and-debian-packages",
        },
        {"name": "row:container-image-id", "value": IMAGE_ID},
        {"name": "row:application", "value": "remote-ops-workspace@1.0.27"},
        {"name": "row:source-date-epoch", "value": "1704067200"},
    ]
    assert payload["components"] == [
        {
            "type": "library",
            "bom-ref": "pkg:pypi/pyqt6-sip@13.13.0",
            "name": "PyQt6_sip",
            "version": "13.13.0",
            "purl": "pkg:pypi/pyqt6-sip@13.13.0",
        },
        {
            "type": "library",
            "bom-ref": "pkg:pypi/remote-ops-workspace@1.0.27",
            "name": "remote-ops-workspace",
            "version": "1.0.27",
            "purl": "pkg:pypi/remote-ops-workspace@1.0.27",
        },
        {
            "type": "library",
            "bom-ref": "pkg:pypi/wheel@0.48.0",
            "name": "wheel",
            "version": "0.48.0",
            "purl": "pkg:pypi/wheel@0.48.0",
        },
        {
            "type": "library",
            "bom-ref": "pkg:deb/debian/libc6@2.41-12?arch=amd64",
            "name": "libc6",
            "version": "2.41-12",
            "purl": "pkg:deb/debian/libc6@2.41-12?arch=amd64",
        },
    ]


def test_container_image_sbom_serial_is_deterministic_and_bound_to_the_image() -> None:
    builder = _load_builder()
    packages = [
        {"name": "wheel", "version": "0.48.0"},
        {"name": "remote-ops-workspace", "version": "1.0.27"},
    ]

    first = builder.build_container_image_sbom(
        packages,
        application_version="1.0.27",
        image_id=IMAGE_ID,
        epoch=1_704_067_200,
        debian_packages=DEBIAN_PACKAGES,
        image_manifest_sha256=MANIFEST_SHA256,
    )
    repeat = builder.build_container_image_sbom(
        packages,
        application_version="1.0.27",
        image_id=IMAGE_ID,
        epoch=1_704_067_200,
        debian_packages=DEBIAN_PACKAGES,
        image_manifest_sha256=MANIFEST_SHA256,
    )
    other_manifest = builder.build_container_image_sbom(
        packages,
        application_version="1.0.27",
        image_id=IMAGE_ID,
        epoch=1_704_067_200,
        debian_packages=DEBIAN_PACKAGES,
        image_manifest_sha256="c" * 64,
    )

    assert first["serialNumber"] == repeat["serialNumber"]
    assert first["serialNumber"] != other_manifest["serialNumber"]


def test_debian_inventory_distinguishes_architectures_and_skips_removed_packages() -> None:
    builder = _load_builder()
    packages = (
        "hold ok installed\tlibfoo\t1:2.3+deb13u1\tarm64\n"
        "deinstall ok config-files\tlibremoved\t1.0\tamd64\n"
        "install ok installed\tlibfoo\t1:2.3+deb13u1\tamd64\n"
    )
    assert [component["purl"] for component in builder.debian_components(packages)] == [
        "pkg:deb/debian/libfoo@1%3A2.3%2Bdeb13u1?arch=amd64",
        "pkg:deb/debian/libfoo@1%3A2.3%2Bdeb13u1?arch=arm64",
    ]


@pytest.mark.parametrize(
    ("inventory", "error"),
    [
        ("", "must contain installed Debian packages"),
        ("invalid", "invalid Debian package inventory"),
        ("install reinstreq installed\tlibfoo\t1.0\tamd64", "invalid Debian package status"),
        ("install ok unpacked\tlibfoo\t1.0\tamd64", "incomplete Debian package record"),
        ("install ok installed\tlibfoo\t\tamd64", "incomplete Debian package record"),
    ],
)
def test_debian_inventory_refuses_unusable_package_state(inventory, error) -> None:
    builder = _load_builder()
    with pytest.raises(ValueError, match=error):
        builder.debian_components(inventory)


@pytest.mark.parametrize(
    ("image_id", "manifest_sha256", "error"),
    [
        ("latest", MANIFEST_SHA256, "image ID must be a SHA-256 digest"),
        (IMAGE_ID, "unknown", "image manifest must have a SHA-256 digest"),
    ],
)
def test_container_image_sbom_refuses_unbound_identity(image_id, manifest_sha256, error) -> None:
    builder = _load_builder()
    with pytest.raises(ValueError, match=error):
        builder.build_container_image_sbom(
            [{"name": "remote-ops-workspace", "version": "1.0.27"}],
            debian_packages=DEBIAN_PACKAGES,
            application_version="1.0.27",
            image_id=image_id,
            image_manifest_sha256=manifest_sha256,
        )


def test_container_image_sbom_uses_the_source_date_epoch_environment_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)

    payload = builder.build_container_image_sbom(
        [{"name": "remote-ops-workspace", "version": "1.0.27"}],
        application_version="1.0.27",
        image_id=IMAGE_ID,
        debian_packages=DEBIAN_PACKAGES,
        image_manifest_sha256=MANIFEST_SHA256,
    )

    assert payload["metadata"]["timestamp"] == "2024-01-01T00:00:00Z"
    assert len(payload["components"]) == 2

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1704240000")
    assert builder.source_date_epoch() == 1_704_240_000
    assert (
        builder.build_container_image_sbom(
            [{"name": "remote-ops-workspace", "version": "1.0.27"}],
            application_version="1.0.27",
            image_id=IMAGE_ID,
            debian_packages=DEBIAN_PACKAGES,
            image_manifest_sha256=MANIFEST_SHA256,
        )["metadata"]["timestamp"]
        == "2024-01-03T00:00:00Z"
    )


@pytest.mark.parametrize(
    "packages",
    [
        [],
        [{"name": "", "version": "1.0"}],
        [{"name": "wheel", "version": ""}],
        [{"name": None, "version": "1.0"}],
        [{"name": "wheel", "version": 1}],
    ],
)
def test_container_image_sbom_rejects_incomplete_inventories(packages) -> None:
    builder = _load_builder()

    with pytest.raises(ValueError, match="container image package"):
        builder.build_container_image_sbom(
            packages,
            application_version="1.0.27",
            image_id=IMAGE_ID,
            debian_packages=DEBIAN_PACKAGES,
            image_manifest_sha256=MANIFEST_SHA256,
        )


def test_container_inventory_does_not_filter_unnamed_distributions() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    collection = workflow.split("- name: Collect container image package inventory", 1)[1].split(
        "- name: Generate container image SBOM", 1
    )[0]

    assert "for distribution in importlib.metadata.distributions()" in collection
    assert "if distribution.metadata.get('Name')" not in collection


@pytest.mark.parametrize(
    "packages",
    [
        [{"name": "wheel", "version": "0.48.0"}],
        [{"name": "remote-ops-workspace", "version": "1.0.26"}],
        [
            {"name": "remote-ops-workspace", "version": "1.0.27"},
            {"name": "remote_ops_workspace", "version": "1.0.26"},
        ],
    ],
)
def test_container_image_sbom_rejects_missing_or_mismatched_application(packages) -> None:
    builder = _load_builder()

    with pytest.raises(ValueError, match="exactly the installed application version"):
        builder.build_container_image_sbom(
            packages,
            application_version="1.0.27",
            image_id=IMAGE_ID,
            debian_packages=DEBIAN_PACKAGES,
            image_manifest_sha256=MANIFEST_SHA256,
        )


def test_container_image_sbom_accepts_normalized_application_name() -> None:
    builder = _load_builder()

    payload = builder.build_container_image_sbom(
        [{"name": "Remote_Ops.Workspace", "version": "1.0.27"}],
        application_version="1.0.27",
        image_id=IMAGE_ID,
        debian_packages=DEBIAN_PACKAGES,
        image_manifest_sha256=MANIFEST_SHA256,
    )

    assert payload["components"][0]["purl"] == "pkg:pypi/remote-ops-workspace@1.0.27"


def test_container_image_sbom_rejects_invalid_source_date_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-a-timestamp")
    with pytest.raises(SystemExit, match="SOURCE_DATE_EPOCH must be an integer Unix timestamp"):
        builder.source_date_epoch()

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "-1")
    with pytest.raises(SystemExit, match="SOURCE_DATE_EPOCH must not be negative"):
        builder.source_date_epoch()


def test_container_image_sbom_load_packages_rejects_malformed_inventories(tmp_path: Path) -> None:
    builder = _load_builder()
    malformed = tmp_path / "packages.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(SystemExit, match="not valid JSON"):
        builder.load_packages(malformed)

    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"name": "wheel"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="must be a JSON list of objects"):
        builder.load_packages(mapping)

    scalars = tmp_path / "scalars.json"
    scalars.write_text(json.dumps(["wheel"]), encoding="utf-8")
    with pytest.raises(SystemExit, match="must be a JSON list of objects"):
        builder.load_packages(scalars)


def test_container_image_sbom_cli_writes_cyclonedx_output(tmp_path: Path, capsys) -> None:
    builder = _load_builder()
    packages = tmp_path / "container-image-packages.json"
    packages.write_text(
        json.dumps([{"name": "remote-ops-workspace", "version": "1.0.27"}]),
        encoding="utf-8",
    )
    debian = tmp_path / "debian.tsv"
    debian.write_text(DEBIAN_PACKAGES, encoding="utf-8")
    archive = tmp_path / "image.tar"
    image_id, manifest = _write_image_archive(archive)
    manifest_output = tmp_path / "nested" / "image-manifest.json"
    output = tmp_path / "nested" / "container-image-sbom.cdx.json"

    assert (
        builder.main(
            [
                "--packages",
                str(packages),
                "--version",
                "1.0.27",
                "--image-id",
                image_id,
                "--debian-packages",
                str(debian),
                "--image-archive",
                str(archive),
                "--manifest-output",
                str(manifest_output),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metadata"]["component"]["version"] == "1.0.27"
    assert [component["name"] for component in payload["components"]] == [
        "remote-ops-workspace",
        "libc6",
    ]
    assert payload["metadata"]["component"]["hashes"] == [
        {"alg": "SHA-256", "content": hashlib.sha256(manifest).hexdigest()}
    ]
    assert manifest_output.read_bytes() == manifest
    assert f"container image SBOM written: {output}" in capsys.readouterr().out


@pytest.mark.parametrize("compressed", [False, True])
def test_verified_manifest_checks_image_id_and_layer_contents(tmp_path: Path, compressed) -> None:
    builder = _load_builder()
    archive = tmp_path / "image.tar"
    image_id, manifest = _write_image_archive(archive, compressed=compressed)
    assert builder.verified_image_manifest(archive, image_id) == manifest
    with pytest.raises(ValueError, match="config does not match the smoke-tested image ID"):
        builder.verified_image_manifest(archive, IMAGE_ID)


@pytest.mark.parametrize(
    ("corrupt_blob", "different_layer", "error"),
    [
        (True, False, "blob digest mismatch"),
        (False, True, "layer does not match the tested configuration"),
    ],
)
def test_verified_manifest_rejects_replaced_layer(
    tmp_path: Path, corrupt_blob, different_layer, error,
) -> None:
    builder = _load_builder()
    archive = tmp_path / "image.tar"
    image_id, _manifest = _write_image_archive(
        archive, corrupt_blob=corrupt_blob, different_layer=different_layer,
    )
    with pytest.raises(ValueError, match=error):
        builder.verified_image_manifest(archive, image_id)


def _write_image_archive(
    path: Path,
    *,
    compressed: bool = False,
    corrupt_blob: bool = False,
    different_layer: bool = False,
) -> tuple[str, bytes]:
    def descriptor(data: bytes, media_type: str) -> dict[str, str | int]:
        return {
            "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
            "mediaType": media_type,
            "size": len(data),
        }

    layer = b"tested image layer"
    layer_type = "application/vnd.oci.image.layer.v1.tar"
    diff_id = descriptor(layer, layer_type)["digest"]
    config = json.dumps({"rootfs": {"type": "layers", "diff_ids": [diff_id]}}).encode()
    if different_layer:
        layer = b"unrelated image layer"
    if compressed:
        layer = gzip.compress(layer, mtime=0)
        layer_type += "+gzip"
    layer_descriptor = descriptor(layer, layer_type)
    config_descriptor = descriptor(config, "application/vnd.oci.image.config.v1+json")
    manifest_type = "application/vnd.oci.image.manifest.v1+json"
    manifest = json.dumps({
        "schemaVersion": 2,
        "mediaType": manifest_type,
        "config": config_descriptor,
        "layers": [layer_descriptor],
    }).encode()
    manifest_descriptor = descriptor(manifest, manifest_type)
    index = json.dumps({"schemaVersion": 2, "manifests": [manifest_descriptor]}).encode()
    if corrupt_blob:
        layer = b"x" + layer[1:]
    files = {"index.json": index}
    for blob, metadata in (
        (manifest, manifest_descriptor),
        (config, config_descriptor),
        (layer, layer_descriptor),
    ):
        digest = str(metadata["digest"]).removeprefix("sha256:")
        files[f"blobs/sha256/{digest}"] = blob
    with tarfile.open(path, "w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return str(config_descriptor["digest"]), manifest


def _load_builder():
    path = Path("scripts/build_container_sbom.py")
    spec = importlib.util.spec_from_file_location("build_container_sbom", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

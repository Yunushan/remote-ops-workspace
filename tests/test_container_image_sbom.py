from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def test_container_image_sbom_inventories_installed_python_distributions() -> None:
    builder = _load_builder()

    payload = builder.build_container_image_sbom(
        [
            {"name": "wheel", "version": "0.48.0"},
            {"name": "PyQt6_sip", "version": "13.13.0"},
            {"name": "remote-ops-workspace", "version": "1.0.27"},
            {"name": "wheel", "version": "0.48.0"},
        ],
        application_version="1.0.27",
        image_id="sha256:abc",
        epoch=1_704_067_200,
    )

    assert payload["bomFormat"] == "CycloneDX"
    assert payload["specVersion"] == "1.5"
    assert payload["version"] == 1
    assert str(payload["serialNumber"]).startswith("urn:uuid:")
    metadata = payload["metadata"]
    assert metadata["timestamp"] == "2024-01-01T00:00:00Z"
    assert metadata["component"] == {
        "type": "container",
        "bom-ref": "pkg:oci/remote-ops-workspace-web@sha256%3Aabc",
        "name": "remote-ops-workspace-web",
        "version": "1.0.27",
        "purl": "pkg:oci/remote-ops-workspace-web@sha256%3Aabc",
    }
    assert metadata["properties"] == [
        {
            "name": "row:sbom-scope",
            "value": "container-web-image-python-environment",
        },
        {"name": "row:container-image-id", "value": "sha256:abc"},
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
    ]


def test_container_image_sbom_serial_is_deterministic_and_bound_to_the_image() -> None:
    builder = _load_builder()
    packages = [
        {"name": "wheel", "version": "0.48.0"},
        {"name": "remote-ops-workspace", "version": "1.0.27"},
    ]

    first = builder.build_container_image_sbom(
        packages, application_version="1.0.27", image_id="sha256:abc", epoch=1_704_067_200
    )
    repeat = builder.build_container_image_sbom(
        packages, application_version="1.0.27", image_id="sha256:abc", epoch=1_704_067_200
    )
    other_image = builder.build_container_image_sbom(
        packages, application_version="1.0.27", image_id="sha256:def", epoch=1_704_067_200
    )

    assert first["serialNumber"] == repeat["serialNumber"]
    assert first["serialNumber"] != other_image["serialNumber"]


def test_container_image_sbom_uses_the_source_date_epoch_environment_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)

    payload = builder.build_container_image_sbom(
        [{"name": "remote-ops-workspace", "version": "1.0.27"}],
        application_version="1.0.27",
        image_id="sha256:abc",
    )

    assert payload["metadata"]["timestamp"] == "2024-01-01T00:00:00Z"
    assert len(payload["components"]) == 1

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1704240000")
    assert builder.source_date_epoch() == 1_704_240_000
    assert (
        builder.build_container_image_sbom(
            [{"name": "remote-ops-workspace", "version": "1.0.27"}],
            application_version="1.0.27",
            image_id="sha256:abc",
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
            packages, application_version="1.0.27", image_id="sha256:abc"
        )


def test_container_inventory_does_not_filter_unnamed_distributions() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    collection = workflow.split("- name: Collect container image Python inventory", 1)[1].split(
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
            packages, application_version="1.0.27", image_id="sha256:abc"
        )


def test_container_image_sbom_accepts_normalized_application_name() -> None:
    builder = _load_builder()

    payload = builder.build_container_image_sbom(
        [{"name": "Remote_Ops.Workspace", "version": "1.0.27"}],
        application_version="1.0.27",
        image_id="sha256:abc",
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
    output = tmp_path / "nested" / "container-image-sbom.cdx.json"

    assert (
        builder.main(
            [
                "--packages",
                str(packages),
                "--version",
                "1.0.27",
                "--image-id",
                "sha256:abc",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metadata"]["component"]["version"] == "1.0.27"
    assert [component["name"] for component in payload["components"]] == [
        "remote-ops-workspace"
    ]
    assert f"container image SBOM written: {output}" in capsys.readouterr().out


def _load_builder():
    path = Path("scripts/build_container_sbom.py")
    spec = importlib.util.spec_from_file_location("build_container_sbom", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

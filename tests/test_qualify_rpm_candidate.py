import hashlib
import io
import json
import tarfile
from copy import deepcopy

import pytest

from scripts import qualify_rpm_candidate as candidate
from scripts.qualify_rpm_recovery import sha256

SOURCE = "a" * 40
VERSION = "1.0.28"
RUN_ID = "192"
ATTEMPT = "2"


@pytest.fixture
def inputs(tmp_path):
    rpm = tmp_path / f"native-dist/linux/{candidate.rpm_name(VERSION)}"
    rpm.parent.mkdir(parents=True)
    rpm.write_bytes(b"candidate-rpm-fixture")
    proof = {
        "target": "linux-x86_64",
        "source": {"head": SOURCE},
        "run_id": RUN_ID,
        "run_attempt": ATTEMPT,
        "source_unchanged": True,
        "native_build_outcome": "success",
        "native_smoke_outcome": "success",
        "native_executable_byte_binding": {"status": "bound"},
        "assets": [
            {
                "path": rpm.relative_to(tmp_path).as_posix(),
                "size": rpm.stat().st_size,
                "sha256": sha256(rpm),
            }
        ],
    }
    return rpm, proof


def test_candidate_requires_exact_native_smoke_package(tmp_path, inputs):
    rpm, proof = inputs
    digest = sha256(rpm)
    assert candidate.candidate_input(tmp_path, proof, VERSION, SOURCE, RUN_ID, ATTEMPT) == (
        rpm,
        digest,
    )
    rpm.write_bytes(b"different-rpm-fixture")
    with pytest.raises(candidate.QualificationError, match="RPM bytes differ"):
        candidate.candidate_input(tmp_path, proof, VERSION, SOURCE, RUN_ID, ATTEMPT)


def test_fedora_archive_verified_before_local_image_import(tmp_path, monkeypatch):
    archive = tmp_path / candidate.FEDORA_ARCHIVE
    archive.write_bytes(b"verified archive")
    monkeypatch.setattr(candidate, "FEDORA_SIZE", archive.stat().st_size)
    monkeypatch.setattr(candidate, "FEDORA_SHA256", sha256(archive))
    commands = []
    monkeypatch.setattr(candidate.subprocess, "run", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr(candidate, "import_fedora_image", lambda source, temporary: str(source))
    assert candidate.load_fedora_image(tmp_path) == str(archive)
    assert commands[0][-1] == candidate.FEDORA_URL
    archive.write_bytes(b"modified archive")
    commands.clear()
    with pytest.raises(candidate.QualificationError, match="differs from the pinned input"):
        candidate.load_fedora_image(tmp_path)
    assert [command[0] for command in commands] == ["curl"]


@pytest.mark.parametrize("store", ["classic", "containerd", "wrong"])
def test_docker_load_binds_the_fedora_manifest_in_both_image_stores(tmp_path, monkeypatch, store):
    config = "sha256:" + hashlib.sha256(b"config").hexdigest()
    layer = "sha256:" + hashlib.sha256(b"layer").hexdigest()
    manifest = json.dumps({"config": {"digest": config}, "layers": [{"digest": layer}]}).encode()
    image = "sha256:" + hashlib.sha256(manifest).hexdigest()
    index = {"manifests": [{"digest": image}]}
    files = {
        "index.json": json.dumps(index).encode(),
        "oci-layout": b'{"imageLayoutVersion":"1.0.0"}',
        "blobs/" + image.replace(":", "/"): manifest,
        "blobs/" + config.replace(":", "/"): b"config",
        "blobs/" + layer.replace(":", "/"): b"layer",
    }
    archive = tmp_path / "fedora.tar.xz"
    with tarfile.open(archive, "w:xz") as output:
        for name in ("blobs", "blobs/sha256"):
            directory = tarfile.TarInfo(name)
            directory.type = tarfile.DIRTYPE
            output.addfile(directory)
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))

    tag = f"localhost/row-rpm-qualification:{tmp_path.name}"
    def docker_load(args, **kwargs):
        assert args[:4] == ["docker", "image", "load", "--input"]
        with tarfile.open(args[-1]) as loaded:
            classic, = json.load(loaded.extractfile("manifest.json"))
            assert classic == {"Config": "blobs/" + config.replace(":", "/"), "RepoTags": [tag],
                               "Layers": ["blobs/" + layer.replace(":", "/")]}
            oci, = json.load(loaded.extractfile("index.json"))["manifests"]
            assert oci == {"digest": image, "annotations": {"org.opencontainers.image.ref.name": tag}}
            assert loaded.extractfile("blobs/" + image.replace(":", "/")).read() == manifest

    observed = {"classic": config, "containerd": image, "wrong": "sha256:" + "0" * 64}[store]
    monkeypatch.setattr(candidate, "IMAGE", image)
    monkeypatch.setattr(candidate.subprocess, "run", docker_load)
    monkeypatch.setattr(candidate.subprocess, "check_output", lambda args, **kwargs: observed)
    if store == "wrong":
        with pytest.raises(candidate.QualificationError, match="differs from the pinned Fedora"):
            candidate.import_fedora_image(archive, tmp_path)
    else:
        assert candidate.import_fedora_image(archive, tmp_path) == observed


@pytest.mark.parametrize(("name", "member_type"), [
    ("../outside", tarfile.REGTYPE),
    ("index.json", tarfile.SYMTYPE),
    ("blobs/sha256/" + "0" * 64, tarfile.LNKTYPE),
    ("oci-layout", tarfile.FIFOTYPE),
    ("extra", tarfile.DIRTYPE),
])
def test_fedora_import_rejects_members_outside_regular_oci_layout(tmp_path, name, member_type):
    archive = tmp_path / "fedora.tar.xz"
    with tarfile.open(archive, "w:xz") as output:
        member = tarfile.TarInfo(name)
        member.type = member_type
        if member.islnk() or member.issym():
            member.linkname = "../outside"
        output.addfile(member)
    with pytest.raises(candidate.QualificationError, match="Unexpected member"):
        candidate.import_fedora_image(archive, tmp_path)
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source", {"head": "b" * 40}),
        ("run_id", "191"),
        ("run_attempt", "1"),
        ("native_smoke_outcome", "failure"),
        ("native_executable_byte_binding", {"status": "not-bound"}),
    ],
)
def test_run_refuses_incompatible_native_proof(tmp_path, inputs, field, replacement):
    _, proof = inputs
    proof[field] = replacement
    with pytest.raises(candidate.QualificationError, match="candidate source, run, and smoke"):
        candidate.candidate_input(tmp_path, proof, VERSION, SOURCE, RUN_ID, ATTEMPT)


def test_result_requires_both_expected_package_hashes_and_complete_recovery():
    candidate_digest = "d" * 64
    record = {
        "schema": "remote-ops-workspace/rpm-recovery/v1",
        "backup_created_with": "verified-candidate-launcher-before-upgrade",
        "backup_sha256": "a" * 64,
        "previous": {
            "version": candidate.PREVIOUS_VERSION,
            "package_sha256": candidate.PREVIOUS_SHA256,
            "architecture": "x86_64",
            "launcher_sha256": "b" * 64,
        },
        "candidate": {
            "version": VERSION,
            "package_sha256": candidate_digest,
            "architecture": "x86_64",
            "launcher_sha256": "c" * 64,
        },
        **dict.fromkeys(candidate.CHECKS, True),
    }
    candidate.verify_receipt(record, VERSION, candidate_digest)
    wrong = deepcopy(record)
    wrong["previous"]["package_sha256"] = candidate_digest
    with pytest.raises(candidate.QualificationError, match="different package"):
        candidate.verify_receipt(wrong, VERSION, candidate_digest)
    record["restored_profiles_and_vault_read_by_previous_launcher"] = False
    with pytest.raises(candidate.QualificationError, match="Incomplete"):
        candidate.verify_receipt(record, VERSION, candidate_digest)

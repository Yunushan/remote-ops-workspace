from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from remote_ops_workspace import keys
from remote_ops_workspace.keys import KeygenPlan


def test_keygen_plan_covers_rsa_options_and_redacted_printable(tmp_path: Path) -> None:
    plan = keys.build_keygen_plan(
        tmp_path / "id_rsa",
        key_type="rsa",
        bits=3072,
        comment="production operator",
        passphrase="never-render-this",
        resident=True,
    )

    assert plan.native is True
    assert plan.command == [
        "remote-ops-keygen",
        "-t",
        "rsa",
        "-f",
        str(tmp_path / "id_rsa"),
        "-N",
        "***REDACTED***",
        "-b",
        "3072",
        "-O",
        "resident",
        "-C",
        "production operator",
    ]
    assert "never-render-this" not in plan.printable()


def test_keygen_plan_rejects_unsupported_encrypted_key_types(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not supported for FIDO"):
        keys.build_keygen_plan(
            tmp_path / "id_ed25519_sk",
            key_type="ed25519-sk",
            passphrase="secret",
        )
    with pytest.raises(ValueError, match="not available for dsa"):
        keys.build_keygen_plan(
            tmp_path / "id_dsa",
            key_type="dsa",
            passphrase="secret",
        )


def test_run_keygen_handles_dry_run_native_and_subprocess_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    subprocess_calls: list[tuple[list[str], bool]] = []
    native_calls: list[KeygenPlan] = []
    monkeypatch.setattr(
        keys.subprocess,
        "run",
        lambda command, *, check: subprocess_calls.append((command, check)),
    )
    monkeypatch.setattr(keys, "_write_native_key_pair", native_calls.append)
    subprocess_plan = keys.build_keygen_plan(tmp_path / "plain")
    native_plan = keys.build_keygen_plan(tmp_path / "encrypted", passphrase="secret")

    assert keys.run_keygen(subprocess_plan, dry_run=True) is subprocess_plan
    assert subprocess_calls == []
    assert keys.run_keygen(subprocess_plan) is subprocess_plan
    assert subprocess_calls == [(subprocess_plan.command, True)]
    assert keys.run_keygen(native_plan) is native_plan
    assert native_calls == [native_plan]


@pytest.mark.parametrize(
    ("key_type", "bits", "public_prefix"),
    [
        ("ed25519", None, b"ssh-ed25519 "),
        ("rsa", 2048, b"ssh-rsa "),
        ("ecdsa", 384, b"ecdsa-sha2-nistp384 "),
    ],
)
def test_native_encrypted_key_generation_writes_loadable_pair(
    tmp_path: Path,
    key_type: str,
    bits: int | None,
    public_prefix: bytes,
) -> None:
    output = tmp_path / f"id_{key_type}"
    plan = keys.build_keygen_plan(
        output,
        key_type=key_type,
        bits=bits,
        comment="operator@example",
        passphrase="correct horse battery staple",
    )

    keys.run_keygen(plan)

    private_key = serialization.load_ssh_private_key(
        output.read_bytes(),
        password=b"correct horse battery staple",
    )
    public_bytes = output.with_name(f"{output.name}.pub").read_bytes()
    assert private_key is not None
    assert public_bytes.startswith(public_prefix)
    assert public_bytes.endswith(b" operator@example\n")


def test_native_encrypted_key_generation_reports_missing_bcrypt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakePrivateKey:
        def private_bytes(self, **_kwargs: object) -> bytes:
            raise UnsupportedAlgorithm("Need bcrypt module")

    class FakeEd25519PrivateKey:
        @staticmethod
        def generate() -> FakePrivateKey:
            return FakePrivateKey()

    monkeypatch.setattr(ed25519, "Ed25519PrivateKey", FakeEd25519PrivateKey)
    output = tmp_path / "id_ed25519"
    plan = keys.build_keygen_plan(output, passphrase="secret")

    with pytest.raises(ValueError, match="requires bcrypt"):
        keys.run_keygen(plan)
    assert not output.exists()
    assert not output.with_name(f"{output.name}.pub").exists()


@pytest.mark.parametrize("occupied", ["private", "public"])
def test_native_key_generation_refuses_to_overwrite_either_key_file(
    tmp_path: Path,
    occupied: str,
) -> None:
    output = tmp_path / "id_ed25519"
    occupied_path = output if occupied == "private" else output.with_name("id_ed25519.pub")
    occupied_path.write_text("keep", encoding="utf-8")
    plan = keys.build_keygen_plan(output, passphrase="secret")

    with pytest.raises(ValueError, match="key file already exists"):
        keys.run_keygen(plan)
    assert occupied_path.read_text(encoding="utf-8") == "keep"


def test_native_key_generation_rejects_manually_constructed_unknown_type(
    tmp_path: Path,
) -> None:
    plan = KeygenPlan(
        command=["remote-ops-keygen"],
        output=tmp_path / "id_unknown",
        key_type="dsa",
        passphrase="secret",
        native=True,
    )

    with pytest.raises(ValueError, match="unsupported software key type: dsa"):
        keys.run_keygen(plan)


def test_ecdsa_curve_defaults_maps_supported_sizes_and_rejects_unknown() -> None:
    assert isinstance(keys._ecdsa_curve(None), ec.SECP256R1)
    assert isinstance(keys._ecdsa_curve(256), ec.SECP256R1)
    assert isinstance(keys._ecdsa_curve(384), ec.SECP384R1)
    assert isinstance(keys._ecdsa_curve(521), ec.SECP521R1)
    with pytest.raises(ValueError, match="ecdsa bits must be one of"):
        keys._ecdsa_curve(255)

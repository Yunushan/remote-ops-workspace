from __future__ import annotations

import shlex
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SOFTWARE_KEY_TYPES = {"ed25519", "ecdsa", "rsa"}
SECURITY_KEY_TYPES = {"ed25519-sk", "ecdsa-sk"}


@dataclass(slots=True)
class KeygenPlan:
    command: list[str]
    output: Path
    key_type: str
    bits: int | None = None
    comment: str = ""
    passphrase: str = field(default="", repr=False)
    native: bool = False

    def printable(self) -> str:
        return shlex.join(self.command)


def build_keygen_plan(
    output: Path,
    key_type: str = "ed25519",
    bits: int | None = None,
    comment: str = "",
    passphrase: str = "",
    resident: bool = False,
) -> KeygenPlan:
    if key_type in SECURITY_KEY_TYPES and passphrase:
        raise ValueError(
            "--passphrase-env is not supported for FIDO/security-key generation; "
            "run without it and let ssh-keygen prompt interactively"
        )

    native = bool(passphrase)
    if native and key_type not in SOFTWARE_KEY_TYPES:
        raise ValueError(f"in-process encrypted key generation is not available for {key_type}")

    command = [
        "remote-ops-keygen" if native else "ssh-keygen",
        "-t",
        key_type,
        "-f",
        str(output),
        "-N",
        "***REDACTED***" if native else "",
    ]
    if key_type == "rsa" and bits:
        command.extend(["-b", str(bits)])
    if resident:
        command.extend(["-O", "resident"])
    if comment:
        command.extend(["-C", comment])
    return KeygenPlan(
        command=command,
        output=output,
        key_type=key_type,
        bits=bits,
        comment=comment,
        passphrase=passphrase,
        native=native,
    )


def run_keygen(plan: KeygenPlan, dry_run: bool = False) -> KeygenPlan:
    if dry_run:
        return plan
    if plan.native:
        _write_native_key_pair(plan)
        return plan
    subprocess.run(plan.command, check=True)  # noqa: S603 - argv list, no shell
    return plan


def _write_native_key_pair(plan: KeygenPlan) -> None:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise ValueError("encrypted key generation requires: pip install -e '.[security]'") from exc

    private_path = plan.output
    public_path = private_path.with_name(f"{private_path.name}.pub")
    if private_path.exists() or public_path.exists():
        raise ValueError(f"key file already exists: {private_path}")

    if plan.key_type == "ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
    elif plan.key_type == "rsa":
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=plan.bits or 3072)
    elif plan.key_type == "ecdsa":
        private_key = ec.generate_private_key(_ecdsa_curve(plan.bits))
    else:
        raise ValueError(f"unsupported software key type: {plan.key_type}")

    passphrase = plan.passphrase.encode("utf-8")
    encryption = serialization.BestAvailableEncryption(passphrase)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=encryption,
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    if plan.comment:
        public_bytes += f" {plan.comment}".encode("utf-8")
    public_bytes += b"\n"

    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(private_bytes)
    _chmod_owner_only(private_path)
    public_path.write_bytes(public_bytes)


def _ecdsa_curve(bits: int | None):  # type: ignore[no-untyped-def]
    from cryptography.hazmat.primitives.asymmetric import ec

    curves = {
        256: ec.SECP256R1,
        384: ec.SECP384R1,
        521: ec.SECP521R1,
    }
    curve = curves.get(bits or 256)
    if curve is None:
        raise ValueError("ecdsa bits must be one of: 256, 384, 521")
    return curve()


def _chmod_owner_only(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

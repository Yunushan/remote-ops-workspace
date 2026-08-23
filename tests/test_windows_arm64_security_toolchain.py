from __future__ import annotations

import json
from pathlib import Path


def test_windows_arm64_security_installer_uses_recorded_modern_toolchain() -> None:
    manifest = json.loads(Path("configs/release_toolchain.json").read_text(encoding="utf-8"))
    script = Path("scripts/install_windows_arm64_security.ps1").read_text(encoding="utf-8")
    openssl = next(
        row for row in manifest["native_toolchains"]["windows"] if row["name"] == "openssl"
    )
    cryptography = next(
        row for row in manifest["python_packages"] if row["name"] == "cryptography"
    )

    assert openssl["targets"] == ["windows-arm64"]
    assert openssl["linkage"] == "static"
    assert openssl["vcpkg_commit"] == "42e4e33e1505c9f47b58c21e0f557c1571b751ee"
    assert openssl["triplet"] == "arm64-windows-static-md"
    assert '[string]$OpenSsl.vcpkg_commit' in script
    assert '[string]$OpenSsl.triplet' in script
    assert 'OPENSSL_STATIC = "1"' in script
    assert 'OPENSSL_NO_VENDOR = "1"' in script
    assert "--no-build-isolation --no-binary=cryptography" in script
    assert "requirements-release.txt" in script
    assert "requirements-release-compat.txt" not in script
    assert "legacy-security" not in script
    assert "ExpectedCryptography" in script
    assert str(cryptography["version"]) not in script

param(
  [string]$ConstraintsPath = (Join-Path $PSScriptRoot "..\requirements-release.txt")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ManifestPath = Join-Path $PSScriptRoot "..\configs\release_toolchain.json"
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$OpenSslRows = @(
  $Manifest.native_toolchains.windows | Where-Object { $_.name -eq "openssl" }
)
$CryptographyRows = @(
  $Manifest.python_packages | Where-Object { $_.name -eq "cryptography" }
)
if ($OpenSslRows.Count -ne 1 -or $CryptographyRows.Count -ne 1) {
  throw "release toolchain must define one Windows OpenSSL row and one cryptography row"
}

$OpenSsl = $OpenSslRows[0]
$ExpectedCryptography = [string]$CryptographyRows[0].version
$ExpectedOpenSsl = "OpenSSL $([string]$OpenSsl.version)"
$VcpkgCommit = [string]$OpenSsl.vcpkg_commit
$Triplet = [string]$OpenSsl.triplet
if (
  [string]$OpenSsl.provider -ne "vcpkg" -or
  [string]$OpenSsl.linkage -ne "static" -or
  $Triplet -ne "arm64-windows-static-md" -or
  @($OpenSsl.targets) -notcontains "windows-arm64"
) {
  throw "release toolchain does not define the required static Windows ARM64 OpenSSL policy"
}
if (-not $env:VCPKG_INSTALLATION_ROOT) {
  throw "Windows ARM64 runner did not provide VCPKG_INSTALLATION_ROOT"
}

$VcpkgRoot = $env:VCPKG_INSTALLATION_ROOT
& git -C $VcpkgRoot fetch --no-tags --depth 1 origin $VcpkgCommit
if ($LASTEXITCODE -ne 0) { throw "vcpkg pinned-commit fetch failed" }
& git -C $VcpkgRoot checkout --detach $VcpkgCommit
if ($LASTEXITCODE -ne 0) { throw "vcpkg pinned-commit checkout failed" }
if ((& git -C $VcpkgRoot rev-parse HEAD).Trim() -ne $VcpkgCommit) {
  throw "vcpkg checkout did not resolve to the pinned commit"
}

& (Join-Path $VcpkgRoot "bootstrap-vcpkg.bat") -disableMetrics
if ($LASTEXITCODE -ne 0) { throw "vcpkg bootstrap failed" }
$Vcpkg = Join-Path $VcpkgRoot "vcpkg.exe"
& $Vcpkg install "openssl:$Triplet" --clean-after-build
if ($LASTEXITCODE -ne 0) { throw "ARM64 OpenSSL installation failed" }

$OpenSslRoot = Join-Path $VcpkgRoot "installed\$Triplet"
foreach ($RequiredPath in @(
  "include\openssl\opensslv.h",
  "lib\libcrypto.lib",
  "lib\libssl.lib"
)) {
  if (-not (Test-Path -LiteralPath (Join-Path $OpenSslRoot $RequiredPath))) {
    throw "ARM64 OpenSSL output missing: $RequiredPath"
  }
}

$env:OPENSSL_DIR = $OpenSslRoot
$env:OPENSSL_STATIC = "1"
$env:OPENSSL_NO_VENDOR = "1"
if ($env:GITHUB_ENV) {
  Add-Content -LiteralPath $env:GITHUB_ENV "OPENSSL_DIR=$OpenSslRoot"
  Add-Content -LiteralPath $env:GITHUB_ENV "OPENSSL_STATIC=1"
  Add-Content -LiteralPath $env:GITHUB_ENV "OPENSSL_NO_VENDOR=1"
}

python -m pip install --constraint $ConstraintsPath pip setuptools wheel maturin cffi pycparser
if ($LASTEXITCODE -ne 0) { throw "pinned cryptography build dependency installation failed" }
python -m pip install --no-cache-dir --no-build-isolation --no-binary=cryptography --constraint $ConstraintsPath "cryptography==$ExpectedCryptography"
if ($LASTEXITCODE -ne 0) { throw "maintained Windows ARM64 cryptography source build failed" }

$Verify = @"
import cryptography
from cryptography.hazmat.backends.openssl.backend import backend
actual_openssl = backend.openssl_version_text()
assert cryptography.__version__ == "$ExpectedCryptography", cryptography.__version__
assert actual_openssl.startswith("$ExpectedOpenSsl"), actual_openssl
print(f"cryptography={cryptography.__version__} openssl={actual_openssl}")
"@
python -c $Verify
if ($LASTEXITCODE -ne 0) { throw "Windows ARM64 cryptography runtime verification failed" }

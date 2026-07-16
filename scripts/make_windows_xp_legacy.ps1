param(
  [ValidateSet("x86", "x64")]
  [string]$Arch = "x86",
  [string]$Dist = "native-dist\windows-xp",
  [string]$Csc = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Get-ProjectVersion {
  $Pyproject = Get-Content -Raw (Join-Path $Root "pyproject.toml")
  if ($Pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "pyproject.toml does not define project.version"
  }
  return $Matches[1]
}

function Get-LegacyCsc([string]$RequestedCompiler, [string]$TargetArch) {
  if ($RequestedCompiler) {
    if (!(Test-Path -LiteralPath $RequestedCompiler)) {
      throw "XP legacy C# compiler does not exist: $RequestedCompiler"
    }
    return (Resolve-Path -LiteralPath $RequestedCompiler).Path
  }
  $FrameworkRoot = if ($TargetArch -eq "x64") {
    Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319"
  } else {
    Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319"
  }
  $Compiler = Join-Path $FrameworkRoot "csc.exe"
  if (!(Test-Path -LiteralPath $Compiler)) {
    throw "A .NET Framework v4 C# compiler is required for the Windows XP legacy host. Install .NET Framework 4 tooling or pass -Csc <path>."
  }
  return $Compiler
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  [System.IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-Sha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$Version = Get-ProjectVersion
$ExpectedTag = "v$Version"
if ($env:RELEASE_TAG -and $env:RELEASE_TAG -ne $ExpectedTag) {
  throw "RELEASE_TAG='$($env:RELEASE_TAG)' does not match project version $ExpectedTag"
}
if ($env:GITHUB_REF_NAME -and ($env:GITHUB_REF_TYPE -eq "tag" -or $env:GITHUB_REF_NAME.StartsWith("v")) -and $env:GITHUB_REF_NAME -ne $ExpectedTag) {
  throw "GITHUB_REF_NAME='$($env:GITHUB_REF_NAME)' does not match project version $ExpectedTag"
}

$Target = "windows-xp-native-$Arch"
$ArtifactArch = "windows-xp-$Arch"
$OutDir = Join-Path $Root (Join-Path $Dist $Arch)
$BuildDir = Join-Path $Root (Join-Path "build\native\windows-xp" $Arch)
$StageDir = Join-Path $BuildDir "stage"
$SourceTemplate = Join-Path $Root "legacy\xp_host\RemoteOpsXpHost.template.cs"
$GeneratedSource = Join-Path $BuildDir "RemoteOpsXpHost.cs"
$Compiler = Get-LegacyCsc -RequestedCompiler $Csc -TargetArch $Arch

Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $OutDir, $StageDir, (Join-Path $StageDir "bin"), (Join-Path $StageDir "docs") | Out-Null

$Source = (Get-Content -Raw $SourceTemplate).Replace("@VERSION@", $Version)
Write-Utf8NoBom -Path $GeneratedSource -Content $Source
$HostExe = Join-Path $StageDir "bin\row-xp-host.exe"
& $Compiler /nologo /target:exe /platform:$Arch /optimize+ /out:$HostExe /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll $GeneratedSource
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $HostExe)) {
  throw "The XP legacy host compiler did not create $HostExe"
}

$VersionOutput = & $HostExe --version
if ($LASTEXITCODE -ne 0 -or ($VersionOutput -join "`n") -notmatch [regex]::Escape($Version)) {
  throw "XP legacy host --version smoke failed"
}
$DryRunOutput = & $HostExe --loopback-dry-run
if ($LASTEXITCODE -ne 0 -or ($DryRunOutput -join "`n") -notmatch "loopback profile dry-run: passed") {
  throw "XP legacy host loopback dry-run smoke failed"
}
$ProfileOutput = & $HostExe --legacy-profile
if ($LASTEXITCODE -ne 0 -or ($ProfileOutput -join "`n") -notmatch "legacy crypto scope: profile-only") {
  throw "XP legacy host security-profile smoke failed"
}

Copy-Item (Join-Path $Root "LICENSE") (Join-Path $StageDir "docs\LICENSE")
Copy-Item (Join-Path $Root "NOTICE") (Join-Path $StageDir "docs\NOTICE")
@'
# Remote Ops Workspace XP Host

This separate legacy host is built with the .NET Framework v4 WinForms stack,
not the modern Python/PyQt6 runtime. It is intended only for Windows XP native
host compatibility evidence and retains legacy protocol compatibility as an
isolated, per-profile opt-in. Modern Windows, Linux and macOS defaults remain
hardened and unchanged.

Commands:

* `bin\row-xp-host.exe --version`
* `bin\row-xp-host.exe --loopback-dry-run`
* `bin\row-xp-host.exe --legacy-profile`
* `bin\row-xp-host.exe --gui-smoke`
'@ | Set-Content -Encoding ASCII (Join-Path $StageDir "README_XP.txt")

$NativeZip = Join-Path $OutDir "remote-ops-workspace-v$Version-$ArtifactArch-native.zip"
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $NativeZip -Force
if (!(Test-Path -LiteralPath $NativeZip)) {
  throw "XP legacy host packaging did not create $NativeZip"
}

$ManifestPath = Join-Path $OutDir "remote-ops-workspace-v$Version-$ArtifactArch-native-manifest.json"
$Manifest = @(
  @{
    file = (Split-Path -Leaf $NativeZip)
    architecture = $Arch
    format = "zip"
    size_bytes = (Get-Item -LiteralPath $NativeZip).Length
    sha256 = Get-Sha256 -Path $NativeZip
    build_stack = "dotnet-framework-v4-winforms"
    current_python_pyqt6_stack = $false
    legacy_compatibility_profile = "isolated-opt-in"
  }
)
Write-Utf8NoBom -Path $ManifestPath -Content (ConvertTo-Json -InputObject $Manifest -Depth 6)

$ChecksumsPath = Join-Path $OutDir "remote-ops-workspace-v$Version-$ArtifactArch-native-SHA256SUMS.txt"
$ChecksumLines = @(
  "$(Get-Sha256 -Path $NativeZip)  $(Split-Path -Leaf $NativeZip)",
  "$(Get-Sha256 -Path $ManifestPath)  $(Split-Path -Leaf $ManifestPath)"
)
[System.IO.File]::WriteAllLines($ChecksumsPath, $ChecksumLines, [System.Text.Encoding]::ASCII)

& python scripts/check_platform_promotion_artifacts.py --target $Target --assets-dir $OutDir --tag $ExpectedTag --strict
if ($LASTEXITCODE -ne 0) {
  throw "XP legacy host artifacts failed strict promotion validation for $Target"
}

Write-Host "created $NativeZip"
Write-Host "created $ManifestPath"
Write-Host "created $ChecksumsPath"

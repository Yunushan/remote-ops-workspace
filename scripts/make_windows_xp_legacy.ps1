param(
  [ValidateSet("x86", "x64")]
  [string]$Arch = "x86",
  [string]$Dist = "native-dist\windows-xp",
  [string]$Csc = "",
  [string]$ReferencePackage = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "find_windows_signtool.ps1")
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

function Sign-XpExecutable([string]$Path) {
  foreach ($Name in @("ROW_WINDOWS_CERTIFICATE_BASE64", "ROW_WINDOWS_CERTIFICATE_PASSWORD", "ROW_WINDOWS_TIMESTAMP_URL")) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))) {
      throw "XP release signing requires $Name in the protected release environment."
    }
  }
  $SignTool = Find-WindowsSignTool
  $Timestamp = [uri]$env:ROW_WINDOWS_TIMESTAMP_URL
  if (!$Timestamp.IsAbsoluteUri -or $Timestamp.Scheme -notin @("http", "https") -or !$Timestamp.Host -or $Timestamp.UserInfo) {
    throw "XP release timestamping requires a credential-free HTTP or HTTPS URL."
  }
  $Certificate = Join-Path $env:RUNNER_TEMP "row-xp-$Arch-$([guid]::NewGuid()).pfx"
  try {
    [System.IO.File]::WriteAllBytes($Certificate, [Convert]::FromBase64String($env:ROW_WINDOWS_CERTIFICATE_BASE64))
    & $SignTool sign /q /fd SHA256 /tr $Timestamp.AbsoluteUri /td SHA256 /f $Certificate /p $env:ROW_WINDOWS_CERTIFICATE_PASSWORD $Path
    if ($LASTEXITCODE -ne 0) {
      throw "XP executable Authenticode signing failed."
    }
    & $SignTool verify /pa /all /tw $Path
    if ($LASTEXITCODE -ne 0) {
      throw "XP executable Authenticode or timestamp verification failed."
    }
  } finally {
    if (Test-Path -LiteralPath $Certificate) {
      Remove-Item -LiteralPath $Certificate -Force
    }
  }
}

function Get-ReferenceAssemblyPaths($Lock, [string]$Package, [string]$Directory) {
  if ((Get-Sha256 $Package) -cne $Lock.sha256) {
    throw ".NET Framework 4 reference package digest mismatch."
  }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $null = New-Item -ItemType Directory -Path $Directory
  $Archive = [IO.Compression.ZipFile]::OpenRead($Package)
  try {
    foreach ($Name in @("mscorlib.dll", "System.dll", "System.Drawing.dll", "System.Windows.Forms.dll")) {
      $Entry = $Archive.GetEntry("build/.NETFramework/v4.0/$Name")
      if ($null -eq $Entry) {
        throw "The .NET Framework 4 reference package is missing $Name."
      }
      $Path = Join-Path $Directory $Name
      [IO.Compression.ZipFileExtensions]::ExtractToFile($Entry, $Path)
      if ((Get-Sha256 $Path) -cne $Lock.assemblies.$Name) {
        throw ".NET Framework 4 reference assembly digest mismatch for $Name."
      }
      $Path
    }
  } finally {
    $Archive.Dispose()
  }
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
$ReferenceLock = Join-Path $Root "legacy\xp_host\net40-references.json"
$ReferenceLockHash = Get-Sha256 $ReferenceLock
$LockedReferences = Get-Content -Raw -LiteralPath $ReferenceLock | ConvertFrom-Json

Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $OutDir, $StageDir, (Join-Path $StageDir "bin"), (Join-Path $StageDir "docs") | Out-Null

if (!$ReferencePackage) {
  $ReferencePackage = Join-Path $BuildDir "net40-references.nupkg"
  Invoke-WebRequest -UseBasicParsing -Uri $LockedReferences.url -OutFile $ReferencePackage -TimeoutSec 90
}
$References = @(Get-ReferenceAssemblyPaths $LockedReferences (Resolve-Path -LiteralPath $ReferencePackage).Path (Join-Path $BuildDir "references"))
$ReferenceOptions = @($References | ForEach-Object { "/reference:$_" })
$CompilerHash = Get-Sha256 $Compiler
$Source = ([System.IO.File]::ReadAllText($SourceTemplate)).Replace("`r`n", "`n").Replace("@VERSION@", $Version)
Write-Utf8NoBom -Path $GeneratedSource -Content $Source
$SourceHash = Get-Sha256 $GeneratedSource
$HostExe = Join-Path $StageDir "bin\row-xp-host.exe"
& $Compiler /nologo /noconfig /nostdlib+ /target:exe /platform:$Arch /optimize+ "/out:$HostExe" @ReferenceOptions $GeneratedSource
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $HostExe)) {
  throw "The XP legacy host compiler did not create $HostExe"
}
if ((Get-Sha256 $Compiler) -cne $CompilerHash) {
  throw "The XP legacy host compiler changed during compilation."
}
if ((Get-Sha256 $GeneratedSource) -cne $SourceHash) {
  throw "The XP legacy host source changed during compilation."
}
if ((Get-Sha256 $ReferenceLock) -cne $ReferenceLockHash) {
  throw "The XP .NET Framework 4 reference lock changed during compilation."
}
foreach ($Path in $References) {
  $Name = Split-Path -Leaf $Path
  if ((Get-Sha256 $Path) -cne $LockedReferences.assemblies.$Name) {
    throw "The .NET Framework 4 reference assembly $Name changed during compilation."
  }
}

$Signed = $env:ROW_XP_REQUIRE_SIGNING -eq "1"
if ($env:GITHUB_REF_TYPE -eq "tag" -and !$Signed) {
  throw "An XP release tag must produce signed candidates."
}
if ($Signed) {
  Sign-XpExecutable $HostExe
}
$Signing = [ordered]@{
  release_channel = if ($Signed) { "production-signed" } else { "unsigned-preview" }
  production_trusted = $Signed
  authenticode_verified = $Signed
  timestamped = $Signed
}

$VersionOutput = & $HostExe --version
if ($LASTEXITCODE -ne 0 -or ($VersionOutput -join "`n") -notmatch [regex]::Escape($Version)) {
  throw "XP legacy host --version smoke failed"
}
$DryRunOutput = & $HostExe --loopback-dry-run
if ($LASTEXITCODE -ne 0 -or $DryRunOutput -cnotcontains "loopback TCP round trip: passed") {
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
    signing = $Signing
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

$BuildInputs = [ordered]@{
  schema_version = 1
  target = $Target
  release_tag = $ExpectedTag
  repository = $env:GITHUB_REPOSITORY
  source_ref = $env:GITHUB_REF
  source_sha = $env:GITHUB_SHA
  run_id = $env:GITHUB_RUN_ID
  run_attempt = $env:GITHUB_RUN_ATTEMPT
  compiler = [ordered]@{
    name = Split-Path -Leaf $Compiler
    file_version = (Get-Item -LiteralPath $Compiler).VersionInfo.FileVersion
    sha256 = $CompilerHash
  }
  reference_lock_sha256 = $ReferenceLockHash
  reference_package = $LockedReferences.package
  reference_package_version = $LockedReferences.version
  reference_package_sha256 = $LockedReferences.sha256
  reference_assemblies = $LockedReferences.assemblies
  generated_source_sha256 = $SourceHash
  executable_sha256 = Get-Sha256 $HostExe
  signing = $Signing
  archive_sha256 = Get-Sha256 $NativeZip
  native_manifest_sha256 = Get-Sha256 $ManifestPath
}
Write-Utf8NoBom -Path (Join-Path $BuildDir "xp-build-inputs.json") -Content (ConvertTo-Json -InputObject $BuildInputs -Depth 6)

Write-Host "created $NativeZip"
Write-Host "created $ManifestPath"
Write-Host "created $ChecksumsPath"

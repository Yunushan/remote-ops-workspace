param(
  [string]$Python = "python",
  [string]$Dist = "native-dist\windows",
  [ValidateSet("x86", "x64", "arm64")]
  [string]$Arch = "x64"
)

$ErrorActionPreference = "Stop"

function Get-ProjectVersion {
  $Pyproject = Get-Content -Raw (Join-Path $Root "pyproject.toml")
  if ($Pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "pyproject.toml does not define project.version"
  }
  return $Matches[1]
}

function Resolve-PathOrCreate([string]$Path) {
  New-Item -ItemType Directory -Force $Path | Out-Null
  return (Resolve-Path $Path).Path
}

function To-RepoPath([string]$Path) {
  return (Resolve-Path $Path).Path.Substring($Root.Length + 1).Replace("\", "/")
}

function Add-ArtifactIntegrity([hashtable]$Item) {
  $ArtifactPath = Join-Path $Root $Item["file"]
  $Item["size_bytes"] = (Get-Item $ArtifactPath).Length
  $Item["sha256"] = (Get-FileHash -Algorithm SHA256 $ArtifactPath).Hash.ToLowerInvariant()
  return $Item
}

function Write-NativeChecksums([string]$Version, [string]$OutDir, [string]$Arch, [string[]]$Paths) {
  $ChecksumPath = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch-native-SHA256SUMS.txt"
  $Lines = foreach ($Path in $Paths) {
    $Hash = (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
    "$Hash  $(Split-Path -Leaf $Path)"
  }
  $Lines | Set-Content -Encoding ASCII $ChecksumPath
  return $ChecksumPath
}

function Find-InnoSetup {
  $Command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
  if ($Command) {
    return $Command.Source
  }
  $Default = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  if (Test-Path $Default) {
    return $Default
  }
  throw "Inno Setup compiler is required. Install it with: choco install innosetup -y"
}

function Get-InnoArchitectureDirectives([string]$Arch) {
  switch ($Arch) {
    "x64" {
      return @"
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
"@
    }
    "arm64" {
      return @"
ArchitecturesAllowed=arm64
ArchitecturesInstallIn64BitMode=arm64
"@
    }
    default {
      return ""
    }
  }
}

function Get-WixArchitecture([string]$Arch) {
  switch ($Arch) {
    "x86" { return "x86" }
    "x64" { return "x64" }
    "arm64" { return "arm64" }
    default { throw "Unsupported Windows architecture: $Arch" }
  }
}

function Build-InnoSetupInstaller([string]$Version, [string]$Stage, [string]$OutDir, [string]$Arch) {
  $Iscc = Find-InnoSetup
  $Iss = Join-Path $BuildDir "remote-ops-workspace.iss"
  $OutputBase = "remote-ops-workspace-v$Version-windows-$Arch-setup"
  $ArchitectureDirectives = Get-InnoArchitectureDirectives $Arch
  $StageEscaped = $Stage.Replace("\", "\\")
  $OutEscaped = $OutDir.Replace("\", "\\")

@"
[Setup]
AppId={{5C887096-F4E5-4AB8-8D6F-65052D08D284}
AppName=Remote Ops Workspace
AppVersion=$Version
AppPublisher=Remote Ops Workspace Contributors
DefaultDirName={autopf}\Remote Ops Workspace
DefaultGroupName=Remote Ops Workspace
DisableProgramGroupPage=yes
OutputDir=$OutEscaped
OutputBaseFilename=$OutputBase
Compression=lzma2
SolidCompression=yes
$ArchitectureDirectives

[Files]
Source: "$StageEscaped\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Remote Ops Workspace CLI"; Filename: "{app}\bin\row.exe"
Name: "{autodesktop}\Remote Ops Workspace CLI"; Filename: "{app}\bin\row.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\bin\row.exe"; Parameters: "--version"; Description: "Show installed version"; Flags: postinstall nowait skipifsilent
"@ | Set-Content -Encoding UTF8 $Iss

  $InnoOutput = & $Iscc $Iss
  $InnoExitCode = $LASTEXITCODE
  $InnoOutput | ForEach-Object { Write-Host $_ }
  if ($InnoExitCode -ne 0) {
    throw "Inno Setup failed with exit code $InnoExitCode"
  }
  $Setup = Join-Path $OutDir "$OutputBase.exe"
  if (!(Test-Path $Setup)) {
    throw "Inno Setup did not create $Setup"
  }
  return $Setup
}

function Build-WixMsi([string]$Version, [string]$Stage, [string]$OutDir, [string]$Arch) {
  $env:PATH = "$env:PATH;$env:USERPROFILE\.dotnet\tools"
  $Wix = Get-Command "wix.exe" -ErrorAction SilentlyContinue
  if (!$Wix) {
    throw "WiX CLI is required. Install it with: dotnet tool install --global wix"
  }

  $Wxs = Join-Path $BuildDir "remote-ops-workspace.wxs"
  $Msi = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch.msi"
  $WixArch = Get-WixArchitecture $Arch
  $RowSource = XmlEscape (Join-Path $Stage "bin\row.exe")
  $LicenseSource = XmlEscape (Join-Path $Stage "docs\LICENSE")
  $NoticeSource = XmlEscape (Join-Path $Stage "docs\NOTICE")
  $ReadmeSource = XmlEscape (Join-Path $Stage "docs\README.md")
  $TargetSource = XmlEscape (Join-Path $Stage "RELEASE_TARGET.md")

@"
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="Remote Ops Workspace" Manufacturer="Remote Ops Workspace Contributors" Version="$Version" UpgradeCode="8F8A21B4-6E48-4B1A-9F5D-B9373E1807D0" Scope="perMachine">
    <MajorUpgrade DowngradeErrorMessage="A newer version of Remote Ops Workspace is already installed." />
    <MediaTemplate EmbedCab="yes" />
    <StandardDirectory Id="ProgramFilesFolder">
      <Directory Id="INSTALLFOLDER" Name="Remote Ops Workspace">
        <Directory Id="BINDIR" Name="bin">
          <Component Id="RowExeComponent" Guid="7689D62F-2557-4DD3-8C58-38C5E245E44C">
            <File Id="RowExe" Source="$RowSource" KeyPath="yes" />
          </Component>
        </Directory>
        <Directory Id="DOCDIR" Name="docs">
          <Component Id="LicenseComponent" Guid="D257B18C-6692-4C99-BF08-2DBFD3D053C9">
            <File Id="LicenseFile" Source="$LicenseSource" KeyPath="yes" />
          </Component>
          <Component Id="NoticeComponent" Guid="A30D9507-7836-47E3-A8F3-D91E7842EA48">
            <File Id="NoticeFile" Source="$NoticeSource" KeyPath="yes" />
          </Component>
          <Component Id="ReadmeComponent" Guid="0184E6B4-1D6F-4F2A-855A-F13BF37B1C9E">
            <File Id="ReadmeFile" Source="$ReadmeSource" KeyPath="yes" />
          </Component>
          <Component Id="TargetReadmeComponent" Guid="2A3A7D0E-1FF2-437E-88C4-8A432DB29D1B">
            <File Id="TargetReadmeFile" Source="$TargetSource" KeyPath="yes" />
          </Component>
        </Directory>
      </Directory>
    </StandardDirectory>
    <Feature Id="MainFeature" Title="Remote Ops Workspace" Level="1">
      <ComponentRef Id="RowExeComponent" />
      <ComponentRef Id="LicenseComponent" />
      <ComponentRef Id="NoticeComponent" />
      <ComponentRef Id="ReadmeComponent" />
      <ComponentRef Id="TargetReadmeComponent" />
    </Feature>
  </Package>
</Wix>
"@ | Set-Content -Encoding UTF8 $Wxs

  & $Wix.Source build $Wxs -arch $WixArch -o $Msi
  if (!(Test-Path $Msi)) {
    throw "WiX did not create $Msi"
  }
  $WixPdb = [System.IO.Path]::ChangeExtension($Msi, ".wixpdb")
  if (Test-Path $WixPdb) {
    Remove-Item -LiteralPath $WixPdb -Force
  }
  return $Msi
}

function XmlEscape([string]$Value) {
  return [System.Security.SecurityElement]::Escape($Value)
}

function Get-PythonArchitecture([string]$Python) {
  $Detected = & $Python -c "import platform,struct; m=platform.machine().lower(); bits=struct.calcsize('P')*8; print('arm64' if 'arm64' in m or 'aarch64' in m else ('x64' if bits == 64 else 'x86'))"
  if ($LASTEXITCODE -ne 0) {
    throw "Unable to detect Python architecture from $Python"
  }
  return $Detected.Trim()
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Version = Get-ProjectVersion
$Tag = $env:GITHUB_REF_NAME
if ($Tag -and $Tag -ne "v$Version") {
  throw "GITHUB_REF_NAME='$Tag' does not match project version v$Version"
}
$PythonArch = Get-PythonArchitecture $Python
if ($PythonArch -ne $Arch) {
  throw "Requested Windows architecture '$Arch' does not match Python architecture '$PythonArch'. Use a matching Python/PyInstaller toolchain."
}

$OutDir = Resolve-PathOrCreate (Join-Path $Root $Dist)
$BuildDir = Join-Path $Root "build\native\windows"
$Stage = Join-Path $BuildDir "stage"
$PyDist = Join-Path $BuildDir "pyinstaller-dist"
$PyWork = Join-Path $BuildDir "pyinstaller-work"
$Launcher = Join-Path $BuildDir "row_launcher.py"

Remove-Item -Recurse -Force $BuildDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $OutDir, $Stage, $PyDist, $PyWork | Out-Null

@"
from remote_ops_workspace.cli import main

raise SystemExit(main())
"@ | Set-Content -Encoding UTF8 $Launcher

& $Python -m PyInstaller `
  --clean `
  --noconfirm `
  --onefile `
  --name row `
  --console `
  --distpath $PyDist `
  --workpath $PyWork `
  --specpath $BuildDir `
  --collect-submodules remote_ops_workspace `
  --copy-metadata remote-ops-workspace `
  $Launcher

$RowExe = Join-Path $PyDist "row.exe"
if (!(Test-Path $RowExe)) {
  throw "PyInstaller did not create $RowExe"
}

New-Item -ItemType Directory -Force (Join-Path $Stage "bin"), (Join-Path $Stage "docs") | Out-Null
Copy-Item $RowExe (Join-Path $Stage "bin\row.exe")
Copy-Item (Join-Path $Root "LICENSE") (Join-Path $Stage "docs\LICENSE")
Copy-Item (Join-Path $Root "NOTICE") (Join-Path $Stage "docs\NOTICE")
Copy-Item (Join-Path $Root "README.md") (Join-Path $Stage "docs\README.md")
Copy-Item (Join-Path $Root "README.tr.md") (Join-Path $Stage "docs\README.tr.md")

@"
# Windows native release

Package: remote-ops-workspace
Version: v$Version
Target: Windows $Arch

This native package installs the standalone `row.exe` command built with
PyInstaller. Protocol sessions still depend on Windows system tools such as
OpenSSH, MSTSC, PuTTY, VcXsrv, and VNC clients.
"@ | Set-Content -Encoding UTF8 (Join-Path $Stage "RELEASE_TARGET.md")

$NativeZip = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch-native.zip"
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $NativeZip -Force

$SetupExe = Build-InnoSetupInstaller -Version $Version -Stage $Stage -OutDir $OutDir -Arch $Arch
$Msi = Build-WixMsi -Version $Version -Stage $Stage -OutDir $OutDir -Arch $Arch

$Manifest = @(
  @{
    phase = "phase-2-windows-native"
    target = "windows-$Arch-native-zip"
    label = "Windows $Arch native portable bundle"
    architecture = $Arch
    file = (To-RepoPath $NativeZip)
    format = "zip"
    install_command = "Extract and run bin\row.exe"
    notes = @("Standalone PyInstaller CLI executable plus docs.", "Built for Windows $Arch.")
  },
  @{
    phase = "phase-2-windows-native"
    target = "windows-$Arch-exe-installer"
    label = "Windows $Arch EXE installer"
    architecture = $Arch
    file = (To-RepoPath $SetupExe)
    format = "exe"
    install_command = "Run the installer interactively or with Inno Setup silent flags."
    notes = @("Unsigned Inno Setup installer for the standalone row.exe CLI.", "Built for Windows $Arch.")
  },
  @{
    phase = "phase-2-windows-native"
    target = "windows-$Arch-msi-installer"
    label = "Windows $Arch MSI installer"
    architecture = $Arch
    file = (To-RepoPath $Msi)
    format = "msi"
    install_command = "msiexec /i $(Split-Path -Leaf $Msi)"
    notes = @("Unsigned WiX MSI installer for managed Windows deployments.", "Built for Windows $Arch.")
  }
)

$Manifest = @($Manifest | ForEach-Object { Add-ArtifactIntegrity $_ })

$ManifestPath = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch-native-manifest.json"
$Manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $ManifestPath
$Checksums = Write-NativeChecksums -Version $Version -OutDir $OutDir -Arch $Arch -Paths @($NativeZip, $SetupExe, $Msi, $ManifestPath)

Write-Host "created $(To-RepoPath $NativeZip)"
Write-Host "created $(To-RepoPath $SetupExe)"
Write-Host "created $(To-RepoPath $Msi)"
Write-Host "created $(To-RepoPath $ManifestPath)"
Write-Host "created $(To-RepoPath $Checksums)"

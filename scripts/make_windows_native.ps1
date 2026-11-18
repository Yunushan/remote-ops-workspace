param(
  [string]$Python = "python",
  [string]$Dist = "native-dist\windows",
  [ValidateSet("x86", "x64", "arm64")]
  [string]$Arch = "x64",
  [string]$EnterpriseBundle,
  [guid]$EnterpriseDeploymentId = [guid]::Empty
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "find_windows_signtool.ps1")
. (Join-Path $PSScriptRoot "windows_enterprise_branding.ps1")
$ArtifactSigner = Join-Path $PSScriptRoot "sign_windows_artifact.ps1"

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

function Invoke-WindowsPyInstaller([string]$Python, [scriptblock]$Build) {
  $Executable = (Get-Command -Name $Python -CommandType Application -ErrorAction Stop).Path
  $OriginalPath = $env:PATH
  try {
    # PyInstaller uses PATH to resolve DLLs during analysis. Keep unrelated
    # host applications from supplying binaries such as the system ICU DLL.
    $env:PATH = @(
      [Environment]::SystemDirectory
      $env:SystemRoot
      (Split-Path -Parent $Executable)
    ) -join [IO.Path]::PathSeparator
    & $Build $Executable
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
  } finally {
    $env:PATH = $OriginalPath
  }
}

function Sign-NativeArtifact([string]$ArtifactPath) {
  if ($env:ROW_REQUIRE_RELEASE_SIGNING -eq "1") {
    & $ArtifactSigner -ArtifactPath $ArtifactPath | Out-Host
  }
}

function Find-InnoSetup {
  $Command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
  if ($Command) {
    return $Command.Source
  }
  # Winget installs Inno Setup per-user by default, while Chocolatey and the
  # standalone installer usually use one of the Program Files locations.
  # Build paths only after confirming each root exists.  PowerShell evaluates
  # every array expression before foreach, and Join-Path rejects a null root.
  $Candidates = @()
  $LocalAppData = [Environment]::GetEnvironmentVariable("LOCALAPPDATA")
  if (![string]::IsNullOrWhiteSpace($LocalAppData)) {
    $Candidates += (Join-Path $LocalAppData "Programs\Inno Setup 6\ISCC.exe")
  }
  foreach ($ProgramFilesRoot in @(
    [Environment]::GetEnvironmentVariable("ProgramFiles(x86)"),
    [Environment]::GetEnvironmentVariable("ProgramFiles")
  )) {
    if (![string]::IsNullOrWhiteSpace($ProgramFilesRoot)) {
      $Candidates += (Join-Path $ProgramFilesRoot "Inno Setup 6\ISCC.exe")
    }
  }
  foreach ($Candidate in $Candidates) {
    if (Test-Path -LiteralPath $Candidate) {
      return $Candidate
    }
  }
  throw "Inno Setup compiler is required. Install it with: winget install --id JRSoftware.InnoSetup --exact"
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

function Build-InnoSetupInstaller([string]$Version, [string]$Stage, [string]$OutDir, [string]$Arch, [string]$IconPath, [hashtable]$Branding) {
  $Iscc = Find-InnoSetup
  $Iss = Join-Path $BuildDir "remote-ops-workspace.iss"
  $OutputBase = "$($Branding.artifact_base)-setup"
  $ProductName = $Branding.name
  $WelcomeDirective = ""
  if ($Branding.enterprise) {
    $WelcomeDirective = "InfoBeforeFile=$(Join-Path $Stage 'docs\welcome.txt')"
  }
  $ArchitectureDirectives = Get-InnoArchitectureDirectives $Arch
  $GuiExe = Join-Path $Stage "bin\row-gui.exe"
  $GuiIconEntries = ""
  if (Test-Path $GuiExe) {
    $GuiIconEntries = @"
Name: "{group}\$ProductName GUI"; Filename: "{app}\bin\row-gui.exe"
Name: "{autodesktop}\$ProductName GUI"; Filename: "{app}\bin\row-gui.exe"; Tasks: desktopicon
"@
  }
  $StageEscaped = $Stage.Replace("\", "\\")
  $OutEscaped = $OutDir.Replace("\", "\\")
  $IconEscaped = $IconPath.Replace("\", "\\")
  $CompilerArgs = @()
  $SigningDirectives = ""
  if ($env:ROW_REQUIRE_RELEASE_SIGNING -eq "1") {
    $PowerShellExe = (Get-Process -Id $PID).Path.Replace('$', '$$')
    $SignerPath = $ArtifactSigner.Replace('$', '$$')
    # ISCC logs the callback command. The signer reads credentials from its environment.
    $CompilerArgs += ('/Srowrelease=$q{0}$q -NoLogo -NoProfile -NonInteractive -File $q{1}$q -ArtifactPath $f' -f $PowerShellExe, $SignerPath)
    $SigningDirectives = "SignTool=rowrelease`nSignedUninstaller=yes`nSignedUninstallerDir=$BuildDir"
  }

@"
[Setup]
AppId={{$($Branding.inno_id)}
AppName=$ProductName
AppVersion=$Version
AppPublisher=$($Branding.publisher)
DefaultDirName={autopf}\$($Branding.directory)
DefaultGroupName=$($Branding.directory)
DisableProgramGroupPage=yes
OutputDir=$OutEscaped
OutputBaseFilename=$OutputBase
SetupIconFile=$IconEscaped
$WelcomeDirective
Compression=lzma2
SolidCompression=yes
$ArchitectureDirectives
$SigningDirectives

[Files]
Source: "$StageEscaped\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
$GuiIconEntries
Name: "{group}\$ProductName CLI"; Filename: "{app}\bin\row.exe"
Name: "{autodesktop}\$ProductName CLI"; Filename: "{app}\bin\row.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\bin\row.exe"; Parameters: "--version"; Description: "Show installed version"; Flags: postinstall nowait skipifsilent
"@ | Set-Content -Encoding UTF8 $Iss

  $InnoOutput = & $Iscc @CompilerArgs $Iss
  $InnoExitCode = $LASTEXITCODE
  $InnoOutput | ForEach-Object { Write-Host $_ }
  if ($InnoExitCode -ne 0) {
    throw "Inno Setup failed with exit code $InnoExitCode"
  }
  $Setup = Join-Path $OutDir "$OutputBase.exe"
  if (!(Test-Path $Setup)) {
    throw "Inno Setup did not create $Setup"
  }
  if ($env:ROW_REQUIRE_RELEASE_SIGNING -eq "1") {
    $SignTool = Find-WindowsSignTool
    & $SignTool verify /pa /all /tw $Setup | Out-Host
    if ($LASTEXITCODE -ne 0) {
      throw "Inno Setup output failed Authenticode signature or timestamp verification"
    }
  }
  return $Setup
}

function Build-WixMsi([string]$Version, [string]$Stage, [string]$OutDir, [string]$Arch, [string]$IconPath, [hashtable]$Branding) {
  $env:PATH = "$env:PATH;$env:USERPROFILE\.dotnet\tools"
  $Wix = Get-Command "wix.exe" -ErrorAction SilentlyContinue
  if (!$Wix) {
    throw "WiX CLI is required. Install it with: dotnet tool install --global wix"
  }

  $Wxs = Join-Path $BuildDir "remote-ops-workspace.wxs"
  $Msi = Join-Path $OutDir "$($Branding.artifact_base).msi"
  $WixArch = Get-WixArchitecture $Arch
  $RowSource = XmlEscape (Join-Path $Stage "bin\row.exe")
  $RowGuiFile = ""
  $RowGuiComponent = ""
  $RowGuiReference = ""
  $RowGuiPath = Join-Path $Stage "bin\row-gui.exe"
  if (Test-Path $RowGuiPath) {
    $RowGuiSource = XmlEscape $RowGuiPath
    if ($Branding.enterprise) {
      $RowGuiComponent = @"
          <Component Id="RowGuiComponent" Guid="*">
            <File Id="RowGuiExe" Source="$RowGuiSource" KeyPath="yes" />
          </Component>
"@
      $RowGuiReference = '      <ComponentRef Id="RowGuiComponent" />'
    } else {
      $RowGuiFile = "            <File Id=`"RowGuiExe`" Source=`"$RowGuiSource`" />"
    }
  }
  $LicenseSource = XmlEscape (Join-Path $Stage "docs\LICENSE")
  $NoticeSource = XmlEscape (Join-Path $Stage "docs\NOTICE")
  $ThirdPartyNoticesSource = XmlEscape (Join-Path $Stage "docs\THIRD_PARTY_NOTICES.md")
  $ReadmeSource = XmlEscape (Join-Path $Stage "docs\README.md")
  $TargetSource = XmlEscape (Join-Path $Stage "RELEASE_TARGET.md")
  $PyQtLicenseSource = XmlEscape (Join-Path $Stage "docs\licenses\PyQt6-GPL-3.0.txt")
  $QtLicenseSource = XmlEscape (Join-Path $Stage "docs\licenses\Qt-LGPL-3.0.txt")
  $QtRelinkSource = XmlEscape (Join-Path $Stage "docs\licenses\Qt-Relinking.md")
  $IconSource = XmlEscape $IconPath
  $ProductName = XmlEscape $Branding.name
  $Publisher = XmlEscape $Branding.publisher
  $InstallDirectory = XmlEscape $Branding.directory
  $WelcomeComponent = ""
  $WelcomeReference = ""
  if ($Branding.enterprise) {
    $WelcomeSource = XmlEscape (Join-Path $Stage "docs\welcome.txt")
    $WelcomeComponent = @"
          <Component Id="WelcomeComponent" Guid="*">
            <File Id="WelcomeFile" Source="$WelcomeSource" KeyPath="yes" />
          </Component>
"@
    $WelcomeReference = '      <ComponentRef Id="WelcomeComponent" />'
  }

  $WixSource = @"
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="$ProductName" Manufacturer="$Publisher" Version="$Version" UpgradeCode="$($Branding.msi_id)" Scope="perMachine">
    <MajorUpgrade DowngradeErrorMessage="A newer version of $ProductName is already installed." />
    <MediaTemplate EmbedCab="yes" />
    <Icon Id="RemoteOpsWorkspaceIcon" SourceFile="$IconSource" />
    <Property Id="ARPPRODUCTICON" Value="RemoteOpsWorkspaceIcon" />
    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLFOLDER" Name="$InstallDirectory">
        <Directory Id="BINDIR" Name="bin">
          <Component Id="RowExeComponent" Guid="7689D62F-2557-4DD3-8C58-38C5E245E44C">
            <File Id="RowExe" Source="$RowSource" KeyPath="yes" />
$RowGuiFile
          </Component>
$RowGuiComponent
        </Directory>
        <Directory Id="DOCDIR" Name="docs">
          <Component Id="LicenseComponent" Guid="D257B18C-6692-4C99-BF08-2DBFD3D053C9">
            <File Id="LicenseFile" Source="$LicenseSource" KeyPath="yes" />
          </Component>
          <Component Id="NoticeComponent" Guid="A30D9507-7836-47E3-A8F3-D91E7842EA48">
            <File Id="NoticeFile" Source="$NoticeSource" KeyPath="yes" />
          </Component>
          <Component Id="ThirdPartyNoticesComponent" Guid="39A32D3A-CFE5-4F09-B4DA-6A5C93866E5C">
            <File Id="ThirdPartyNoticesFile" Source="$ThirdPartyNoticesSource" KeyPath="yes" />
          </Component>
          <Component Id="ReadmeComponent" Guid="0184E6B4-1D6F-4F2A-855A-F13BF37B1C9E">
            <File Id="ReadmeFile" Source="$ReadmeSource" KeyPath="yes" />
          </Component>
          <Component Id="TargetReadmeComponent" Guid="2A3A7D0E-1FF2-437E-88C4-8A432DB29D1B">
            <File Id="TargetReadmeFile" Source="$TargetSource" KeyPath="yes" />
          </Component>
$WelcomeComponent
          <Directory Id="LICENSESDIR" Name="licenses">
            <Component Id="PyQtLicenseComponent" Guid="BFA62B82-EA32-4B88-9FC2-88B20C0A4F7F">
              <File Id="PyQtLicenseFile" Source="$PyQtLicenseSource" KeyPath="yes" />
            </Component>
            <Component Id="QtLicenseComponent" Guid="0570ED19-9AC2-41BC-9B33-0A5674ACF0E1">
              <File Id="QtLicenseFile" Source="$QtLicenseSource" KeyPath="yes" />
            </Component>
            <Component Id="QtRelinkComponent" Guid="D7D26461-21E9-4B15-94B1-EF8AA8EF0C37">
              <File Id="QtRelinkFile" Source="$QtRelinkSource" KeyPath="yes" />
            </Component>
          </Directory>
        </Directory>
      </Directory>
    </StandardDirectory>
    <Feature Id="MainFeature" Title="$ProductName" Level="1">
      <ComponentRef Id="RowExeComponent" />
$RowGuiReference
      <ComponentRef Id="LicenseComponent" />
      <ComponentRef Id="NoticeComponent" />
      <ComponentRef Id="ThirdPartyNoticesComponent" />
      <ComponentRef Id="ReadmeComponent" />
      <ComponentRef Id="TargetReadmeComponent" />
      <ComponentRef Id="PyQtLicenseComponent" />
      <ComponentRef Id="QtLicenseComponent" />
      <ComponentRef Id="QtRelinkComponent" />
$WelcomeReference
    </Feature>
  </Package>
</Wix>
"@
  if ($Branding.enterprise) {
    # Let WiX derive each component identity from its distinct install path.
    $WixSource = $WixSource -replace '(<Component Id="[^"]+" Guid=")[0-9A-F-]{36}(">)', '${1}*${2}'
  }
  Set-Content -LiteralPath $Wxs -Encoding UTF8 -Value $WixSource

  & $Wix.Source build $Wxs -arch $WixArch -o $Msi | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "WiX MSI build failed with exit code $LASTEXITCODE"
  }
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

function Test-PythonModule([string]$Python, [string]$Module) {
  & $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$Module') else 1)"
  return $LASTEXITCODE -eq 0
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Version = Get-ProjectVersion
$Branding = @{
  enterprise = $false
  name = "Remote Ops Workspace"
  publisher = "Remote Ops Workspace Contributors"
  directory = "Remote Ops Workspace"
  inno_id = "5C887096-F4E5-4AB8-8D6F-65052D08D284"
  msi_id = "8F8A21B4-6E48-4B1A-9F5D-B9373E1807D0"
  artifact_base = "remote-ops-workspace-v$Version-windows-$Arch"
}
if ($EnterpriseBundle) {
  $Branding = Read-WindowsEnterpriseBranding $EnterpriseBundle $EnterpriseDeploymentId $Version
} elseif ($EnterpriseDeploymentId -ne [guid]::Empty) {
  throw "EnterpriseDeploymentId requires an EnterpriseBundle"
}
$ExpectedTag = "v$Version"
$ReleaseTag = $env:RELEASE_TAG
if ($ReleaseTag -and $ReleaseTag -ne $ExpectedTag) {
  throw "RELEASE_TAG='$ReleaseTag' does not match project version $ExpectedTag"
}
$RefName = $env:GITHUB_REF_NAME
$RefType = $env:GITHUB_REF_TYPE
if ($RefName -and (($RefType -eq "tag") -or $RefName.StartsWith("v")) -and $RefName -ne $ExpectedTag) {
  throw "GITHUB_REF_NAME='$RefName' does not match project version $ExpectedTag"
}
$PythonArch = Get-PythonArchitecture $Python
if ($PythonArch -ne $Arch) {
  throw "Requested Windows architecture '$Arch' does not match Python architecture '$PythonArch'. Use a matching Python/PyInstaller toolchain."
}
$BuildGuiLauncher = $Arch -ne "x86"
if ($BuildGuiLauncher -and !(Test-PythonModule -Python $Python -Module "PyQt6")) {
  throw "PyQt6 is required to build the Windows $Arch GUI launcher. Install the desktop extra before running this script."
}

$Destination = Join-Path $Root $Dist
$BuildDir = Join-Path $Root "build\native\windows"
if ($Branding.enterprise) {
  $EnterpriseOutput = Resolve-PathOrCreate (Join-Path $Destination "enterprise\$($Branding.inno_id)\$Arch")
  $OutDir = Join-Path $EnterpriseOutput "v$Version"
  if (Test-Path -LiteralPath $OutDir) {
    throw "Enterprise installers already exist at $OutDir. Use a separate -Dist for a new candidate."
  }
  $BuildDir = Join-Path $Root "build\native\windows-enterprise\$([guid]::NewGuid())"
} else {
  $OutDir = Resolve-PathOrCreate $Destination
}
$Stage = Join-Path $BuildDir "stage"
$PortableStage = Join-Path $BuildDir "portable-stage"
$PyDist = Join-Path $BuildDir "pyinstaller-dist"
$PyWork = Join-Path $BuildDir "pyinstaller-work"
$Launcher = Join-Path $BuildDir "row_launcher.py"
$GuiLauncher = Join-Path $BuildDir "row_gui_launcher.py"
$IconSvg = Join-Path $Root "src\remote_ops_workspace\assets\remote_ops_workspace.svg"
$IconIco = Join-Path $Root "src\remote_ops_workspace\assets\remote_ops_workspace.ico"
$GuiManifest = Join-Path $Root "src\remote_ops_workspace\assets\remote_ops_workspace_gui.manifest"
if (
  !(Test-Path -LiteralPath $IconSvg) -or
  !(Test-Path -LiteralPath $IconIco) -or
  !(Test-Path -LiteralPath $GuiManifest)
) {
  throw "Windows GUI assets (SVG, ICO, or manifest) are missing under src\\remote_ops_workspace\\assets"
}

if (Test-Path -LiteralPath $BuildDir) {
  $ResolvedBuildDir = (Resolve-Path -LiteralPath $BuildDir).Path
  if (!$ResolvedBuildDir.StartsWith("$Root\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Windows native build directory must stay in the repository"
  }
  $BuildParent = Get-Item -LiteralPath $ResolvedBuildDir
  while ($BuildParent.FullName -ne $Root) {
    if ($BuildParent.Attributes -band [IO.FileAttributes]::ReparsePoint) {
      throw "Windows native build directory must not traverse a reparse point"
    }
    $BuildParent = $BuildParent.Parent
  }
  Remove-Item -LiteralPath $ResolvedBuildDir -Recurse -Force
}
New-Item -ItemType Directory -Force $Stage, $PyDist, $PyWork | Out-Null

@"
from remote_ops_workspace.cli import main

raise SystemExit(main())
"@ | Set-Content -Encoding UTF8 $Launcher

if ($BuildGuiLauncher) {
@"
from remote_ops_workspace.gui import main

raise SystemExit(main())
"@ | Set-Content -Encoding UTF8 $GuiLauncher
}

$ServerImports = if ($Arch -ne "x86") {
  @("--collect-submodules", "pyftpdlib", "--collect-submodules", "OpenSSL", "--hidden-import", "asyncore", "--hidden-import", "asynchat")
} else { @() }

Invoke-WindowsPyInstaller -Python $Python -Build {
  param([string]$Executable)
  & $Executable -m PyInstaller `
    --clean `
    --noconfirm `
    --onefile `
    --name row `
    --console `
    --icon $IconIco `
    --distpath $PyDist `
    --workpath $PyWork `
    --specpath $BuildDir `
    --collect-submodules remote_ops_workspace `
    --collect-data remote_ops_workspace `
    --add-data "$Root\configs;remote_ops_workspace/configs" `
    --add-data "$Root\apps\web;remote_ops_workspace/web" `
    --copy-metadata remote-ops-workspace `
    @ServerImports `
    --exclude-module PyQt6 `
    --exclude-module remote_ops_workspace.gui `
    --exclude-module remote_ops_workspace.gui_designs `
    --exclude-module remote_ops_workspace.gui_editors `
    $Launcher
}

if ($BuildGuiLauncher) {
  Invoke-WindowsPyInstaller -Python $Python -Build {
    param([string]$Executable)
    & $Executable -m PyInstaller `
      --clean `
      --noconfirm `
      --onefile `
      --name row-gui `
      --windowed `
      --icon $IconIco `
      --manifest $GuiManifest `
      --add-data "$IconSvg;remote_ops_workspace/assets" `
      --distpath $PyDist `
      --workpath $PyWork `
      --specpath $BuildDir `
      --collect-submodules remote_ops_workspace `
      --collect-data remote_ops_workspace `
      --add-data "$Root\configs;remote_ops_workspace/configs" `
      --add-data "$Root\apps\web;remote_ops_workspace/web" `
      --copy-metadata remote-ops-workspace `
      @ServerImports `
      --hidden-import PyQt6.QtCore `
      --hidden-import PyQt6.QtGui `
      --hidden-import PyQt6.QtWidgets `
      $GuiLauncher
  }
}

$RowExe = Join-Path $PyDist "row.exe"
if (!(Test-Path $RowExe)) {
  throw "PyInstaller did not create $RowExe"
}
$RowGuiExe = Join-Path $PyDist "row-gui.exe"
if ($BuildGuiLauncher -and !(Test-Path $RowGuiExe)) {
  throw "PyInstaller did not create $RowGuiExe"
}

# Installer smoke compares the packaged executables with these build outputs.
Sign-NativeArtifact $RowExe
if ($BuildGuiLauncher) {
  Sign-NativeArtifact $RowGuiExe
}
New-Item -ItemType Directory -Force (Join-Path $Stage "bin"), (Join-Path $Stage "docs") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Stage "docs\licenses") | Out-Null
Copy-Item $RowExe (Join-Path $Stage "bin\row.exe")
if ($BuildGuiLauncher) {
  Copy-Item $RowGuiExe (Join-Path $Stage "bin\row-gui.exe")
}
Copy-Item (Join-Path $Root "LICENSE") (Join-Path $Stage "docs\LICENSE")
Copy-Item (Join-Path $Root "NOTICE") (Join-Path $Stage "docs\NOTICE")
Copy-Item (Join-Path $Root "redistribution-evidence\THIRD_PARTY_NOTICES.md") (Join-Path $Stage "docs\THIRD_PARTY_NOTICES.md")
Copy-Item (Join-Path $Root "redistribution-evidence\PyQt6-GPL-3.0.txt") (Join-Path $Stage "docs\licenses\PyQt6-GPL-3.0.txt")
Copy-Item (Join-Path $Root "redistribution-evidence\Qt-LGPL-3.0.txt") (Join-Path $Stage "docs\licenses\Qt-LGPL-3.0.txt")
Copy-Item (Join-Path $Root "redistribution-evidence\Qt-Relinking.md") (Join-Path $Stage "docs\licenses\Qt-Relinking.md")
Copy-Item (Join-Path $Root "README.md") (Join-Path $Stage "docs\README.md")
Copy-Item (Join-Path $Root "README.tr.md") (Join-Path $Stage "docs\README.tr.md")

$GuiTargetNote = if ($BuildGuiLauncher) {
  "It also includes the double-clickable bin\row-gui.exe launcher for the PyQt6 desktop UI."
} else {
  "This 32-bit Windows build is CLI-first because PyQt6 does not publish 32-bit Windows wheels."
}
$GuiLicenseNote = if ($BuildGuiLauncher) {
  "The bundled GUI uses PyQt6 under GPLv3 and Qt under LGPLv3; see docs\THIRD_PARTY_NOTICES.md and docs\licenses."
} else {
  "This x86 package does not include the PyQt6 GUI."
}

@"
# Windows native release

Package: remote-ops-workspace
Version: v$Version
Target: Windows $Arch

This native package installs the standalone row.exe command built with
PyInstaller. $GuiTargetNote $GuiLicenseNote Protocol sessions still depend on Windows system tools such as
OpenSSH, MSTSC, PuTTY, VcXsrv, and VNC clients.
"@ | Set-Content -Encoding UTF8 (Join-Path $Stage "RELEASE_TARGET.md")

if ($Branding.enterprise) {
  $StagedIcon = Join-Path $BuildDir "enterprise-logo.ico"
  $StagedWelcome = Join-Path $Stage "docs\welcome.txt"
  Copy-Item -LiteralPath $Branding.icon -Destination $StagedIcon
  Copy-Item -LiteralPath $Branding.welcome -Destination $StagedWelcome
  $BuiltSetup = Build-InnoSetupInstaller -Version $Version -Stage $Stage -OutDir $BuildDir -Arch $Arch -IconPath $StagedIcon -Branding $Branding
  $BuiltMsi = Build-WixMsi -Version $Version -Stage $Stage -OutDir $BuildDir -Arch $Arch -IconPath $StagedIcon -Branding $Branding
  Sign-NativeArtifact $BuiltMsi
  $Pending = Resolve-PathOrCreate (Join-Path $EnterpriseOutput ".pending-$([guid]::NewGuid())")
  $Artifacts = foreach ($Built in @($BuiltSetup, $BuiltMsi)) {
    $Name = Split-Path -Leaf $Built
    $Path = Join-Path $Pending $Name
    Copy-Item -LiteralPath $Built -Destination $Path
    @{
      name = $Name
      size_bytes = (Get-Item -LiteralPath $Path).Length
      sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
  }
  $DeploymentManifest = @{
    deployment_id = $Branding.inno_id
    product_name = $Branding.name
    publisher = $Branding.publisher
    version = $Version
    architecture = $Arch
    icon_sha256 = (Get-FileHash -LiteralPath $StagedIcon -Algorithm SHA256).Hash.ToLowerInvariant()
    welcome_sha256 = (Get-FileHash -LiteralPath $StagedWelcome -Algorithm SHA256).Hash.ToLowerInvariant()
    authenticode_verified = ($env:ROW_REQUIRE_RELEASE_SIGNING -eq "1")
    artifacts = @($Artifacts)
  }
  $ManifestPath = Join-Path $Pending "enterprise-installers.json"
  $DeploymentManifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath $ManifestPath
  [IO.Directory]::Move($Pending, $OutDir)
  Write-Host "created $(Join-Path $OutDir 'enterprise-installers.json')"
  return
}

New-Item -ItemType Directory -Force $PortableStage | Out-Null
Copy-Item -Path (Join-Path $Stage "*") -Destination $PortableStage -Recurse -Force
if ($BuildGuiLauncher) {
  Copy-Item (Join-Path $PortableStage "bin\row-gui.exe") (Join-Path $PortableStage "Remote Ops Workspace GUI.exe")
}

$NativeZip = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch-native.zip"
Compress-Archive -Path (Join-Path $PortableStage "*") -DestinationPath $NativeZip -Force

$SetupExe = Build-InnoSetupInstaller -Version $Version -Stage $Stage -OutDir $OutDir -Arch $Arch -IconPath $IconIco -Branding $Branding
$Msi = Build-WixMsi -Version $Version -Stage $Stage -OutDir $OutDir -Arch $Arch -IconPath $IconIco -Branding $Branding
Sign-NativeArtifact $Msi

$PortableInstallCommand = if ($BuildGuiLauncher) {
  "Extract and double-click Remote Ops Workspace GUI.exe for the desktop UI, or run bin\row.exe for CLI workflows."
} else {
  "Extract and run bin\row.exe. The Windows x86 portable build is CLI-first."
}
$PortableNotes = @("Standalone PyInstaller CLI executable plus docs.", "Built for Windows $Arch.")
$ReleaseSigningEnabled = $env:ROW_REQUIRE_RELEASE_SIGNING -eq "1"
$InstallerNotes = if ($ReleaseSigningEnabled) {
  @("Authenticode-signed and timestamped for the production release channel.", "Built for Windows $Arch.")
} else {
  @("Unsigned preview installer for testing only; not trusted production media.", "Built for Windows $Arch.")
}
$ReleaseChannel = if ($ReleaseSigningEnabled) { "production-signed" } else { "unsigned-preview" }
$SigningMetadata = @{
  release_channel = $ReleaseChannel
  production_trusted = $ReleaseSigningEnabled
  authenticode_verified = $ReleaseSigningEnabled
  timestamped = $ReleaseSigningEnabled
}
$PortableEntrypoints = @{
  cli = "bin\row.exe"
}
if ($BuildGuiLauncher) {
  $PortableNotes += "Includes no-console PyQt6 GUI launcher: bin\row-gui.exe."
  $PortableNotes += "Includes top-level double-click GUI alias: Remote Ops Workspace GUI.exe."
  $PortableEntrypoints["desktop_gui"] = "Remote Ops Workspace GUI.exe"
  $PortableEntrypoints["desktop_gui_bin"] = "bin\row-gui.exe"
  $InstallerNotes += "Installs bin\row-gui.exe and GUI shortcuts where the installer format supports shortcuts."
} else {
  $PortableNotes += "PyQt6 does not publish 32-bit Windows wheels, so this x86 bundle does not include row-gui.exe."
  $InstallerNotes += "PyQt6 does not publish 32-bit Windows wheels, so this x86 installer does not include row-gui.exe."
  $PortableNotes += "Encrypted vault support is unavailable and fail-closed because no reviewed cryptography 50 Windows x86 toolchain exists."
  $InstallerNotes += "Encrypted vault support is unavailable and fail-closed because no reviewed cryptography 50 Windows x86 toolchain exists."
  $PortableNotes += "Known-vulnerable cryptography fallback releases are intentionally excluded."
  $InstallerNotes += "Known-vulnerable cryptography fallback releases are intentionally excluded."
}

$Manifest = @(
  @{
    phase = "phase-2-windows-native"
    target = "windows-$Arch-native-zip"
    label = "Windows $Arch native portable bundle"
    architecture = $Arch
    file = (To-RepoPath $NativeZip)
    format = "zip"
    install_command = $PortableInstallCommand
    portable_entrypoints = $PortableEntrypoints
    signing = $SigningMetadata
    notes = $PortableNotes
  },
  @{
    phase = "phase-2-windows-native"
    target = "windows-$Arch-exe-installer"
    label = "Windows $Arch EXE installer"
    architecture = $Arch
    file = (To-RepoPath $SetupExe)
    format = "exe"
    install_command = "Run the installer interactively or with Inno Setup silent flags."
    signing = $SigningMetadata
    notes = $InstallerNotes
  },
  @{
    phase = "phase-2-windows-native"
    target = "windows-$Arch-msi-installer"
    label = "Windows $Arch MSI installer"
    architecture = $Arch
    file = (To-RepoPath $Msi)
    format = "msi"
    install_command = "msiexec /i $(Split-Path -Leaf $Msi)"
    signing = $SigningMetadata
    notes = $InstallerNotes
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

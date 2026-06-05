param(
  [string]$Dist = "native-dist\windows",
  [ValidateSet("x86", "x64", "arm64")]
  [string]$Arch = "x64",
  [string]$Version = "",
  [int]$CommandTimeoutSeconds = 180
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

function Invoke-SmokeCommand([string]$Label, [string]$FilePath, [string[]]$ArgumentList) {
  Write-Host "native installer smoke: $Label"
  $Process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -NoNewWindow -PassThru
  if (!$Process.WaitForExit($CommandTimeoutSeconds * 1000)) {
    & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
    throw "$Label timed out after $CommandTimeoutSeconds seconds"
  }
  if ($Process.ExitCode -ne 0) {
    throw "$Label failed with exit code $($Process.ExitCode)"
  }
}

function Test-RowVersion([string]$Path, [string]$ExpectedVersion) {
  if (!(Test-Path $Path)) {
    throw "expected installed row executable missing: $Path"
  }
  $Output = & $Path --version
  if ($LASTEXITCODE -ne 0) {
    throw "row --version failed for $Path"
  }
  if (($Output -join "`n") -notmatch [regex]::Escape($ExpectedVersion)) {
    throw "row --version output did not include $ExpectedVersion"
  }
}

function Test-RowGuiLauncher([string]$RowPath, [string]$Arch) {
  if ($Arch -eq "x86") {
    return
  }
  $GuiPath = Join-Path (Split-Path -Parent $RowPath) "row-gui.exe"
  if (!(Test-Path $GuiPath)) {
    throw "expected installed GUI launcher missing: $GuiPath"
  }
}

function Find-MsiRowExe {
  $Candidates = @()
  if ($env:ProgramFiles) {
    $Candidates += (Join-Path $env:ProgramFiles "Remote Ops Workspace\bin\row.exe")
  }
  $ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  if ($ProgramFilesX86) {
    $Candidates += (Join-Path $ProgramFilesX86 "Remote Ops Workspace\bin\row.exe")
  }
  foreach ($Candidate in $Candidates) {
    if ($Candidate -and (Test-Path $Candidate)) {
      return $Candidate
    }
  }
  throw "MSI install did not create row.exe in Program Files"
}

if (!$Version) {
  $Version = Get-ProjectVersion
}

$OutDir = Resolve-Path (Join-Path $Root $Dist)
$SetupExe = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch-setup.exe"
$Msi = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch.msi"
foreach ($Artifact in @($SetupExe, $Msi)) {
  if (!(Test-Path $Artifact)) {
    throw "native installer smoke artifact missing: $Artifact"
  }
}

$SmokeRoot = Join-Path $Root "build\native-smoke\windows-$Arch"
Remove-Item -Recurse -Force $SmokeRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $SmokeRoot | Out-Null

# install / verify / upgrade / uninstall smoke for the Inno Setup .exe installer.
$ExeInstallDir = Join-Path $SmokeRoot "exe-install"
$ExeInstallArgs = @(
  "/VERYSILENT",
  "/SUPPRESSMSGBOXES",
  "/NORESTART",
  "/NOICONS",
  "/DIR=$ExeInstallDir"
)
Invoke-SmokeCommand "EXE install" $SetupExe $ExeInstallArgs
$ExeRow = Join-Path $ExeInstallDir "bin\row.exe"
Test-RowVersion $ExeRow $Version
Test-RowGuiLauncher $ExeRow $Arch
Invoke-SmokeCommand "EXE upgrade" $SetupExe $ExeInstallArgs
Test-RowVersion $ExeRow $Version
Test-RowGuiLauncher $ExeRow $Arch
$Uninstaller = Get-ChildItem -Path $ExeInstallDir -Filter "unins*.exe" | Select-Object -First 1
if (!$Uninstaller) {
  throw "EXE uninstall helper was not created"
}
Invoke-SmokeCommand "EXE uninstall" $Uninstaller.FullName @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
if (Test-Path $ExeRow) {
  throw "EXE uninstall left row.exe behind"
}
$ExeGui = Join-Path $ExeInstallDir "bin\row-gui.exe"
if (Test-Path $ExeGui) {
  throw "EXE uninstall left row-gui.exe behind"
}

# install / verify / upgrade / uninstall smoke for the WiX .msi installer.
$MsiLog = Join-Path $SmokeRoot "msi-smoke.log"
Invoke-SmokeCommand "MSI install" "msiexec.exe" @("/i", $Msi, "/qn", "/norestart", "/l*v", $MsiLog)
$MsiRow = Find-MsiRowExe
Test-RowVersion $MsiRow $Version
Test-RowGuiLauncher $MsiRow $Arch
Invoke-SmokeCommand "MSI upgrade" "msiexec.exe" @("/i", $Msi, "/qn", "/norestart", "/l*v", $MsiLog)
$MsiRow = Find-MsiRowExe
Test-RowVersion $MsiRow $Version
Test-RowGuiLauncher $MsiRow $Arch
Invoke-SmokeCommand "MSI uninstall" "msiexec.exe" @("/x", $Msi, "/qn", "/norestart", "/l*v", $MsiLog)
if (Test-Path $MsiRow) {
  throw "MSI uninstall left row.exe behind"
}
$MsiGui = Join-Path (Split-Path -Parent $MsiRow) "row-gui.exe"
if (Test-Path $MsiGui) {
  throw "MSI uninstall left row-gui.exe behind"
}

Write-Host "native installer smoke passed for Windows $Arch"

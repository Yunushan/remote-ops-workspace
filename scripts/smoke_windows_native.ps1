param(
  [string]$Dist = "native-dist\windows",
  [ValidateSet("x86", "x64", "arm64")]
  [string]$Arch = "x64",
  [string]$Version = ""
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
  $Process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -NoNewWindow -Wait -PassThru
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

function Test-PortableGuiLauncher([string]$InstallDir, [string]$Arch) {
  if ($Arch -eq "x86") {
    return
  }
  $RootGuiPath = Join-Path $InstallDir "Remote Ops Workspace GUI.exe"
  if (!(Test-Path $RootGuiPath)) {
    throw "expected portable GUI alias missing: $RootGuiPath"
  }
  $BinGuiPath = Join-Path $InstallDir "bin\row-gui.exe"
  if (!(Test-Path $BinGuiPath)) {
    throw "expected portable bin GUI launcher missing: $BinGuiPath"
  }
}

function Test-RowVault([string]$Path, [string]$Label) {
  $OldRowHome = [Environment]::GetEnvironmentVariable("ROW_HOME", "Process")
  $OldVaultPassword = [Environment]::GetEnvironmentVariable("ROW_VAULT_PASSWORD", "Process")
  $VaultHome = Join-Path $SmokeRoot ("vault-" + [Guid]::NewGuid().ToString("N"))
  try {
    $env:ROW_HOME = $VaultHome
    $env:ROW_VAULT_PASSWORD = "release-native-vault-smoke-passphrase"

    $InitOutput = & $Path vault init 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "$Label vault init failed: $($InitOutput -join ' ')"
    }
    $StatusOutput = & $Path vault status --json 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "$Label vault status failed: $($StatusOutput -join ' ')"
    }
    try {
      $Status = ($StatusOutput -join "`n") | ConvertFrom-Json
    } catch {
      throw "$Label vault status did not return valid JSON: $($StatusOutput -join ' ')"
    }
    if (-not $Status.initialized) {
      throw "$Label vault did not report initialized state"
    }
    if (-not $Status.backend_available) {
      throw "$Label vault cryptography backend is unavailable"
    }
    if ($Status.kdf -ne "scrypt") {
      throw "$Label vault did not report the expected scrypt KDF"
    }
  } finally {
    if ($null -eq $OldRowHome) {
      Remove-Item Env:ROW_HOME -ErrorAction SilentlyContinue
    } else {
      $env:ROW_HOME = $OldRowHome
    }
    if ($null -eq $OldVaultPassword) {
      Remove-Item Env:ROW_VAULT_PASSWORD -ErrorAction SilentlyContinue
    } else {
      $env:ROW_VAULT_PASSWORD = $OldVaultPassword
    }
    Remove-Item -Recurse -Force $VaultHome -ErrorAction SilentlyContinue
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
$NativeZip = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch-native.zip"
$SetupExe = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch-setup.exe"
$Msi = Join-Path $OutDir "remote-ops-workspace-v$Version-windows-$Arch.msi"
foreach ($Artifact in @($NativeZip, $SetupExe, $Msi)) {
  if (!(Test-Path $Artifact)) {
    throw "native installer smoke artifact missing: $Artifact"
  }
}

$SmokeRoot = Join-Path $Root "build\native-smoke\windows-$Arch"
Remove-Item -Recurse -Force $SmokeRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $SmokeRoot | Out-Null

# extract / verify / remove smoke for the native portable zip.
$PortableInstallDir = Join-Path $SmokeRoot "portable"
Expand-Archive -Path $NativeZip -DestinationPath $PortableInstallDir -Force
$PortableRow = Join-Path $PortableInstallDir "bin\row.exe"
Test-RowVersion $PortableRow $Version
Test-PortableGuiLauncher $PortableInstallDir $Arch
Test-RowVault $PortableRow "portable ZIP"
Remove-Item -Recurse -Force $PortableInstallDir
if (Test-Path $PortableInstallDir) {
  throw "portable zip cleanup left extracted files behind"
}

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
Test-RowVault $ExeRow "EXE install"
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
Test-RowVault $MsiRow "MSI install"
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

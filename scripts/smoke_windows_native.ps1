param(
  [string]$Dist = "native-dist\windows",
  [ValidateSet("x86", "x64", "arm64")]
  [string]$Arch = "x64",
  [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Test-CandidateRegisteredProduct([string]$KeyName, [string]$DisplayName, [string]$InstallLocation) {
  if ($KeyName -ieq "{5C887096-F4E5-4AB8-8D6F-65052D08D284}_is1") { return $true }
  if ($DisplayName -imatch '^Remote Ops Workspace(?:$|[\s(\-])') { return $true }
  if ($InstallLocation -and [IO.Path]::GetFileName($InstallLocation.TrimEnd([char[]]@('\', '/'))) -ieq "Remote Ops Workspace") { return $true }
  return $false
}

function Get-CandidateRegisteredInstallations {
  # Read both registry views and both install scopes. Never use Win32_Product:
  # querying it can trigger Windows Installer consistency repair.
  $UninstallPath = "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
  # Packed form of the fixed WiX UpgradeCode 8F8A21B4-6E48-4B1A-9F5D-B9373E1807D0.
  $UpgradePaths = @(
    "SOFTWARE\Classes\Installer\UpgradeCodes\4B12A8F884E6A1B4F9D59B73E381700D",
    "SOFTWARE\Microsoft\Installer\UpgradeCodes\4B12A8F884E6A1B4F9D59B73E381700D"
  )
  foreach ($Hive in @([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryHive]::CurrentUser)) {
    foreach ($View in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
      $Base = $null
      $Uninstall = $null
      try {
        $Base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($Hive, $View)
        foreach ($UpgradePath in $UpgradePaths) {
          $Upgrade = $Base.OpenSubKey($UpgradePath, $false)
          if ($Upgrade) { $Upgrade.Dispose(); return @("msi-upgrade") }
        }
        $Uninstall = $Base.OpenSubKey($UninstallPath, $false)
        if (!$Uninstall) { continue }
        foreach ($Name in $Uninstall.GetSubKeyNames()) {
          $Entry = $null
          try {
            $Entry = $Uninstall.OpenSubKey($Name, $false)
            if (!$Entry) { throw "installed product registration disappeared during native candidate preflight" }
            if (Test-CandidateRegisteredProduct $Name ([string]$Entry.GetValue("DisplayName")) ([string]$Entry.GetValue("InstallLocation"))) { return @("registered-product") }
          } finally {
            if ($Entry) { $Entry.Dispose() }
          }
        }
      } finally {
        if ($Uninstall) { $Uninstall.Dispose() }
        if ($Base) { $Base.Dispose() }
      }
    }
  }
  return @()
}

function Assert-DisposableCandidateHost {
  if ($env:GITHUB_ACTIONS -ne "true" -or $env:RUNNER_ENVIRONMENT -ne "github-hosted" -or !$env:GITHUB_WORKSPACE) {
    throw "full native candidate smoke requires a disposable GitHub-hosted Actions runner"
  }
  if (![IO.Path]::GetFullPath($Root).Equals([IO.Path]::GetFullPath($env:GITHUB_WORKSPACE), [StringComparison]::OrdinalIgnoreCase)) {
    throw "native candidate smoke source root differs from the hosted checkout"
  }
  foreach ($Directory in @($env:ProgramFiles, [Environment]::GetEnvironmentVariable("ProgramFiles(x86)"), $env:LOCALAPPDATA)) {
    if ($Directory -and (Test-Path -LiteralPath (Join-Path $Directory "Remote Ops Workspace"))) {
      throw "native candidate smoke refuses a preexisting Remote Ops Workspace install directory"
    }
  }
  if (Test-Path -LiteralPath (Join-Path $Root "build/native-smoke/windows-$Arch/exe-install")) {
    throw "native candidate smoke refuses a preexisting candidate EXE install directory"
  }
  if (@(Get-CandidateRegisteredInstallations).Count) {
    throw "native candidate smoke refuses a preexisting Remote Ops Workspace registration"
  }
}

function Remove-CandidateSmokeTree([string]$Path) {
  Assert-CandidateSmokePath $Path
  if (Test-Path -LiteralPath $Path) {
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
  }
}

function Assert-CandidateSmokePath([string]$Path) {
  $Expected = [IO.Path]::GetFullPath((Join-Path $Root "build/native-smoke/windows-$Arch"))
  $Actual = [IO.Path]::GetFullPath($Path)
  $Prefix = $Expected.TrimEnd([char[]]@('\', '/')) + [IO.Path]::DirectorySeparatorChar
  if (!$Actual.Equals($Expected, [StringComparison]::OrdinalIgnoreCase) -and !$Actual.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "native candidate smoke deletion escapes the source-pinned smoke root"
  }
  # Reject every existing component before traversing it. Do not follow links
  # while examining children of a recursive deletion target.
  $Current = [IO.Path]::GetFullPath($Root)
  $RootPrefix = $Current.TrimEnd([char[]]@('\', '/')) + [IO.Path]::DirectorySeparatorChar
  if (!$Actual.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "native candidate smoke deletion escapes its checkout" }
  $Components = @($Current)
  foreach ($Part in $Actual.Substring($RootPrefix.Length).Split([char[]]@('\', '/'), [StringSplitOptions]::RemoveEmptyEntries)) {
    $Current = Join-Path $Current $Part
    $Components += $Current
  }
  foreach ($Component in $Components) {
    if (Test-Path -LiteralPath $Component) {
      if ((Get-Item -LiteralPath $Component -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "native candidate smoke deletion refuses reparse paths" }
    }
  }
  if (!(Test-Path -LiteralPath $Actual -PathType Container)) { return }
  $Pending = New-Object 'System.Collections.Generic.Stack[string]'
  $Pending.Push($Actual)
  $Seen = 0
  while ($Pending.Count) {
    foreach ($Item in (Get-ChildItem -LiteralPath $Pending.Pop() -Force)) {
      $Seen++
      if ($Seen -gt 10000) { throw "native candidate smoke cleanup tree exceeds inspection bound" }
      if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "native candidate smoke deletion refuses reparse paths" }
      if ($Item.PSIsContainer) { $Pending.Push($Item.FullName) }
    }
  }
}

function Save-CandidateByteBinding {
  $script:CandidateByteBinding.observations = @($script:CandidateByteBindingRows.ToArray())
  $Json = $script:CandidateByteBinding | ConvertTo-Json -Depth 8
  [IO.File]::WriteAllText($script:CandidateByteBindingPath, $Json + "`n", (New-Object Text.UTF8Encoding($false)))
}

function Initialize-CandidateByteBinding {
  $script:CandidateByteBindingPath = Join-Path $SmokeRoot "candidate-runtime-byte-binding.json"
  $script:CandidateByteBindingRows = New-Object 'System.Collections.Generic.List[object]'
  $script:CandidateExpectedExecutables = @{}
  $script:CandidateRequiredPaths = @("portable/bin/row.exe", "exe-install/bin/row.exe", "msi-install/bin/row.exe")
  $Names = @{ cli = "row.exe" }
  if ($Arch -ne "x86") {
    $Names.gui = "row-gui.exe"
    $script:CandidateRequiredPaths += @("portable/bin/row-gui.exe", "portable/Remote Ops Workspace GUI.exe", "exe-install/bin/row-gui.exe", "msi-install/bin/row-gui.exe")
  }
  $script:CandidateByteBinding = [ordered]@{
    schema_version = 1
    target = "windows-$Arch"
    scope = "Observed executable bytes before each smoke launch match actual PyInstaller outputs; excludes external runtime files, adversarial race resistance, signing trust and independent runtime/license approval"
    status = "in-progress"
    smoke_complete = $false
    expected_executables = @()
    required_paths = $script:CandidateRequiredPaths
    observations = @()
  }
  Save-CandidateByteBinding
  $Cleanup = [ordered]@{
    schema_version = 1
    target = "windows-$Arch"
    failure_strategy = "disposable GitHub-hosted runner removal"
    failure_uninstall_verified = $false
    scope = "Existing successful uninstall probes verify their own command results and file absence; failure, cancellation and timeout do not prove installer uninstall or rollback"
  } | ConvertTo-Json -Depth 4
  [IO.File]::WriteAllText((Join-Path $SmokeRoot "candidate-cleanup-scope.json"), $Cleanup + "`n", (New-Object Text.UTF8Encoding($false)))
  foreach ($Role in ($Names.Keys | Sort-Object)) {
    $Relative = "build/native/windows/pyinstaller-dist/" + $Names[$Role]
    $ExpectedPath = Join-Path $Root $Relative
    if (!(Test-Path -LiteralPath $ExpectedPath -PathType Leaf)) {
      $script:CandidateByteBinding.status = "failed"
      Save-CandidateByteBinding
      throw "candidate PyInstaller output missing: $Relative"
    }
    $ExpectedHash = (Get-FileHash -LiteralPath $ExpectedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $Item = [ordered]@{ role = $Role; path = $Relative; sha256 = $ExpectedHash; size = (Get-Item -LiteralPath $ExpectedPath).Length }
    $script:CandidateExpectedExecutables[$Role] = $Item
    $script:CandidateByteBinding.expected_executables += $Item
    Save-CandidateByteBinding
  }
}

function Get-CandidateNormalizedPath([string]$Path) {
  $Full = [IO.Path]::GetFullPath($Path)
  $SmokePrefix = [IO.Path]::GetFullPath($SmokeRoot).TrimEnd([char[]]@('\', '/')) + [IO.Path]::DirectorySeparatorChar
  if ($Full.StartsWith($SmokePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    $Relative = $Full.Substring($SmokePrefix.Length).Replace('\', '/')
    if ($script:CandidateRequiredPaths -ccontains $Relative) { return $Relative }
  }
  foreach ($Directory in @($env:ProgramFiles, [Environment]::GetEnvironmentVariable("ProgramFiles(x86)"))) {
    if (!$Directory) { continue }
    foreach ($Name in @("row.exe", "row-gui.exe")) {
      $Allowed = [IO.Path]::GetFullPath((Join-Path $Directory "Remote Ops Workspace/bin/$Name"))
      if ($Full.Equals($Allowed, [StringComparison]::OrdinalIgnoreCase)) { return "msi-install/bin/$Name" }
    }
  }
  throw "candidate smoke executable path is outside its known install locations"
}

function Assert-CandidateExecutableBytes([string]$Path, [string]$Role, [string]$Label) {
  $Normalized = Get-CandidateNormalizedPath $Path
  $Expected = $script:CandidateExpectedExecutables[$Role]
  $ActualHash = $null
  if (Test-Path -LiteralPath $Path -PathType Leaf) {
    $ActualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
  }
  $Matched = $null -ne $Expected -and $ActualHash -eq $Expected.sha256
  $script:CandidateByteBindingRows.Add([ordered]@{
    path = $Normalized; role = $Role; probe = $Label
    expected_sha256 = if ($Expected) { $Expected.sha256 } else { $null }
    observed_sha256 = $ActualHash; matched = $Matched
  })
  if (!$Matched) { $script:CandidateByteBinding.status = "failed" }
  Save-CandidateByteBinding
  if (!$Matched) { throw "candidate executable bytes do not match PyInstaller output: $Normalized" }
}

function Complete-CandidateByteBinding {
  $Seen = @($script:CandidateByteBindingRows | Where-Object { $_.matched } | ForEach-Object { $_.path } | Sort-Object -Unique)
  foreach ($Required in $script:CandidateRequiredPaths) {
    if ($Seen -cnotcontains $Required) {
      $script:CandidateByteBinding.status = "failed"
      Save-CandidateByteBinding
      throw "candidate smoke did not bind required executable: $Required"
    }
  }
  foreach ($Expected in $script:CandidateExpectedExecutables.Values) {
    if ((Get-FileHash -LiteralPath (Join-Path $Root $Expected.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected.sha256) {
      $script:CandidateByteBinding.status = "failed"
      Save-CandidateByteBinding
      throw "candidate PyInstaller output changed during smoke: $($Expected.path)"
    }
  }
  if (@($script:CandidateByteBindingRows | Where-Object { !$_.matched }).Count) { throw "candidate smoke contains an executable byte mismatch" }
  $script:CandidateByteBinding.smoke_complete = $true
  $script:CandidateByteBinding.status = "bound"
  Save-CandidateByteBinding
}

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
  Assert-CandidateExecutableBytes $Path "cli" "row --version"
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

function Test-RowRuntimeResources([string]$Path, [string]$Label) {
  Assert-CandidateExecutableBytes $Path "cli" "$Label platforms --json"
  if (!(Test-Path $Path)) {
    throw "expected installed row executable missing: $Path"
  }
  $Output = & $Path platforms --json
  if ($LASTEXITCODE -ne 0) {
    throw "$Label platforms --json failed for $Path"
  }
  try {
    $Catalog = ($Output -join "`n") | ConvertFrom-Json
  } catch {
    throw "$Label platforms --json did not return valid JSON: $($Output -join ' ')"
  }
  if (@($Catalog.release_architectures).Count -eq 0) {
    throw "$Label packaged platform catalog has no release_architectures"
  }
  if (@($Catalog.windows_legacy_targets).Count -eq 0) {
    throw "$Label packaged platform catalog has no windows_legacy_targets"
  }
  Write-Host "native installer smoke runtime resources: $Label platforms --json"
}

function Test-PackagedGui([string]$GuiPath, [string]$Label) {
  Assert-CandidateExecutableBytes $GuiPath "gui" $Label
  $OldRowHome = [Environment]::GetEnvironmentVariable("ROW_HOME", "Process")
  $OldQtPlatform = [Environment]::GetEnvironmentVariable("QT_QPA_PLATFORM", "Process")
  $GuiHome = Join-Path $SmokeRoot ("gui-" + [Guid]::NewGuid().ToString("N"))
  $Report = Join-Path $GuiHome "result.json"
  $Process = $null
  try {
    $env:ROW_HOME = $GuiHome
    $env:QT_QPA_PLATFORM = "windows"
    $Process = Start-Process -FilePath $GuiPath -ArgumentList @("--smoke-json", ('"' + $Report + '"')) -WindowStyle Hidden -PassThru
    if (!$Process.WaitForExit(25000)) {
      throw "$Label packaged GUI startup exceeded 25 seconds"
    }
    $Process.Refresh()
    if ($Process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $Report -PathType Leaf)) {
      throw "$Label packaged GUI did not produce a successful startup report"
    }
    $Result = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
    if ($Result.success -ne $true -or $Result.frozen -ne $true -or $Result.qt_platform -ne "windows" -or $Result.version -ne $Version) {
      throw "$Label GUI report did not prove the frozen native Windows release"
    }
    if ($Result.profile_persisted -ne $true -or $Result.profile_selected -ne $true -or $Result.window_visible -ne $true -or $Result.paint_colour_count -lt 3) {
      throw "$Label GUI profile workflow or paint evidence failed"
    }
    $Image = [IO.Path]::ChangeExtension($Report, ".png")
    if (!(Test-Path -LiteralPath $Image -PathType Leaf) -or (Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Result.screenshot_sha256) {
      throw "$Label GUI screenshot digest did not match the startup report"
    }
    Write-Host "native installer smoke packaged GUI: $Label startup, profile selection and paint passed"
  } finally {
    if ($Process -and !$Process.HasExited) {
      Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    [Environment]::SetEnvironmentVariable("ROW_HOME", $OldRowHome, "Process")
    [Environment]::SetEnvironmentVariable("QT_QPA_PLATFORM", $OldQtPlatform, "Process")
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
  Test-PackagedGui $GuiPath "installed GUI"
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
  Assert-CandidateExecutableBytes $BinGuiPath "gui" "portable bin GUI"
  Test-PackagedGui $RootGuiPath "portable GUI alias"
}

function Test-RowVault([string]$Path, [string]$Label, [bool]$ExpectedBackend) {
  $OldRowHome = [Environment]::GetEnvironmentVariable("ROW_HOME", "Process")
  $OldVaultPassword = [Environment]::GetEnvironmentVariable("ROW_VAULT_PASSWORD", "Process")
  $VaultHome = Join-Path $SmokeRoot ("vault-" + [Guid]::NewGuid().ToString("N"))
  try {
    $env:ROW_HOME = $VaultHome
    $env:ROW_VAULT_PASSWORD = "release-native-vault-smoke-passphrase"

    Assert-CandidateExecutableBytes $Path "cli" "CLI command"
    $InitialStatusOutput = & $Path vault status --json 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "$Label initial vault status failed: $($InitialStatusOutput -join ' ')"
    }
    try {
      $InitialStatus = ($InitialStatusOutput -join [Environment]::NewLine) | ConvertFrom-Json
    } catch {
      throw "$Label initial vault status did not return valid JSON: $($InitialStatusOutput -join ' ')"
    }
    if ([bool]$InitialStatus.backend_available -ne $ExpectedBackend) {
      throw "$Label vault backend availability did not match expected state $ExpectedBackend"
    }
    if (-not $ExpectedBackend) {
      $PreviousErrorActionPreference = $ErrorActionPreference
      try {
        # The x86 bundle must fail closed; capture its expected native stderr instead of
        # letting the script-wide Stop policy abort before the exit code is checked.
        $ErrorActionPreference = "Continue"
        Assert-CandidateExecutableBytes $Path "cli" "CLI command"
        $InitOutput = & $Path vault init 2>&1
        $InitExitCode = $LASTEXITCODE
      } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
      }
      if ($InitExitCode -eq 0) {
        throw "$Label vault init unexpectedly succeeded without a maintained backend"
      }
      if (($InitOutput -join " ") -notmatch "\.\[security\]") {
        throw "$Label vault init did not explain the maintained security extra: $($InitOutput -join ' ')"
      }
      Assert-CandidateExecutableBytes $Path "cli" "CLI command"
      $AfterStatusOutput = & $Path vault status --json 2>&1
      if ($LASTEXITCODE -ne 0) {
        throw "$Label post-failure vault status failed: $($AfterStatusOutput -join ' ')"
      }
      try {
        $AfterStatus = ($AfterStatusOutput -join [Environment]::NewLine) | ConvertFrom-Json
      } catch {
        throw "$Label post-failure vault status did not return valid JSON: $($AfterStatusOutput -join ' ')"
      }
      if ($AfterStatus.initialized -or $AfterStatus.backend_available) {
        throw "$Label vault did not remain uninitialized and fail closed"
      }
      Write-Host "native installer smoke: $Label vault backend unavailable and fail-closed"
      return
    }

    Assert-CandidateExecutableBytes $Path "cli" "CLI command"
    $InitOutput = & $Path vault init 2>&1
    if ($LASTEXITCODE -ne 0) {
      throw "$Label vault init failed: $($InitOutput -join ' ')"
    }
    Assert-CandidateExecutableBytes $Path "cli" "CLI command"
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
    Remove-CandidateSmokeTree $VaultHome
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

Assert-DisposableCandidateHost

if (!$Version) {
  $Version = Get-ProjectVersion
}
$ExpectedVaultBackend = $Arch -ne "x86"

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
Remove-CandidateSmokeTree $SmokeRoot
New-Item -ItemType Directory -Force $SmokeRoot | Out-Null
Initialize-CandidateByteBinding

# extract / verify / remove smoke for the native portable zip.
$PortableInstallDir = Join-Path $SmokeRoot "portable"
Expand-Archive -Path $NativeZip -DestinationPath $PortableInstallDir -Force
$PortableRow = Join-Path $PortableInstallDir "bin\row.exe"
Test-RowVersion $PortableRow $Version
Test-RowRuntimeResources $PortableRow "portable ZIP verify"
Test-PortableGuiLauncher $PortableInstallDir $Arch
Test-RowVault $PortableRow "portable ZIP" $ExpectedVaultBackend
Remove-CandidateSmokeTree $PortableInstallDir
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
Test-RowRuntimeResources $ExeRow "EXE verify"
Test-RowGuiLauncher $ExeRow $Arch
Test-RowVault $ExeRow "EXE install" $ExpectedVaultBackend
Invoke-SmokeCommand "EXE upgrade" $SetupExe $ExeInstallArgs
Test-RowVersion $ExeRow $Version
Test-RowRuntimeResources $ExeRow "EXE upgrade"
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
Test-RowRuntimeResources $MsiRow "MSI verify"
Test-RowGuiLauncher $MsiRow $Arch
Test-RowVault $MsiRow "MSI install" $ExpectedVaultBackend
Invoke-SmokeCommand "MSI upgrade" "msiexec.exe" @("/i", $Msi, "/qn", "/norestart", "/l*v", $MsiLog)
$MsiRow = Find-MsiRowExe
Test-RowVersion $MsiRow $Version
Test-RowRuntimeResources $MsiRow "MSI upgrade"
Test-RowGuiLauncher $MsiRow $Arch
Invoke-SmokeCommand "MSI uninstall" "msiexec.exe" @("/x", $Msi, "/qn", "/norestart", "/l*v", $MsiLog)
if (Test-Path $MsiRow) {
  throw "MSI uninstall left row.exe behind"
}
$MsiGui = Join-Path (Split-Path -Parent $MsiRow) "row-gui.exe"
if (Test-Path $MsiGui) {
  throw "MSI uninstall left row-gui.exe behind"
}

Complete-CandidateByteBinding
Write-Host "native installer smoke passed for Windows $Arch"

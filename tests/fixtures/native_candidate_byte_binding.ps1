param([string]$FixtureRoot, [string]$Case, [string]$SmokeSource)
$ErrorActionPreference = "Stop"
$Tokens = $null
$Errors = $null
$Ast = [Management.Automation.Language.Parser]::ParseFile($SmokeSource, [ref]$Tokens, [ref]$Errors)
if ($Errors.Count) { throw ($Errors | Out-String) }
foreach ($Function in $Ast.FindAll({ param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
  Invoke-Expression $Function.Extent.Text
}
$Root = $FixtureRoot
$Arch = "x64"
$Version = "1.0.27"
$SmokeRoot = Join-Path $FixtureRoot "build/native-smoke/windows-x64"
$Build = Join-Path $FixtureRoot "build/native/windows/pyinstaller-dist"
New-Item -ItemType Directory -Force $SmokeRoot,$Build | Out-Null
if ($Case.StartsWith("host-") -or $Case.StartsWith("deletion-")) {
  $Caught = $false
  if ($Case.StartsWith("host-")) {
    $env:GITHUB_ACTIONS = "true"
    $env:RUNNER_ENVIRONMENT = "github-hosted"
    $env:GITHUB_WORKSPACE = $Root
    $env:ProgramFiles = Join-Path $Root "fixture-program-files"
    [Environment]::SetEnvironmentVariable("ProgramFiles(x86)", (Join-Path $Root "fixture-program-files-x86"), "Process")
    $env:LOCALAPPDATA = Join-Path $Root "fixture-local-appdata"
    function Get-CandidateRegisteredInstallations { return @() }
    switch ($Case) {
      "host-local" { $env:GITHUB_ACTIONS = "false" }
      "host-self-hosted" { $env:RUNNER_ENVIRONMENT = "self-hosted" }
      "host-wrong-checkout" { $env:GITHUB_WORKSPACE = Join-Path $Root "other-checkout" }
      "host-existing-directory" {
        New-Item -ItemType Directory -Force (Join-Path $env:ProgramFiles "Remote Ops Workspace") | Out-Null
      }
      "host-existing-owned-install" {
        New-Item -ItemType Directory -Force (Join-Path $SmokeRoot "exe-install") | Out-Null
      }
      "host-existing-inno" { function Get-CandidateRegisteredInstallations { return @("registered-product") } }
      "host-existing-msi" { function Get-CandidateRegisteredInstallations { return @("msi-upgrade") } }
      "host-registry-error" { function Get-CandidateRegisteredInstallations { throw "fixture cannot read registry" } }
      "host-registration-matcher" {
        if (!(Test-CandidateRegisteredProduct "{5C887096-F4E5-4AB8-8D6F-65052D08D284}_is1" "" "")) { throw "fixed Inno registration was not recognized" }
        if (!(Test-CandidateRegisteredProduct "{other-guid}" "Remote Ops Workspace 1.0.27" "")) { throw "MSI display name was not recognized" }
        if (!(Test-CandidateRegisteredProduct "{other-guid}" "" (Join-Path $Root "Remote Ops Workspace"))) { throw "product installation directory was not recognized" }
        if (Test-CandidateRegisteredProduct "{other-guid}" "Another application" (Join-Path $Root "Another application")) { throw "unrelated registration was recognized as ROW" }
        if (Test-CandidateRegisteredProduct "{other-guid}" "Another application" ('C:\Unrelated' + [char]0 + 'Install')) { throw "malformed unrelated registration was recognized as ROW" }
        if (!(Test-CandidateRegisteredProduct "{other-guid}" "" '  "C:\Program Files\Remote Ops Workspace\"  ')) { throw "quoted ROW installation directory was not recognized" }
      }
    }
    try { Assert-DisposableCandidateHost } catch { $Caught = $true }
    if (($Case -in @("host-allowed", "host-registration-matcher")) -eq $Caught) { throw "host guard did not enforce its contract" }
  } else {
    $Outside = Join-Path $Root "outside-smoke"
    New-Item -ItemType Directory -Force $Outside | Out-Null
    $OutsideMarker = Join-Path $Outside "preserved.txt"
    [IO.File]::WriteAllText($OutsideMarker, "outside marker")
    $Check = $SmokeRoot
    if ($Case -eq "deletion-escape") { $Check = $Outside }
    if ($Case -eq "deletion-prefix-sibling") { $Check = $SmokeRoot + "-outside" }
    if ($Case -in @("deletion-link", "deletion-linked-ancestor")) {
      New-Item -ItemType Junction -Path (Join-Path $SmokeRoot "external-junction") -Target $Outside | Out-Null
      if ($Case -eq "deletion-linked-ancestor") { $Check = Join-Path $SmokeRoot "external-junction/preserved.txt" }
    }
    if ($Case -eq "deletion-contained") {
      New-Item -ItemType Directory -Force (Join-Path $SmokeRoot "nested/empty") | Out-Null
    }
    try { Remove-CandidateSmokeTree $Check } catch { $Caught = $true }
    if (($Case -eq "deletion-contained") -eq $Caught) { throw "deletion guard did not enforce its contract" }
    if ([IO.File]::ReadAllText($OutsideMarker) -ne "outside marker") { throw "deletion guard altered an outside marker" }
    if ($Case -eq "deletion-contained" -and (Test-Path -LiteralPath $Check)) { throw "verified contained cleanup did not remove its test tree" }
  }
  Write-Output "BYTE_BINDING_FIXTURE_PASSED"
  return
}

$Canary = Join-Path $FixtureRoot "canary.exe"
$Marker = Join-Path $FixtureRoot "unexpected-launch.txt"
# Copy a benign Windows-supplied executable. Do not depend on local policy
# allowing newly compiled unsigned programs or change application control.
$CanarySource = Join-Path $env:WINDIR "System32/curl.exe"
if (!(Test-Path -LiteralPath $CanarySource -PathType Leaf)) { throw "Windows curl fixture executable is unavailable" }
Copy-Item -LiteralPath $CanarySource -Destination $Canary
foreach ($Name in @("row.exe", "row-gui.exe")) { Copy-Item -LiteralPath $Canary -Destination (Join-Path $Build $Name) }
if ($Case -in @("wrong-cli", "wrong-gui", "wrong-resources")) {
  $Name = if ($Case -eq "wrong-gui") { "row-gui.exe" } else { "row.exe" }
  [IO.File]::WriteAllText((Join-Path $Build $Name), "different expected build bytes")
}
Initialize-CandidateByteBinding
$Portable = Join-Path $SmokeRoot "portable/bin"
New-Item -ItemType Directory -Force $Portable | Out-Null
$ActualCli = Join-Path $Portable "row.exe"
$ActualGui = Join-Path $Portable "row-gui.exe"
Copy-Item -LiteralPath $Canary -Destination $ActualCli
Copy-Item -LiteralPath $Canary -Destination $ActualGui
$script:CandidateNativeCommandAttempts = 0
$script:CandidateStartProcessAttempts = 0
# Native command breakpoints match executable names, not full paths in
# Windows PowerShell 5.1. These names exist only in this isolated fixture.
# Actions observe invocation and continue; they never replace execution.
$InvocationBreakpoints = @(
  Set-PSBreakpoint -Command ([IO.Path]::GetFileName($ActualCli)),([IO.Path]::GetFileName($ActualGui)) -Action { $script:CandidateNativeCommandAttempts++; continue }
  Set-PSBreakpoint -Command "Start-Process" -Action { $script:CandidateStartProcessAttempts++; continue }
)
try {
if ($Case -in @("wrong-cli", "wrong-gui", "wrong-resources")) {
  $env:ROW_HOME = "test-environment-must-remain-unchanged"
  $Caught = $false
  try {
    switch ($Case) {
      "wrong-cli" { Test-RowVersion $ActualCli $Version }
      "wrong-gui" { Test-PackagedGui $ActualGui "portable GUI" }
      "wrong-resources" { Test-RowRuntimeResources $ActualCli "portable ZIP verify" }
    }
  } catch {
    if ($_.Exception.Message -notlike "candidate executable bytes do not match PyInstaller output:*") { throw }
    $Caught = $true
  }
  if (!$Caught -or (Test-Path -LiteralPath $Marker)) { throw "wrong-byte executable was not refused before launch" }
  if ($env:ROW_HOME -ne "test-environment-must-remain-unchanged") { throw "mismatch changed the GUI environment before refusal" }
} elseif ($Case -eq "matching-cli-launch") {
  # Test-RowVersion requires a successful native exit and captured curl version
  # output, proving its real launch returned before this fixture marker.
  Test-RowVersion $ActualCli "curl"
  [IO.File]::WriteAllText($Marker, "verified trusted CLI version")
} else {
  foreach ($Relative in $script:CandidateRequiredPaths) {
    $Actual = Join-Path $SmokeRoot $Relative
    New-Item -ItemType Directory -Force (Split-Path -Parent $Actual) | Out-Null
    Copy-Item -LiteralPath $Canary -Destination $Actual -Force
    $Role = if ($Relative.EndsWith("row.exe")) { "cli" } else { "gui" }
    Assert-CandidateExecutableBytes $Actual $Role "fixture observed executable"
  }
  if ($Case -eq "changed-build") {
    [IO.File]::WriteAllText((Join-Path $Build "row.exe"), "build changed after observation")
    $Caught = $false
    try { Complete-CandidateByteBinding } catch {
      if ($_.Exception.Message -notlike "candidate PyInstaller output changed during smoke:*") { throw }
      $Caught = $true
    }
    if (!$Caught) { throw "changed source output was accepted" }
  } else {
    Complete-CandidateByteBinding
  }
}
} finally {
  $Invocations = [ordered]@{
    native_command_attempts = $script:CandidateNativeCommandAttempts
    start_process_attempts = $script:CandidateStartProcessAttempts
  } | ConvertTo-Json
  [IO.File]::WriteAllText((Join-Path $FixtureRoot "command-invocations.json"), $Invocations + "`n", (New-Object Text.UTF8Encoding($false)))
  Remove-PSBreakpoint -Breakpoint $InvocationBreakpoints
}
Write-Output "BYTE_BINDING_FIXTURE_PASSED"

param([switch]$Build)

$ErrorActionPreference = "Stop"
$Venv = Join-Path $env:RUNNER_TEMP "professional-venv"
python -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw "Could not create the Windows evidence environment" }
$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --require-hashes --only-binary=:all: -r requirements-locks/windows-x64-bootstrap.txt
if ($LASTEXITCODE -ne 0) { throw "Windows evidence bootstrap installation failed" }
& $Python -m pip install --require-hashes --no-build-isolation --only-binary=:all: --no-binary=pyftpdlib -r requirements-locks/windows-x64.txt
if ($LASTEXITCODE -ne 0) { throw "Windows evidence runtime installation failed" }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Windows evidence dependencies are inconsistent" }
Split-Path -Parent $Python | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append

$Tools = Join-Path $env:RUNNER_TEMP "professional-tools"
dotnet tool install --tool-path $Tools wix --version 5.0.2
if ($LASTEXITCODE -ne 0) { throw "Pinned WiX installation failed" }
$WixVersion = (& (Join-Path $Tools "wix.exe") --version).Trim()
if ($LASTEXITCODE -ne 0 -or $WixVersion -notmatch '^5\.0\.2(?:\+|$)') {
  throw "Expected the WiX 5.0.2 compiler"
}
$Tools | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
if (!$Build) { return }

$Inno = Join-Path ([Environment]::GetEnvironmentVariable("ProgramFiles(x86)")) "Inno Setup 6\ISCC.exe"
$Probe = Join-Path $env:RUNNER_TEMP "professional-inno-probe.iss"
@("[Setup]", "AppName=ROW compiler probe", "AppVersion=0",
  "DefaultDirName={tmp}\ROWCompilerProbe", "Output=no", "Uninstallable=no") |
  Set-Content -LiteralPath $Probe -Encoding utf8
function Test-InnoVersion {
  if (!(Test-Path -LiteralPath $Inno)) { return $false }
  $Lines = @(& $Inno /O- $Probe 2>&1)
  return ($LASTEXITCODE -eq 0 -and @($Lines | Select-String '^Compiler engine version: Inno Setup 6\.7\.1\r?$').Count -eq 1)
}
if (!(Test-InnoVersion)) {
  choco install innosetup --version=6.7.1 --allow-downgrade --force -y --no-progress
  if ($LASTEXITCODE -notin @(0, 3010)) { throw "Pinned Inno Setup installation failed" }
}
if (!(Test-InnoVersion)) { throw "Expected the Inno Setup 6.7.1 compiler" }
Split-Path -Parent $Inno | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append

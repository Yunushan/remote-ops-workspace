param(
  [Parameter(Mandatory)]
  [string]$ArtifactPath
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "find_windows_signtool.ps1")

foreach ($Name in @("ROW_WINDOWS_CERTIFICATE_PATH", "ROW_WINDOWS_CERTIFICATE_PASSWORD", "ROW_WINDOWS_TIMESTAMP_URL")) {
  if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))) {
    throw "Production signing requires environment variable $Name"
  }
}

$SignTool = Find-WindowsSignTool
& $SignTool sign /fd SHA256 /tr $env:ROW_WINDOWS_TIMESTAMP_URL /td SHA256 /f $env:ROW_WINDOWS_CERTIFICATE_PATH /p $env:ROW_WINDOWS_CERTIFICATE_PASSWORD $ArtifactPath
if ($LASTEXITCODE -ne 0) {
  throw "Authenticode signing failed for $ArtifactPath"
}
& $SignTool verify /pa /all /tw $ArtifactPath
if ($LASTEXITCODE -ne 0) {
  throw "Authenticode signature or timestamp verification failed for $ArtifactPath"
}

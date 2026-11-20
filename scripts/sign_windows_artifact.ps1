[CmdletBinding(DefaultParameterSetName = "Artifact")]
param(
  [Parameter(Mandatory, ParameterSetName = "Artifact")]
  [string]$ArtifactPath,
  [Parameter(Mandatory, ParameterSetName = "Rehearsal")]
  [switch]$Rehearse,
  [string]$CertificatePath = $env:ROW_WINDOWS_CERTIFICATE_PATH
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "find_windows_signtool.ps1")

function Invoke-SignTool([string]$Executable, [string[]]$Arguments) {
  $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
  $StartInfo.FileName = $Executable
  $StartInfo.UseShellExecute = $false
  $StartInfo.CreateNoWindow = $true
  $StartInfo.RedirectStandardOutput = $true
  $StartInfo.RedirectStandardError = $true
  $StartInfo.WorkingDirectory = $ExecutionContext.SessionState.Path.CurrentFileSystemLocation.ProviderPath
  $StartInfo.EnvironmentVariables.Remove("ROW_WINDOWS_CERTIFICATE_BASE64")
  # Windows PowerShell 5.1 does not preserve native arguments with embedded quotes.
  # Double backslashes before each quote or the closing delimiter for Windows argv.
  $EncodedArguments = foreach ($Argument in $Arguments) {
    $Escaped = $Argument -replace '(\\*)"', '${1}${1}\"' -replace '(\\+)\z', '${1}${1}'
    '"' + $Escaped + '"'
  }
  $StartInfo.Arguments = $EncodedArguments -join " "
  $Process = [System.Diagnostics.Process]::Start($StartInfo)
  try {
    $Output = $Process.StandardOutput.ReadToEndAsync()
    $Errors = $Process.StandardError.ReadToEndAsync()
    $Process.WaitForExit()
    foreach ($Diagnostic in @($Output.Result, $Errors.Result)) {
      if ($Diagnostic) {
        if ($env:ROW_WINDOWS_CERTIFICATE_PASSWORD) {
          $Diagnostic = $Diagnostic.Replace($env:ROW_WINDOWS_CERTIFICATE_PASSWORD, "[redacted]")
        }
        Write-Host $Diagnostic.TrimEnd()
      }
    }
    return $Process.ExitCode
  } finally {
    $Process.Dispose()
  }
}

$Timestamp = $null
if (![uri]::TryCreate($env:ROW_WINDOWS_TIMESTAMP_URL, [UriKind]::Absolute, [ref]$Timestamp) -or
    $Timestamp.Scheme -notin @("http", "https") -or !$Timestamp.Host -or $Timestamp.UserInfo) {
  throw "ROW_WINDOWS_TIMESTAMP_URL must be a credential-free HTTP or HTTPS timestamp URL."
}

$Thumbprint = $env:ROW_WINDOWS_CERTIFICATE_THUMBPRINT
$StoreLocation = $env:ROW_WINDOWS_CERTIFICATE_STORE_LOCATION
$UseEncodedPfx = $Rehearse -and ![string]::IsNullOrWhiteSpace($env:ROW_WINDOWS_CERTIFICATE_BASE64)
if (![string]::IsNullOrWhiteSpace($Thumbprint)) {
  if ($Thumbprint -cnotmatch '\A[0-9a-fA-F]{40}\z') {
    throw "ROW_WINDOWS_CERTIFICATE_THUMBPRINT must be a 40-digit hexadecimal certificate thumbprint."
  }
  if ($CertificatePath -or $env:ROW_WINDOWS_CERTIFICATE_PASSWORD -or $env:ROW_WINDOWS_CERTIFICATE_BASE64) {
    throw "Choose one Windows signing source: certificate-store thumbprint or PFX."
  }
  if ($StoreLocation -and $StoreLocation -notin @("CurrentUser", "LocalMachine")) {
    throw "ROW_WINDOWS_CERTIFICATE_STORE_LOCATION must be CurrentUser or LocalMachine."
  }
  $CertificateArgs = @("/s", "My", "/sha1", $Thumbprint)
  if ($StoreLocation -eq "LocalMachine") {
    $CertificateArgs += "/sm"
  }
} else {
  if ($StoreLocation) {
    throw "ROW_WINDOWS_CERTIFICATE_STORE_LOCATION requires ROW_WINDOWS_CERTIFICATE_THUMBPRINT."
  }
  if ($UseEncodedPfx -and $CertificatePath) {
    throw "Choose one PFX source: certificate path or ROW_WINDOWS_CERTIFICATE_BASE64."
  }
  if (([string]::IsNullOrWhiteSpace($CertificatePath) -and !$UseEncodedPfx) -or
      [string]::IsNullOrWhiteSpace($env:ROW_WINDOWS_CERTIFICATE_PASSWORD)) {
    throw "PFX signing requires a certificate path and ROW_WINDOWS_CERTIFICATE_PASSWORD."
  }
}

$SignTool = Find-WindowsSignTool
$RehearsalDirectory = $null
$RehearsalPfx = $null
try {
  if ($Rehearse) {
    $RehearsalId = [guid]::NewGuid().ToString("N")
    $RehearsalDirectory = (New-Item -ItemType Directory -Path (
      Join-Path ([IO.Path]::GetTempPath()) "row-signing-rehearsal-$RehearsalId"
    )).FullName
    $ArtifactPath = Join-Path $RehearsalDirectory "rehearsal.dll"
    Add-Type -TypeDefinition "public static class RowSigningRehearsal$RehearsalId {}" -OutputAssembly $ArtifactPath
    if ($UseEncodedPfx) {
      $RehearsalPfx = Join-Path $RehearsalDirectory "rehearsal.pfx"
      [IO.File]::WriteAllBytes($RehearsalPfx, [Convert]::FromBase64String($env:ROW_WINDOWS_CERTIFICATE_BASE64))
      $CertificatePath = $RehearsalPfx
    }
  }
  if ([string]::IsNullOrWhiteSpace($Thumbprint)) {
    $CertificateArgs = @("/f", $CertificatePath, "/p", $env:ROW_WINDOWS_CERTIFICATE_PASSWORD)
  }
  $SignArgs = @("sign", "/fd", "SHA256", "/tr", $Timestamp.AbsoluteUri, "/td", "SHA256") + $CertificateArgs + @($ArtifactPath)
  if ((Invoke-SignTool $SignTool $SignArgs) -ne 0) {
    throw "Authenticode signing failed for $ArtifactPath"
  }
  if ((Invoke-SignTool $SignTool @("verify", "/pa", "/all", "/tw", $ArtifactPath)) -ne 0) {
    throw "Authenticode signature or timestamp verification failed for $ArtifactPath"
  }
} finally {
  if ($RehearsalDirectory) {
    foreach ($File in @($RehearsalPfx, $ArtifactPath)) {
      if ($File -and (Test-Path -LiteralPath $File)) {
        Remove-Item -LiteralPath $File -Force
      }
    }
    [IO.Directory]::Delete($RehearsalDirectory)
  }
}
if ($Rehearse) {
  Write-Output "Windows Authenticode signing, timestamp and trust rehearsal passed."
}

param(
  [Parameter(Mandatory)]
  [string]$ArtifactPath,
  [string]$CertificatePath = $env:ROW_WINDOWS_CERTIFICATE_PATH
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "find_windows_signtool.ps1")

$Timestamp = $null
if (![uri]::TryCreate($env:ROW_WINDOWS_TIMESTAMP_URL, [UriKind]::Absolute, [ref]$Timestamp) -or
    $Timestamp.Scheme -notin @("http", "https") -or !$Timestamp.Host -or $Timestamp.UserInfo) {
  throw "ROW_WINDOWS_TIMESTAMP_URL must be a credential-free HTTP or HTTPS timestamp URL."
}

$Thumbprint = $env:ROW_WINDOWS_CERTIFICATE_THUMBPRINT
$StoreLocation = $env:ROW_WINDOWS_CERTIFICATE_STORE_LOCATION
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
  if ([string]::IsNullOrWhiteSpace($CertificatePath) -or
      [string]::IsNullOrWhiteSpace($env:ROW_WINDOWS_CERTIFICATE_PASSWORD)) {
    throw "PFX signing requires a certificate path and ROW_WINDOWS_CERTIFICATE_PASSWORD."
  }
  $CertificateArgs = @("/f", $CertificatePath, "/p", $env:ROW_WINDOWS_CERTIFICATE_PASSWORD)
}

$SignTool = Find-WindowsSignTool
& $SignTool sign /fd SHA256 /tr $Timestamp.AbsoluteUri /td SHA256 @CertificateArgs $ArtifactPath
if ($LASTEXITCODE -ne 0) {
  throw "Authenticode signing failed for $ArtifactPath"
}
& $SignTool verify /pa /all /tw $ArtifactPath
if ($LASTEXITCODE -ne 0) {
  throw "Authenticode signature or timestamp verification failed for $ArtifactPath"
}

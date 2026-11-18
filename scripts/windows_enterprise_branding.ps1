function Get-InstallerBrandingFile([string]$Root, [string]$RelativePath) {
  $Current = Get-Item -LiteralPath $Root -ErrorAction Stop
  foreach ($Part in $RelativePath.Split("/")) {
    if (!$Current.PSIsContainer -or ($Current.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
      throw "Enterprise bundle must contain a plain path for $RelativePath"
    }
    $Current = Get-Item -LiteralPath (Join-Path $Current.FullName $Part) -ErrorAction Stop
  }
  if ($Current.PSIsContainer -or ($Current.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "Enterprise bundle must contain a plain file for $RelativePath"
  }
  return $Current.FullName
}

function Get-InstallerDisplayText([string]$Value, [string]$Label) {
  $Value = $Value.Trim()
  if (!$Value -or $Value.Length -gt 64 -or $Value -match '[\p{C}\\/:*?"<>|;{}\[\]]') {
    throw "Enterprise $Label must be 1 to 64 characters of installer display text"
  }
  return $Value
}

function Read-WindowsEnterpriseBranding([string]$Bundle, [guid]$DeploymentId, [string]$Version) {
  if ($DeploymentId -in @(
      [guid]::Empty,
      [guid]"5C887096-F4E5-4AB8-8D6F-65052D08D284",
      [guid]"8F8A21B4-6E48-4B1A-9F5D-B9373E1807D0"
    )) {
    throw "Enterprise installers require a deployment GUID distinct from the public installers"
  }

  $MetadataPath = Get-InstallerBrandingFile $Bundle "branding/branding.json"
  $Metadata = Get-Content -Raw -Encoding UTF8 -LiteralPath $MetadataPath | ConvertFrom-Json
  if ($Metadata.schema_version -ne 1 -or $Metadata.logo -cne "branding/logo.ico" -or
      $Metadata.welcome_message_file -cne "welcome.txt") {
    throw "Use a row customizer bundle with an ICO logo to build enterprise Windows installers"
  }
  $BrandName = Get-InstallerDisplayText $Metadata.brand_name "brand name"
  $Publisher = if ($Metadata.organization) {
    Get-InstallerDisplayText $Metadata.organization "organization"
  } else { $BrandName }
  $Slug = $BrandName.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
  $Slug = $Slug.Trim('-')
  if (!$Slug) { $Slug = "remote-ops-workspace" }
  $IconPath = Get-InstallerBrandingFile $Bundle "branding/logo.ico"
  $WelcomePath = Get-InstallerBrandingFile $Bundle "welcome.txt"
  $Id = $DeploymentId.ToString("D").ToUpperInvariant()
  return @{
    enterprise = $true
    name = "$BrandName Remote Ops Workspace"
    publisher = $Publisher
    directory = "Remote Ops Workspace $Id"
    inno_id = $Id
    msi_id = $Id
    artifact_base = "$Slug-$Version"
    icon = $IconPath
    welcome = $WelcomePath
  }
}

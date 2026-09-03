$ErrorActionPreference = "Stop"
$BundleRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Target = if ($env:ROW_HOME) { $env:ROW_HOME } else { Join-Path $env:APPDATA "RemoteOpsWorkspace" }
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Copy-Item -Force (Join-Path $BundleRoot "config/settings.json") (Join-Path $Target "settings.json")
Copy-Item -Force (Join-Path $BundleRoot "config/profiles.json") (Join-Path $Target "profiles.json")
Copy-Item -Force (Join-Path $BundleRoot "config/policy.json") (Join-Path $Target "policy.json")
Copy-Item -Force (Join-Path $BundleRoot "welcome.txt") (Join-Path $Target "welcome.txt")
Write-Host "Applied Remote Ops Workspace enterprise bundle to $Target"

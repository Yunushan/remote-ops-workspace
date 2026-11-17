function Find-WindowsSignTool {
  $Command = Get-Command signtool.exe -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($Command) {
    return $Command.Source
  }

  $SdkRoot = (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots' -Name KitsRoot10 -ErrorAction SilentlyContinue).KitsRoot10
  if (!$SdkRoot -and ${env:ProgramFiles(x86)}) {
    $SdkRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10"
  }
  if (!$SdkRoot) {
    throw "Production signing requires signtool.exe from the Windows SDK."
  }
  $SdkBin = Join-Path $SdkRoot "bin"
  $Versions = Get-ChildItem -LiteralPath $SdkBin -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^10\.0\.\d+\.\d+$' } |
    Sort-Object { [version]$_.Name } -Descending

  $HostArchitecture = if ($env:PROCESSOR_ARCHITEW6432) {
    $env:PROCESSOR_ARCHITEW6432
  } else {
    $env:PROCESSOR_ARCHITECTURE
  }
  $Architectures = switch ($HostArchitecture) {
    "ARM64" { "arm64"; "x64"; "x86" }
    "AMD64" { "x64"; "x86" }
    "x86" { "x86" }
  }
  foreach ($Architecture in $Architectures) {
    foreach ($Version in $Versions) {
      $Candidate = Join-Path $Version.FullName "$Architecture\signtool.exe"
      if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
        return $Candidate
      }
    }
  }
  throw "Production signing requires signtool.exe from the Windows SDK."
}

param(
  [string]$Python = "python",
  [string]$Extras = "desktop,security"
)

$ErrorActionPreference = "Stop"

Write-Host "Remote Ops Workspace installer"
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
  throw "Python command not found: $Python. Install Python 3.10+ first."
}

& $Python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[${Extras}]"
& .\.venv\Scripts\row.exe init --quiet
& .\.venv\Scripts\row.exe doctor
& .\.venv\Scripts\row.exe welcome

Write-Host ""
Write-Host "Activate this environment later with: .\.venv\Scripts\Activate.ps1"

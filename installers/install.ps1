param(
  [string]$Python = "python",
  [string]$Extras = "desktop,security"
)

$ErrorActionPreference = "Stop"

Write-Host "Remote Ops Workspace installer"
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
  throw "Python command not found: $Python. Install Python 3.10 through 3.15 first."
}

& $Python -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info < (3, 16) else 1)"
if ($LASTEXITCODE -ne 0) {
  throw "Python 3.10 through 3.15 is required."
}

& $Python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[${Extras}]"
& .\.venv\Scripts\row.exe init --quiet --no-examples
& .\.venv\Scripts\row.exe doctor
& .\.venv\Scripts\row.exe welcome

Write-Host ""
Write-Host "Activate this environment later with: .\.venv\Scripts\Activate.ps1"

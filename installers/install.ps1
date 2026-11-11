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
if ($LASTEXITCODE -ne 0) {
  throw "Failed to create the Python virtual environment."
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
  throw "Failed to upgrade pip in the virtual environment."
}
& .\.venv\Scripts\python.exe -m pip install -e ".[${Extras}]"
if ($LASTEXITCODE -ne 0) {
  throw "Failed to install Remote Ops Workspace."
}
& .\.venv\Scripts\row.exe init --quiet --no-examples
if ($LASTEXITCODE -ne 0) {
  throw "Failed to initialize Remote Ops Workspace."
}
& .\.venv\Scripts\row.exe doctor
if ($LASTEXITCODE -ne 0) {
  throw "Remote Ops Workspace doctor reported a failure."
}
& .\.venv\Scripts\row.exe welcome
if ($LASTEXITCODE -ne 0) {
  throw "Remote Ops Workspace welcome failed."
}

Write-Host ""
Write-Host "Activate this environment later with: .\.venv\Scripts\Activate.ps1"

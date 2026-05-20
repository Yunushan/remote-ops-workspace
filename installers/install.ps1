param(
  [string]$Python = "python",
  [string]$Extras = "desktop,security"
)

$ErrorActionPreference = "Stop"
& $Python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[${Extras}]"
& .\.venv\Scripts\row.exe init
& .\.venv\Scripts\row.exe doctor

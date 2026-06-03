@echo off
setlocal
if not defined PYTHON_BIN set PYTHON_BIN=python
if not defined ROW_EXTRAS set ROW_EXTRAS=desktop,security
echo Remote Ops Workspace installer
where %PYTHON_BIN% >nul 2>nul || (
  echo Python command not found: %PYTHON_BIN%. Install Python 3.10+ first.
  exit /b 1
)
%PYTHON_BIN% -m venv .venv || exit /b 1
.venv\Scripts\python.exe -m pip install --upgrade pip || exit /b 1
.venv\Scripts\python.exe -m pip install -e ".[%ROW_EXTRAS%]" || exit /b 1
.venv\Scripts\row.exe init --quiet || exit /b 1
.venv\Scripts\row.exe doctor || exit /b 1
.venv\Scripts\row.exe welcome || exit /b 1
echo.
echo Activate this environment later with: .venv\Scripts\activate.bat
endlocal

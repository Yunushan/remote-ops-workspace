@echo off
setlocal
if not defined PYTHON_BIN set PYTHON_BIN=python
if not defined ROW_EXTRAS set ROW_EXTRAS=desktop,security
%PYTHON_BIN% -m venv .venv || exit /b 1
.venv\Scripts\python.exe -m pip install --upgrade pip || exit /b 1
.venv\Scripts\python.exe -m pip install -e ".[%ROW_EXTRAS%]" || exit /b 1
.venv\Scripts\row.exe init || exit /b 1
.venv\Scripts\row.exe doctor || exit /b 1
endlocal

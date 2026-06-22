@echo off
setlocal EnableExtensions

set "TARGET="
set "RELEASE_TAG="
set "SMOKE_ID="
set "EVIDENCE_FILE="
set "PROOF_FILE="
set "HOST_LABEL="
set "EVIDENCE_RUN_ID="

:parse
if "%~1"=="" goto parsed
if "%~1"=="--target" (
  set "TARGET=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--release-tag" (
  set "RELEASE_TAG=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--smoke-id" (
  set "SMOKE_ID=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--evidence-file" (
  set "EVIDENCE_FILE=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--proof-file" (
  set "PROOF_FILE=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--host-label" (
  set "HOST_LABEL=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--evidence-run-id" (
  set "EVIDENCE_RUN_ID=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--help" goto usage
echo unknown argument: %~1 1>&2
exit /b 2

:parsed
if "%TARGET%"=="" goto usage
if "%RELEASE_TAG%"=="" goto usage
if "%SMOKE_ID%"=="" goto usage
if "%EVIDENCE_FILE%"=="" goto usage
if "%PROOF_FILE%"=="" (
  echo --proof-file is required so XP evidence cannot be generated from an empty placeholder. 1>&2
  exit /b 2
)
if "%HOST_LABEL%"=="" (
  echo --host-label is required so XP smoke evidence is bound to a sanitized host identity. 1>&2
  exit /b 2
)
if "%EVIDENCE_RUN_ID%"=="" (
  echo --evidence-run-id is required so XP smoke evidence is bound to a concrete evidence run. 1>&2
  exit /b 2
)
if not exist "%PROOF_FILE%" (
  echo proof file is missing: %PROOF_FILE% 1>&2
  exit /b 1
)

for %%F in ("%EVIDENCE_FILE%") do if not exist "%%~dpF" mkdir "%%~dpF"
(
  echo xp smoke target: %TARGET%
  echo xp smoke release: %RELEASE_TAG%
  echo xp smoke id: %SMOKE_ID%
  echo xp smoke host label: %HOST_LABEL%
  echo xp smoke evidence run id: %EVIDENCE_RUN_ID%
  type "%PROOF_FILE%"
) > "%EVIDENCE_FILE%"

echo XP smoke evidence written: %EVIDENCE_FILE%
exit /b 0

:usage
echo Usage: scripts\xp_smoke_runner.cmd --target ^<target^> --release-tag ^<vX.Y.Z^> --smoke-id ^<id^> --evidence-file ^<path^> --proof-file ^<path^> --host-label ^<sanitized-host^> --evidence-run-id ^<run-id^>
exit /b 2

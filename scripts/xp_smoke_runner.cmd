@echo off
setlocal EnableExtensions

set "TARGET="
set "RELEASE_TAG="
set "SMOKE_ID="
set "EVIDENCE_FILE="
set "PROOF_FILE="
set "HOST_LABEL="
set "EVIDENCE_RUN_ID="
set "OBSERVED_AT_UTC="
set "SOURCE_WORKFLOW_RUN_URL="
set "SOURCE_HEAD_SHA="
set "SOURCE_RUN_ATTEMPT="
set "OS_NAME="
set "OS_ARCHITECTURE="
set "OS_SERVICE_PACK="
set "OS_EDITION="

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
if "%~1"=="--observed-at-utc" (
  set "OBSERVED_AT_UTC=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--source-workflow-run-url" (
  set "SOURCE_WORKFLOW_RUN_URL=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--source-head-sha" (
  set "SOURCE_HEAD_SHA=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--source-run-attempt" (
  set "SOURCE_RUN_ATTEMPT=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--os-name" (
  set "OS_NAME=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--os-architecture" (
  set "OS_ARCHITECTURE=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--os-service-pack" (
  set "OS_SERVICE_PACK=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--os-edition" (
  set "OS_EDITION=%~2"
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
if "%OBSERVED_AT_UTC%"=="" (
  echo --observed-at-utc is required so XP smoke evidence is bound to the observed host identity timestamp. 1>&2
  exit /b 2
)
if "%SOURCE_WORKFLOW_RUN_URL%"=="" (
  echo --source-workflow-run-url is required so XP smoke evidence is bound to the release source workflow run. 1>&2
  exit /b 2
)
if "%SOURCE_HEAD_SHA%"=="" (
  echo --source-head-sha is required so XP smoke evidence is bound to the release source commit. 1>&2
  exit /b 2
)
if "%SOURCE_RUN_ATTEMPT%"=="" (
  echo --source-run-attempt is required so XP smoke evidence is bound to the release source run attempt. 1>&2
  exit /b 2
)
if "%OS_NAME%"=="" (
  echo --os-name is required so XP smoke evidence is bound to the native OS identity. 1>&2
  exit /b 2
)
if "%OS_ARCHITECTURE%"=="" (
  echo --os-architecture is required so XP smoke evidence is bound to the native OS architecture. 1>&2
  exit /b 2
)
if "%OS_SERVICE_PACK%"=="" (
  echo --os-service-pack is required so XP smoke evidence is bound to the native OS service pack. 1>&2
  exit /b 2
)
if not exist "%PROOF_FILE%" (
  echo proof file is missing: %PROOF_FILE% 1>&2
  exit /b 1
)

set "XP_SMOKE_VER_OUTPUT="
for /f "delims=" %%V in ('ver') do if not defined XP_SMOKE_VER_OUTPUT set "XP_SMOKE_VER_OUTPUT=%%V"
if "%XP_SMOKE_VER_OUTPUT%"=="" set "XP_SMOKE_VER_OUTPUT=unavailable"
set "XP_SMOKE_PROCESSOR_ARCHITECTURE=%PROCESSOR_ARCHITECTURE%"
if "%XP_SMOKE_PROCESSOR_ARCHITECTURE%"=="" set "XP_SMOKE_PROCESSOR_ARCHITECTURE=unavailable"
set "XP_SMOKE_PROCESSOR_ARCHITEW6432=%PROCESSOR_ARCHITEW6432%"
set "XP_SMOKE_WMIC_OS_CAPTION=unavailable"
set "XP_SMOKE_WMIC_OS_CSDVERSION=unavailable"
for /f "tokens=1,* delims==" %%A in ('wmic os get Caption^,CSDVersion /value 2^>nul') do (
  if /I "%%A"=="Caption" set "XP_SMOKE_WMIC_OS_CAPTION=%%B"
  if /I "%%A"=="CSDVersion" set "XP_SMOKE_WMIC_OS_CSDVERSION=%%B"
)
if "%XP_SMOKE_WMIC_OS_CAPTION%"=="" set "XP_SMOKE_WMIC_OS_CAPTION=unavailable"
if "%XP_SMOKE_WMIC_OS_CSDVERSION%"=="" set "XP_SMOKE_WMIC_OS_CSDVERSION=unavailable"

for %%F in ("%EVIDENCE_FILE%") do if not exist "%%~dpF" mkdir "%%~dpF"
(
  echo xp smoke target: %TARGET%
  echo xp smoke release: %RELEASE_TAG%
  echo xp smoke id: %SMOKE_ID%
  echo xp smoke os name: %OS_NAME%
  echo xp smoke os architecture: %OS_ARCHITECTURE%
  echo xp smoke os service pack: %OS_SERVICE_PACK%
  if not "%OS_EDITION%"=="" echo xp smoke os edition: %OS_EDITION%
  echo xp smoke host probe command: ver
  echo xp smoke host probe output: %XP_SMOKE_VER_OUTPUT%
  echo xp smoke processor architecture env: %XP_SMOKE_PROCESSOR_ARCHITECTURE%
  echo xp smoke processor architecture w6432 env: %XP_SMOKE_PROCESSOR_ARCHITEW6432%
  echo xp smoke wmic os caption: %XP_SMOKE_WMIC_OS_CAPTION%
  echo xp smoke wmic os csdversion: %XP_SMOKE_WMIC_OS_CSDVERSION%
  echo xp smoke host label: %HOST_LABEL%
  echo xp smoke evidence run id: %EVIDENCE_RUN_ID%
  echo xp smoke observed at utc: %OBSERVED_AT_UTC%
  echo xp smoke source workflow run: %SOURCE_WORKFLOW_RUN_URL%
  echo xp smoke source head sha: %SOURCE_HEAD_SHA%
  echo xp smoke source run attempt: %SOURCE_RUN_ATTEMPT%
  type "%PROOF_FILE%"
) > "%EVIDENCE_FILE%"

echo XP smoke evidence written: %EVIDENCE_FILE%
exit /b 0

:usage
echo Usage: scripts\xp_smoke_runner.cmd --target ^<target^> --release-tag ^<vX.Y.Z^> --smoke-id ^<id^> --evidence-file ^<path^> --proof-file ^<path^> --host-label ^<sanitized-host^> --evidence-run-id ^<run-id^> --observed-at-utc ^<YYYY-MM-DDTHH:MM:SSZ^> --source-workflow-run-url ^<github-actions-run-url^> --source-head-sha ^<github-actions-head-sha^> --source-run-attempt ^<github-actions-run-attempt^> --os-name "Windows XP" --os-architecture ^<x86-or-x64^> --os-service-pack ^<SP2-or-SP3^> [--os-edition ^<edition^>]
exit /b 2

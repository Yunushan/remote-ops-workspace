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
set "SECURITY_UPDATE_CHANNEL="
set "CVE_REVIEW_REFERENCE="

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
if "%~1"=="--security-update-channel" (
  set "SECURITY_UPDATE_CHANNEL=%~2"
  shift
  shift
  goto parse
)
if "%~1"=="--cve-review-reference" (
  set "CVE_REVIEW_REFERENCE=%~2"
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
set "EXPECTED_XP_ID_PREFIX="
if /I "%TARGET%"=="windows-xp-native-x86" set "EXPECTED_XP_ID_PREFIX=xp-x86-"
if /I "%TARGET%"=="windows-xp-native-x64" set "EXPECTED_XP_ID_PREFIX=xp-x64-"
if "%EXPECTED_XP_ID_PREFIX%"=="" (
  echo --target must be windows-xp-native-x86 or windows-xp-native-x64 for XP native smoke evidence. 1>&2
  exit /b 2
)
if "%PROOF_FILE%"=="" (
  echo --proof-file is required so XP evidence cannot be generated from an empty placeholder. 1>&2
  exit /b 2
)
if "%HOST_LABEL%"=="" (
  echo --host-label is required so XP smoke evidence is bound to a sanitized host identity. 1>&2
  exit /b 2
)
if /I not "%HOST_LABEL:~0,7%"=="%EXPECTED_XP_ID_PREFIX%" (
  echo --host-label must use target-scoped prefix %EXPECTED_XP_ID_PREFIX%. 1>&2
  exit /b 2
)
if "%EVIDENCE_RUN_ID%"=="" (
  echo --evidence-run-id is required so XP smoke evidence is bound to a concrete evidence run. 1>&2
  exit /b 2
)
if /I not "%EVIDENCE_RUN_ID:~0,7%"=="%EXPECTED_XP_ID_PREFIX%" (
  echo --evidence-run-id must use target-scoped prefix %EXPECTED_XP_ID_PREFIX%. 1>&2
  exit /b 2
)
if "%OBSERVED_AT_UTC%"=="" (
  echo --observed-at-utc is required so XP smoke evidence is bound to the observed host identity timestamp. 1>&2
  exit /b 2
)
echo %OBSERVED_AT_UTC%| findstr /R "^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z$" >nul
if errorlevel 1 (
  echo --observed-at-utc must use YYYY-MM-DDTHH:MM:SSZ. 1>&2
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
if "%SOURCE_HEAD_SHA:~39,1%"=="" (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
if not "%SOURCE_HEAD_SHA:~40,1%"=="" (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
echo %SOURCE_HEAD_SHA%| find "A" >nul
if not errorlevel 1 (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
echo %SOURCE_HEAD_SHA%| find "B" >nul
if not errorlevel 1 (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
echo %SOURCE_HEAD_SHA%| find "C" >nul
if not errorlevel 1 (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
echo %SOURCE_HEAD_SHA%| find "D" >nul
if not errorlevel 1 (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
echo %SOURCE_HEAD_SHA%| find "E" >nul
if not errorlevel 1 (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
echo %SOURCE_HEAD_SHA%| find "F" >nul
if not errorlevel 1 (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
echo %SOURCE_HEAD_SHA%| findstr /R "^[0-9a-f]*$" >nul
if errorlevel 1 (
  echo --source-head-sha must be a lowercase 40-character Git commit SHA. 1>&2
  exit /b 2
)
if "%SOURCE_RUN_ATTEMPT%"=="" (
  echo --source-run-attempt is required so XP smoke evidence is bound to the release source run attempt. 1>&2
  exit /b 2
)
echo %SOURCE_RUN_ATTEMPT%| findstr /R "^[1-9][0-9]*$" >nul
if errorlevel 1 (
  echo --source-run-attempt must be a positive integer. 1>&2
  exit /b 2
)
if /I not "%SOURCE_WORKFLOW_RUN_URL:~0,19%"=="https://github.com/" (
  echo --source-workflow-run-url must be a GitHub Actions run URL. 1>&2
  exit /b 2
)
if "%SOURCE_WORKFLOW_RUN_URL:~-1%"=="/" (
  echo --source-workflow-run-url must be canonical without trailing slash. 1>&2
  exit /b 2
)
if not "%SOURCE_WORKFLOW_RUN_URL%"=="%SOURCE_WORKFLOW_RUN_URL: =%" (
  echo --source-workflow-run-url must be canonical without whitespace. 1>&2
  exit /b 2
)
if "%SOURCE_WORKFLOW_RUN_URL:/actions/runs/=%"=="%SOURCE_WORKFLOW_RUN_URL%" (
  echo --source-workflow-run-url must be a GitHub Actions run URL. 1>&2
  exit /b 2
)
set "REQUESTED_SOURCE_RUN_ID=%SOURCE_WORKFLOW_RUN_URL%"
for %%R in ("%REQUESTED_SOURCE_RUN_ID%") do set "REQUESTED_SOURCE_RUN_ID=%%~nxR"
echo %REQUESTED_SOURCE_RUN_ID%| findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 (
  echo --source-workflow-run-url must end with a numeric GitHub Actions run id. 1>&2
  exit /b 2
)
set "REQUESTED_SOURCE_REPOSITORY=%SOURCE_WORKFLOW_RUN_URL:https://github.com/=%"
for /f "tokens=1,2 delims=/" %%A in ("%REQUESTED_SOURCE_REPOSITORY%") do set "REQUESTED_SOURCE_REPOSITORY=%%A/%%B"
if not "%GITHUB_SHA%"=="" if /I not "%GITHUB_SHA%"=="%SOURCE_HEAD_SHA%" (
  echo target %TARGET% GITHUB_SHA %GITHUB_SHA% must match --source-head-sha %SOURCE_HEAD_SHA% 1>&2
  exit /b 2
)
if not "%GITHUB_RUN_ATTEMPT%"=="" if not "%GITHUB_RUN_ATTEMPT%"=="%SOURCE_RUN_ATTEMPT%" (
  echo target %TARGET% GITHUB_RUN_ATTEMPT %GITHUB_RUN_ATTEMPT% must match --source-run-attempt %SOURCE_RUN_ATTEMPT% 1>&2
  exit /b 2
)
if not "%GITHUB_RUN_ID%"=="" if not "%GITHUB_RUN_ID%"=="%REQUESTED_SOURCE_RUN_ID%" (
  echo target %TARGET% GITHUB_RUN_ID %GITHUB_RUN_ID% must match --source-workflow-run-url %SOURCE_WORKFLOW_RUN_URL% 1>&2
  exit /b 2
)
if not "%GITHUB_REPOSITORY%"=="" if /I not "%GITHUB_REPOSITORY%"=="%REQUESTED_SOURCE_REPOSITORY%" (
  echo target %TARGET% GITHUB_REPOSITORY %GITHUB_REPOSITORY% must match --source-workflow-run-url %SOURCE_WORKFLOW_RUN_URL% 1>&2
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

set "SECURITY_PROVENANCE_REQUIRED="
if /I "%SMOKE_ID%"=="legacy_crypto_profile_scoped" set "SECURITY_PROVENANCE_REQUIRED=1"
if /I "%SMOKE_ID%"=="modern_defaults_unchanged" set "SECURITY_PROVENANCE_REQUIRED=1"
if defined SECURITY_PROVENANCE_REQUIRED (
  if "%SECURITY_UPDATE_CHANNEL%"=="" goto missing_security_update_channel
  if "%CVE_REVIEW_REFERENCE%"=="" goto missing_cve_review_reference
  findstr /I /L /C:"security update channel: %SECURITY_UPDATE_CHANNEL%" "%PROOF_FILE%" >nul
  if errorlevel 1 goto missing_security_update_channel_proof
  findstr /I /L /C:"CVE review reference: %CVE_REVIEW_REFERENCE%" "%PROOF_FILE%" >nul
  if errorlevel 1 goto missing_cve_review_reference_proof
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

:missing_security_update_channel
echo --security-update-channel is required for XP security smoke evidence. 1>&2
exit /b 2

:missing_cve_review_reference
echo --cve-review-reference is required for XP security smoke evidence. 1>&2
exit /b 2

:missing_security_update_channel_proof
echo proof file must include security update channel: %SECURITY_UPDATE_CHANNEL% 1>&2
exit /b 2

:missing_cve_review_reference_proof
echo proof file must include CVE review reference: %CVE_REVIEW_REFERENCE% 1>&2
exit /b 2

:usage
echo Usage: scripts\xp_smoke_runner.cmd --target ^<target^> --release-tag ^<vX.Y.Z^> --smoke-id ^<id^> --evidence-file ^<path^> --proof-file ^<path^> --host-label ^<sanitized-host^> --evidence-run-id ^<run-id^> --observed-at-utc ^<YYYY-MM-DDTHH:MM:SSZ^> --source-workflow-run-url ^<github-actions-run-url^> --source-head-sha ^<github-actions-head-sha^> --source-run-attempt ^<github-actions-run-attempt^> --os-name "Windows XP" --os-architecture ^<x86-or-x64^> --os-service-pack ^<SP2-or-SP3^> [--os-edition ^<edition^>] [--security-update-channel ^<channel^> --cve-review-reference ^<reference^>]
exit /b 2

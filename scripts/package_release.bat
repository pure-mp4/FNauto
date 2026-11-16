@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "SRC=dist\FNauto"
if not exist "%SRC%\FNauto.exe" (
  echo Build first: build.bat
  exit /b 1
)

set "VERSION="
for /f "usebackq delims=" %%V in (`python -c "from version import APP_VERSION; print(APP_VERSION)"`) do set "VERSION=%%V"
if not defined VERSION (
  echo Could not read the version from version.py
  exit /b 1
)

set "ZIP=FNauto-v%VERSION%-win64.zip"
set "SUM=%ZIP%.sha256"
if exist "%ZIP%" del /f /q "%ZIP%"
if exist "%SUM%" del /f /q "%SUM%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%SRC%' -DestinationPath '%ZIP%' -Force"
if errorlevel 1 (
  echo Could not create %ZIP%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash -Algorithm SHA256 -LiteralPath '%ZIP%').Hash.ToLower(); Set-Content -LiteralPath '%SUM%' -Value ($h + '  %ZIP%') -Encoding ASCII"
if errorlevel 1 (
  echo Could not create %SUM%
  exit /b 1
)

echo Created %ZIP%
echo Created %SUM%

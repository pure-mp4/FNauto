@echo off
cd /d "%~dp0"
set "FNAUTO_ICON=%~dp0icon.ico"
set "FNAUTO_VERSION_FILE=%~dp0version_info.txt"
if not exist "%FNAUTO_ICON%" (
  echo Missing icon: %FNAUTO_ICON%
  exit /b 1
)
python scripts\make_version_info.py --output "%FNAUTO_VERSION_FILE%"
if errorlevel 1 exit /b 1
python build_with_icon.py --icon "%FNAUTO_ICON%" --version-file "%FNAUTO_VERSION_FILE%"
if errorlevel 1 exit /b 1
echo Build complete: dist\FNauto\FNauto.exe

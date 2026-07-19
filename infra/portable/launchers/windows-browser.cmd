@echo off
setlocal
set "ROOT=%~dp0"
set "BROWSER=%ROOT%BIN\thorium.exe"
if not exist "%BROWSER%" (
  echo Thorium executable not found: "%BROWSER%" 1>&2
  exit /b 111
)
start "" /D "%ROOT%BIN" "%BROWSER%" --user-data-dir="%ROOT%USER_DATA" --disable-encryption --disable-machine-id %*

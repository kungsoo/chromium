@echo off
setlocal
set "ROOT=%~dp0"
set "SHELL_EXE=%ROOT%@THORIUM_SHELL_RELATIVE@"
if exist "%SHELL_EXE%" goto :found
echo thorium_shell.exe was not found below "%ROOT%BIN". 1>&2
exit /b 111

:found
start "" /D "%ROOT%BIN" "%SHELL_EXE%" --user-data-dir="%ROOT%USER_DATA\thorium_shell" --disable-encryption --disable-machine-id --enable-experimental-web-platform-features --enable-clear-hevc-for-testing %*

@echo off
setlocal EnableExtensions
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\manage\install_operator_shortcuts.ps1" %*
exit /b %ERRORLEVEL%
endlocal

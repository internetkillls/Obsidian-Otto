@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" uninstall-health-automation %*
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" install-health-automation %*
exit /b %ERRORLEVEL%
endlocal

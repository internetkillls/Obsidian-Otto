@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" openclaw-gateway-restart %*
set "EXITCODE=%ERRORLEVEL%"
exit /b %EXITCODE%

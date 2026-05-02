@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" openclaw-gateway-probe %*
set "EXITCODE=%ERRORLEVEL%"
exit /b %EXITCODE%

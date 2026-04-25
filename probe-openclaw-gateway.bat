@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" openclaw-gateway-probe %*
set "EXITCODE=%ERRORLEVEL%"
if "%OTTO_NO_PAUSE%"=="" pause
exit /b %EXITCODE%

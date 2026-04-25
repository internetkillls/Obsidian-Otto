@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" openclaw-gateway-restart %*
set "EXITCODE=%ERRORLEVEL%"
if not "%OTTO_NO_PAUSE%"=="1" pause
exit /b %EXITCODE%

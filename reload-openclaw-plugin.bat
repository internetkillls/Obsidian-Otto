@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" openclaw-plugin-reload %*
set "EXITCODE=%ERRORLEVEL%"
if "%OTTO_NO_PAUSE%"=="" pause
exit /b %EXITCODE%

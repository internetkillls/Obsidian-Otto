@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" openclaw-plugin-reload %*
set "EXITCODE=%ERRORLEVEL%"
exit /b %EXITCODE%

@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" wsl-live-promote --gateway-port 18790 --write
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" wsl-live-preflight --gateway-port 18790
exit /b %ERRORLEVEL%
endlocal

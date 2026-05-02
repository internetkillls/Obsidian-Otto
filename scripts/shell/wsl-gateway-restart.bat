@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" wsl-gateway-restart %*
exit /b %ERRORLEVEL%
endlocal

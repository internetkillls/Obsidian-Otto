@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" wsl-gateway-start %*
exit /b %ERRORLEVEL%
endlocal

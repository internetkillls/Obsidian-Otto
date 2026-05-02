@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" wsl-gateway-stop %*
exit /b %ERRORLEVEL%
endlocal

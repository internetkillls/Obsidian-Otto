@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" gateway-owner %*
exit /b %ERRORLEVEL%
endlocal

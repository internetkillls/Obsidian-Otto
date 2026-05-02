@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" operator-status %*
exit /b %ERRORLEVEL%
endlocal

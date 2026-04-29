@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" kairos %*
exit /b %ERRORLEVEL%
endlocal

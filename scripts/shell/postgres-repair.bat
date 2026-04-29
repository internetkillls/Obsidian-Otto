@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" postgres-repair %*
exit /b %ERRORLEVEL%
endlocal

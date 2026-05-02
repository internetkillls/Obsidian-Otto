@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" health-repair %*
exit /b %ERRORLEVEL%
endlocal

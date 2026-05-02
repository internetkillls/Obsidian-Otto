@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" status %*
set "EXITCODE=%ERRORLEVEL%"
exit /b %EXITCODE%
endlocal

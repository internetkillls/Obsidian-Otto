@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" sanity-check %*
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" sync-openclaw %*
set "EXITCODE=%ERRORLEVEL%"
exit /b %EXITCODE%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" sanity-check %*
exit /b %ERRORLEVEL%
endlocal

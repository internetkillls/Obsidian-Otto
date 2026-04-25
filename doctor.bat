@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" doctor %*
set "EXITCODE=%ERRORLEVEL%"
if not "%OTTO_NO_PAUSE%"=="1" pause
exit /b %EXITCODE%
endlocal

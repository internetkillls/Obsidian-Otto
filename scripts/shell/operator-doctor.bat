@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" operator-doctor %*
exit /b %ERRORLEVEL%
endlocal

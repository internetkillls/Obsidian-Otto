@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" operator-update %*
exit /b %ERRORLEVEL%
endlocal

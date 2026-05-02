@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" brain %*
exit /b %ERRORLEVEL%
endlocal

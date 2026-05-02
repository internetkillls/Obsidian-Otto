@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" %*
exit /b %ERRORLEVEL%
endlocal

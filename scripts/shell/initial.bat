@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" init %*
exit /b %ERRORLEVEL%
endlocal

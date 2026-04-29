@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" advanced
exit /b %ERRORLEVEL%
endlocal

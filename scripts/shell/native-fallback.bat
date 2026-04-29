@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" native-fallback %*
exit /b %ERRORLEVEL%
endlocal

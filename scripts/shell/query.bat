@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" query %*
exit /b %ERRORLEVEL%
endlocal

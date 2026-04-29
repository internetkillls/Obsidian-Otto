@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" dream %*
exit /b %ERRORLEVEL%
endlocal

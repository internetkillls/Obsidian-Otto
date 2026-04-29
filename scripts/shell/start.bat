@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" start %*
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" stop %*
exit /b %ERRORLEVEL%
endlocal

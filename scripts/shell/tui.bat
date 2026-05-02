@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" tui %*
exit /b %ERRORLEVEL%
endlocal

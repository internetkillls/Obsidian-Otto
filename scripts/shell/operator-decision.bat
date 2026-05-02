@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" operator-decision %*
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" metadata-enrich %*
exit /b %ERRORLEVEL%
endlocal

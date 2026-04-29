@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" notion-export-hygiene %*
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" kairos %*
exit /b %ERRORLEVEL%
endlocal

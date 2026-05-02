@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" docker-clean %*
exit /b %ERRORLEVEL%
endlocal

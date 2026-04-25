@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" docker-clean %*
exit /b %ERRORLEVEL%
endlocal

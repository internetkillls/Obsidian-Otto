@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" docker-up %*
exit /b %ERRORLEVEL%
endlocal

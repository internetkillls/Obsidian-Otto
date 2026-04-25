@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" brain %*
exit /b %ERRORLEVEL%
endlocal

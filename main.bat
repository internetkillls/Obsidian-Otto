@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" %*
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" init %*
exit /b %ERRORLEVEL%
endlocal

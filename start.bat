@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" start %*
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" stop %*
exit /b %ERRORLEVEL%
endlocal

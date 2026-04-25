@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" query %*
exit /b %ERRORLEVEL%
endlocal

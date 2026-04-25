@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" dream %*
exit /b %ERRORLEVEL%
endlocal

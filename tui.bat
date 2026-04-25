@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" tui %*
exit /b %ERRORLEVEL%
endlocal

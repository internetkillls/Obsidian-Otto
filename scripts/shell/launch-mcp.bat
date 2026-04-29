@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" launch-mcp %*
exit /b %ERRORLEVEL%
endlocal

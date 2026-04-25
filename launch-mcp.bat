@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" launch-mcp %*
exit /b %ERRORLEVEL%
endlocal

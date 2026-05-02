@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" mcp-clean %*
exit /b %ERRORLEVEL%
endlocal

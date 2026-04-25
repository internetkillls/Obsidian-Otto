@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" sync-openclaw %*
exit /b %ERRORLEVEL%
endlocal

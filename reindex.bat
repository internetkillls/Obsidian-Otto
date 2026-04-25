@echo off
setlocal EnableExtensions
call "%~dp0otto.bat" reindex %*
exit /b %ERRORLEVEL%
endlocal

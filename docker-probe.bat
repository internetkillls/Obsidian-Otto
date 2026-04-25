@echo off
setlocal
call "%~dp0otto.bat" docker-probe %*
exit /b %ERRORLEVEL%

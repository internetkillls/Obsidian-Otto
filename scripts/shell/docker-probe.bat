@echo off
setlocal
call "%~dp0..\..\otto.bat" docker-probe %*
exit /b %ERRORLEVEL%

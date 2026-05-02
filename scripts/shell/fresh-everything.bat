@echo off
setlocal EnableExtensions
call "%~dp0..\..\otto.bat" fresh-everything %*
exit /b %ERRORLEVEL%
endlocal

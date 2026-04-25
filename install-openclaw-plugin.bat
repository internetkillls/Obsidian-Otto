@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
openclaw plugins install -l "%ROOT%packages\openclaw-otto-bridge" --force
if errorlevel 1 exit /b %ERRORLEVEL%
echo [Otto] Plugin linked. Restart the OpenClaw gateway to load the new tools.
exit /b 0

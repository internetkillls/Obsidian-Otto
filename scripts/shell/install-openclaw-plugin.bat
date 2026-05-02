@echo off
setlocal EnableExtensions
set "ROOT=%~dp0..\.."
pushd "%ROOT%"
if errorlevel 1 exit /b %ERRORLEVEL%
openclaw plugins install -l "%CD%\packages\openclaw-otto-bridge" --force
if not errorlevel 1 goto linked
openclaw plugins install -l "%CD%\packages\openclaw-otto-bridge"
if errorlevel 1 (
  popd
  exit /b %ERRORLEVEL%
)
:linked
popd
echo [Otto] Plugin linked. Restart the OpenClaw gateway to load the new tools.
exit /b 0

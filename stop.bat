@echo off
setlocal
set "ROOT=%~dp0"
set "PID_FILE=%ROOT%state\pids\runtime.pid"
if not exist "%PID_FILE%" (
  echo No runtime PID file found.
  exit /b 0
)
set /p OTTO_PID=<"%PID_FILE%"
if "%OTTO_PID%"=="" (
  echo PID file was empty.
  exit /b 1
)
:: Verify the PID is actually a Python process (Otto runtime) before killing
for /f "tokens=2" %%a in ('tasklist /FI "PID eq %OTTO_PID%" /FO CSV /NH 2^>nul') do (
    set "PROC_NAME=%%~a"
)
if not defined PROC_NAME (
    echo Process %OTTO_PID% not found — stale PID file removed.
    del "%PID_FILE%" >nul 2>nul
    exit /b 0
)
echo [Otto] Stopping runtime PID %OTTO_PID% ...
taskkill /PID %OTTO_PID% /T /F 2>nul
del "%PID_FILE%" >nul 2>nul
echo [Otto] Stopped.
endlocal

@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "COMMON=%ROOT%scripts\shell\otto_common.bat"
set "LAUNCHER=%ROOT%scripts\manage\run_launcher.py"

if not exist "%COMMON%" (
    echo [ERROR] Missing helper: scripts\shell\otto_common.bat
    exit /b 1
)
if not exist "%LAUNCHER%" (
    echo [ERROR] Missing launcher script: scripts\manage\run_launcher.py
    exit /b 1
)

call "%COMMON%" :ensure_python_env "%ROOT%" PYTHON_EXE PYTHONPATH_VALUE
if errorlevel 1 (
    echo [Otto] Virtual environment missing. Run initial.bat first.
    exit /b 1
)

set "PYTHONPATH=%PYTHONPATH_VALUE%"
"%PYTHON_EXE%" "%LAUNCHER%" --once brain -- %*
exit /b %ERRORLEVEL%
endlocal

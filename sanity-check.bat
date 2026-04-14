@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "COMMON=%ROOT%scripts\shell\otto_common.bat"

if not exist "%COMMON%" (
  echo [ERROR] Missing helper: scripts\shell\otto_common.bat
  exit /b 1
)

call "%COMMON%" :ensure_python_env "%ROOT%" PYTHON_EXE PYTHONPATH_VALUE
if errorlevel 1 (
  echo [Otto] Virtual environment missing. Run initial.bat first.
  exit /b 1
)

set "PYTHONPATH=%PYTHONPATH_VALUE%"
"%PYTHON_EXE%" "%ROOT%scripts\manage\sanity_check.py" --write-report
exit /b %ERRORLEVEL%
endlocal

@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>nul

set "ROOT=%~dp0"
set "COMMON=%ROOT%scripts\shell\otto_common.bat"
set "BOOTSTRAP=%ROOT%scripts\shell\otto_bootstrap.bat"
set "LAUNCHER=%ROOT%scripts\manage\run_launcher.py"

if /I "%~1"=="env-check" goto :env_check
if /I "%~1"=="init" goto :init

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
    echo [Otto] Virtual environment missing. Run `otto.bat init` first.
    exit /b 1
)

if /I "%~1"=="help" goto :help
if /I "%~1"=="list" goto :list
if /I "%~1"=="describe" goto :describe

set "PYTHONPATH=%PYTHONPATH_VALUE%"

if "%~1"=="" (
    "%PYTHON_EXE%" "%LAUNCHER%"
    exit /b %ERRORLEVEL%
)

set "ACTION=%~1"
shift
"%PYTHON_EXE%" "%LAUNCHER%" --once "%ACTION%" -- %*
exit /b %ERRORLEVEL%

:env_check
if not exist "%COMMON%" (
    echo MISSING
    exit /b 1
)
call "%COMMON%" :ensure_python_env "%ROOT%" PYTHON_EXE PYTHONPATH_VALUE
if errorlevel 1 (
    echo MISSING
    exit /b 1
)
echo OK
exit /b 0

:init
if not exist "%BOOTSTRAP%" (
    echo [ERROR] Missing bootstrap script: scripts\shell\otto_bootstrap.bat
    exit /b 1
)
call "%BOOTSTRAP%"
exit /b %ERRORLEVEL%

:help
set "PYTHONPATH=%PYTHONPATH_VALUE%"
echo Obsidian-Otto command surface
echo.
echo   otto.bat               Open the interactive launcher
echo   otto.bat list          List available commands
echo   otto.bat describe X    Describe one command
echo   otto.bat docker-probe  Diagnose Docker access used by status
echo   otto.bat ^<action^>     Run one action directly
echo.
"%PYTHON_EXE%" "%LAUNCHER%" --list-actions
exit /b %ERRORLEVEL%

:list
set "PYTHONPATH=%PYTHONPATH_VALUE%"
"%PYTHON_EXE%" "%LAUNCHER%" --list-actions
exit /b %ERRORLEVEL%

:describe
set "PYTHONPATH=%PYTHONPATH_VALUE%"
if "%~2"=="" (
    echo [ERROR] Missing action name. Example: otto.bat describe status
    exit /b 1
)
"%PYTHON_EXE%" "%LAUNCHER%" --describe "%~2"
exit /b %ERRORLEVEL%

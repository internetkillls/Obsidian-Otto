@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "ROOT=%~dp0"
pushd "%ROOT%"

if not exist ".venv\Scripts\python.exe" (
    echo [Otto] Creating virtual environment...
    where py >nul 2>nul && (
        py -3 -m venv .venv
    ) || (
        python -m venv .venv
    )
)

set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [Otto] Could not find virtual environment Python.
    exit /b 1
)

echo [Otto] Upgrading pip...
"%PYTHON_EXE%" -m pip install --upgrade pip >nul

echo [Otto] Installing core requirements...
"%PYTHON_EXE%" -m pip install -r "%ROOT%requirements.txt"

echo.
echo Enter vault path, type PICK to browse, or press Enter for bundled sample vault:
set /p OTTO_VAULT_PATH=Vault path [Enter/PICK/path]: 

if /I "%OTTO_VAULT_PATH%"=="PICK" (
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\install\pick_vault.ps1"`) do (
        set "OTTO_VAULT_PATH=%%I"
    )
)

if "%OTTO_VAULT_PATH%"=="" set "OTTO_VAULT_PATH=%ROOT%data\sample\vault"

set /p OTTO_USE_DOCKER=Enable optional Docker helpers? [y/N]: 
set "OTTO_DOCKER_FLAG="
if /I "%OTTO_USE_DOCKER%"=="y" set "OTTO_DOCKER_FLAG=--docker"
if /I "%OTTO_USE_DOCKER%"=="yes" set "OTTO_DOCKER_FLAG=--docker"

echo [Otto] Bootstrapping...
set "PYTHONPATH=%ROOT%src"
"%PYTHON_EXE%" "%ROOT%scripts\install\bootstrap.py" --non-interactive --vault-path "%OTTO_VAULT_PATH%" %OTTO_DOCKER_FLAG%
if errorlevel 1 (
    echo [Otto] Bootstrap failed.
    exit /b 1
)

echo.
echo [Otto] Running sanity check...
"%PYTHON_EXE%" "%ROOT%scripts\manage\sanity_check.py" --write-report

echo.
echo [Otto] Done.
echo Next:
echo   - status.bat
echo   - tui.bat
echo   - reindex.bat
echo   - sanity-check.bat
popd
endlocal

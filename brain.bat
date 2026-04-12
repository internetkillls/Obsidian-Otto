@echo off
setlocal

cd /d "%~dp0"

if "%~1"=="" (
    echo Otto Brain CLI
    echo Usage: brain.bat [self-model ^| predictions ^| ritual ^| all]
    echo.
    echo   self-model   - Build Otto self-model from vault scan
    echo   predictions  - Generate Otto predictions from profile
    echo   ritual       - Run full scan/reflect/dream/act cycle
    echo   all          - Run self-model + predictions + ritual cycle
    exit /b 1
)

set "PYTHONPATH=%~dp0src"

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python -m otto.brain_cli %*

endlocal

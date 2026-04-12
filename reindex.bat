@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
set "PYTHONPATH=%ROOT%src"

set /p OTTO_SCOPE=Optional scope (blank for full vault): 
if "%OTTO_SCOPE%"=="" (
  "%PYTHON_EXE%" "%ROOT%scripts\manage\run_pipeline.py" --full
) else (
  "%PYTHON_EXE%" "%ROOT%scripts\manage\run_pipeline.py" --scope "%OTTO_SCOPE%" --full
)
endlocal

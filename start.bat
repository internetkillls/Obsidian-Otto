@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Virtual environment missing. Run initial.bat first.
  exit /b 1
)
set "PYTHONPATH=%ROOT%src"
echo [Otto] Starting background runtime...
start "Obsidian-Otto Runtime" /min "%PYTHON_EXE%" "%ROOT%scripts\manage\runtime_loop.py"
echo [Otto] Started. Check status.bat or tui.bat.
endlocal

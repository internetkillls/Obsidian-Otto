@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
set "PYTHONPATH=%ROOT%src"
set /p OTTO_QUERY=Enter query: 
"%PYTHON_EXE%" "%ROOT%scripts\manage\query_memory.py" --mode fast --query "%OTTO_QUERY%"
endlocal

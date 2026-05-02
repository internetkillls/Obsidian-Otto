@echo off
if "%~1"=="" goto :eof
goto %~1

:ensure_python_env
setlocal
set "ROOT=%~2"
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
set "PYTHONPATH_VALUE=%ROOT%src"
if not exist "%PYTHON_EXE%" (
    endlocal & exit /b 1
)
endlocal & (
    set "%~3=%PYTHON_EXE%"
    set "%~4=%PYTHONPATH_VALUE%"
)
exit /b 0

@echo off
setlocal
echo === Obsidian-Otto Doctor ===
call "%~dp0status.bat"
echo.
call "%~dp0sanity-check.bat"
echo.
echo === QMD Memory Index Health ===
call "%~dp0qmd-health.bat"
echo.
echo Remediation hints:
echo   Docker:     otto.bat docker-clean
echo   Pipeline:   otto.bat reindex
echo   OpenClaw:   otto.bat sync-openclaw
echo   QMD index:  otto.bat qmd-reindex
endlocal

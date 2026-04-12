@echo off
setlocal
echo === Obsidian-Otto Doctor ===
call "%~dp0status.bat"
echo.
call "%~dp0sanity-check.bat"
echo.
echo To clean Docker services, run docker-clean.bat
echo To rerun the data pipeline, run reindex.bat
endlocal

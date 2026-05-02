@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

:menu
cls
echo.
echo  ╔══════════════════════════════╗
echo  ║      Obsidian-Otto          ║
echo  ╚══════════════════════════════╝
echo.
echo  DAILY
echo    1   tui.bat          Live dashboard
echo    2   query.bat        Query memory
echo    3   reindex.bat      Re-run pipeline
echo.
echo  BACKGROUND
echo    4   start.bat        Start runtime
echo    5   stop.bat         Stop runtime
echo    6   kairos.bat       KAIROS heartbeat
echo    7   dream.bat        Dream consolidation
echo    8   brain.bat        Brain self-model
echo.
echo  OPENCLAW ^& MEMORY
echo    9   sync-openclaw.bat  Sync config + QMD check
echo   10   qmd-health.bat     QMD index status
echo   11   qmd-reindex.bat    Trigger QMD reindex
echo   12   launch-mcp.bat     Start MCP server
echo.
echo  DIAGNOSTICS
echo   13   doctor.bat       Full diagnostic
echo   14   status.bat       Status JSON
echo   15   sanity-check.bat Sanity check
echo.
echo  SETUP
echo   16   initial.bat      First-time setup
echo   17   docker-up.bat    Start Docker
echo   18   docker-clean.bat Stop / clean Docker
echo.
echo    0   Exit
echo.
set /p CHOICE=  Choice:

if "%CHOICE%"=="1"  call "%~dp0tui.bat"            & goto menu
if "%CHOICE%"=="2"  call "%~dp0query.bat"           & goto menu
if "%CHOICE%"=="3"  call "%~dp0reindex.bat"         & goto menu
if "%CHOICE%"=="4"  call "%~dp0start.bat"           & goto menu
if "%CHOICE%"=="5"  call "%~dp0stop.bat"            & goto menu
if "%CHOICE%"=="6"  call "%~dp0kairos.bat"          & goto menu
if "%CHOICE%"=="7"  call "%~dp0dream.bat"           & goto menu
if "%CHOICE%"=="8"  call "%~dp0brain.bat" all       & goto menu
if "%CHOICE%"=="9"  call "%~dp0sync-openclaw.bat"   & pause & goto menu
if "%CHOICE%"=="10" call "%~dp0qmd-health.bat"      & pause & goto menu
if "%CHOICE%"=="11" call "%~dp0qmd-reindex.bat"     & pause & goto menu
if "%CHOICE%"=="12" call "%~dp0launch-mcp.bat"      & goto menu
if "%CHOICE%"=="13" call "%~dp0doctor.bat"          & pause & goto menu
if "%CHOICE%"=="14" call "%~dp0status.bat"          & pause & goto menu
if "%CHOICE%"=="15" call "%~dp0sanity-check.bat"    & pause & goto menu
if "%CHOICE%"=="16" call "%~dp0initial.bat"         & pause & goto menu
if "%CHOICE%"=="17" call "%~dp0docker-up.bat"       & pause & goto menu
if "%CHOICE%"=="18" call "%~dp0docker-clean.bat"    & pause & goto menu
if "%CHOICE%"=="0"  goto :eof

echo  [!] Invalid choice.
pause
goto menu

endlocal

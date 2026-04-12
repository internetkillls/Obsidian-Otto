@echo off
setlocal
set "ROOT=%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker is not installed or not on PATH.
  exit /b 1
)
docker compose -f "%ROOT%docker-compose.yml" up -d
endlocal

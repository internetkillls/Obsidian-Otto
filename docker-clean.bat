@echo off
setlocal
set "ROOT=%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker is not installed or not on PATH.
  exit /b 0
)
if not exist "%ROOT%docker-compose.yml" (
  echo No docker-compose.yml found.
  exit /b 0
)
docker compose -f "%ROOT%docker-compose.yml" down -v --remove-orphans
endlocal

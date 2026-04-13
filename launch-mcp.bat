@echo off
setlocal

REM Otto MCP Fabric Launcher
REM - obsidian-mcp:       foreground stdio (OpenClaw connects via pipe)
REM - obsidian-scripts-mcp: background detached (runs Otto script tools)

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Start Docker Desktop first.
    exit /b 1
)

REM Load .env if it exists
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
)

REM Ensure required env vars
if not defined OBSIDIAN_VAULT_HOST (
    set "OBSIDIAN_VAULT_HOST=C:\Users\joshu\Obsidian\Vault"
    echo [WARN] OBSIDIAN_VAULT_HOST not set. Defaulting to C:\Users\joshu\Obsidian\Vault
    echo [WARN] Edit .env to configure.
)
if not defined OBSIDIAN_VAULT_PATH (
    set "OBSIDIAN_VAULT_PATH=/vault"
)

REM Build containers
echo [OTTO] Building MCP containers...
docker compose -f docker-compose.yml build obsidian-mcp obsidian-scripts-mcp
if errorlevel 1 (
    echo [ERROR] MCP container build failed.
    exit /b 1
)

REM Start obsidian-scripts-mcp in background
echo [OTTO] Starting obsidian-scripts-mcp (background)...
docker compose -f docker-compose.yml up -d obsidian-scripts-mcp
if errorlevel 1 (
    echo [ERROR] obsidian-scripts-mcp start failed.
    exit /b 1
)

REM Start obsidian-mcp in foreground stdio
echo [OTTO] Starting obsidian-mcp (foreground stdio)...
docker compose -f docker-compose.yml run --rm ^
    -e OBSIDIAN_VAULT_PATH="%OBSIDIAN_VAULT_PATH%" ^
    -v "%OBSIDIAN_VAULT_HOST%:%OBSIDIAN_VAULT_PATH%:ro" ^
    obsidian-mcp

endlocal

@echo off
setlocal

REM Otto MCP Fabric Launcher
REM Starts Obsidian MCP and Obsidian CLI MCP containers via docker-compose

REM Ensure .env exists
if not exist ".env" (
    echo OBSIDIAN_VAULT_PATH=C:\Users\joshu\Obsidian\Vault > .env
    echo OBSIDIAN_VAULT_HOST=C:\Users\joshu\Obsidian >> .env
    echo [WARN] Created .env with default vault path. Edit .env to configure.
)

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Start Docker Desktop first.
    exit /b 1
)

REM Build and start MCP containers
echo [OTTO] Building MCP containers...
docker compose -f docker-compose.yml build obsidian-mcp obsidian-cli-mcp
if errorlevel 1 (
    echo [ERROR] MCP container build failed.
    exit /b 1
)

echo [OTTO] Starting MCP Fabric...
docker compose -f docker-compose.yml up -d obsidian-mcp obsidian-cli-mcp
if errorlevel 1 (
    echo [ERROR] MCP container start failed.
    exit /b 1
)

echo [OTTO] MCP Fabric started.
echo [OTTO] Obsidian MCP: running (stdio on obsidian-mcp container)
echo [OTTO] Obsidian CLI MCP: running (stdio on obsidian-cli-mcp container)
echo [OTTO] Connect OpenClaw via: docker compose -f docker-compose.yml exec obsidian-mcp ...
echo [OTTO] See docs/migration-plan.md Phase 1b for verification steps.

endlocal

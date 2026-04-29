param(
    [switch]$NoStartupTask,
    [switch]$Uninstall,
    [string]$TaskName = "Obsidian-Otto WSL Gateway Startup"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$OttoBat = Join-Path $Root "otto.bat"
$StateDir = Join-Path $Root "state\operator"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Startup = [Environment]::GetFolderPath("Startup")
$Shell = New-Object -ComObject WScript.Shell

function New-OttoShortcut {
    param(
        [string]$Name,
        [string]$Arguments,
        [string]$Description
    )
    $Path = Join-Path $Desktop $Name
    $Shortcut = $Shell.CreateShortcut($Path)
    $Shortcut.TargetPath = $OttoBat
    $Shortcut.Arguments = $Arguments
    $Shortcut.WorkingDirectory = $Root
    $Shortcut.Description = $Description
    $Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
    $Shortcut.Save()
    return $Path
}

if (!(Test-Path $OttoBat)) {
    throw "Missing otto.bat at $OttoBat"
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

if ($Uninstall) {
    $ShortcutNames = @(
        "Obsidian-Otto Operator.lnk",
        "Otto Start WSL Gateway.lnk",
        "Otto Restart WSL Gateway.lnk",
        "Otto WSL Live Status.lnk",
        "Otto Native Fallback.lnk"
    )
    foreach ($Name in $ShortcutNames) {
        $Path = Join-Path $Desktop $Name
        if (Test-Path $Path) {
            Remove-Item -LiteralPath $Path -Force
        }
    }
    $StartupShortcut = Join-Path $Startup "Otto WSL Gateway Startup.lnk"
    if (Test-Path $StartupShortcut) {
        Remove-Item -LiteralPath $StartupShortcut -Force
    }
    schtasks.exe /Delete /TN $TaskName /F *> $null
    $Result = @{
        ok = $true
        state = "OPERATOR_SHORTCUTS_UNINSTALLED"
        updated_at = (Get-Date).ToString("o")
        desktop = $Desktop
        startup_task = $TaskName
    }
    $Result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $StateDir "shortcut_install_last.json") -Encoding UTF8
    $Result | ConvertTo-Json -Depth 5
    exit 0
}

$Created = @()
$Created += New-OttoShortcut -Name "Obsidian-Otto Operator.lnk" -Arguments "advanced" -Description "Open the Obsidian-Otto operator launcher."
$Created += New-OttoShortcut -Name "Otto Start WSL Gateway.lnk" -Arguments "wsl-gateway-start" -Description "Start the current WSL OpenClaw gateway config."
$Created += New-OttoShortcut -Name "Otto Restart WSL Gateway.lnk" -Arguments "wsl-gateway-restart" -Description "Restart the current WSL OpenClaw gateway config."
$Created += New-OttoShortcut -Name "Otto WSL Live Status.lnk" -Arguments "wsl-live-status" -Description "Show WSL live owner, gateway, and rollback status."
$Created += New-OttoShortcut -Name "Otto Native Fallback.lnk" -Arguments "native-fallback" -Description "Fallback to native Windows OpenClaw if WSL fails."

$TaskInstalled = $false
$TaskError = $null
$StartupShortcut = $null
if (-not $NoStartupTask) {
    $TaskCommand = "`"$OttoBat`" wsl-gateway-start"
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $TaskOutput = schtasks.exe /Create /F /TN $TaskName /SC ONLOGON /TR $TaskCommand /RL LIMITED 2>&1
    $ErrorActionPreference = $PreviousErrorActionPreference
    if ($LASTEXITCODE -eq 0) {
        $TaskInstalled = $true
    } else {
        $TaskError = ($TaskOutput | Out-String).Trim()
        New-Item -ItemType Directory -Force -Path $Startup | Out-Null
        $StartupShortcut = Join-Path $Startup "Otto WSL Gateway Startup.lnk"
        $Shortcut = $Shell.CreateShortcut($StartupShortcut)
        $Shortcut.TargetPath = $OttoBat
        $Shortcut.Arguments = "wsl-gateway-start"
        $Shortcut.WorkingDirectory = $Root
        $Shortcut.Description = "Start the Obsidian-Otto WSL OpenClaw gateway on Windows login."
        $Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
        $Shortcut.Save()
    }
}

$Result = @{
    ok = $true
    state = "OPERATOR_SHORTCUTS_INSTALLED"
    updated_at = (Get-Date).ToString("o")
    desktop = $Desktop
    shortcuts = $Created
    startup_task = @{
        installed = $TaskInstalled
        name = $TaskName
        command = "$OttoBat wsl-gateway-start"
        error = $TaskError
        fallback_startup_shortcut = $StartupShortcut
    }
    next_required_action = "Use the desktop Operator shortcut, or restart Windows to let the startup task open the current WSL gateway."
}

$Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $StateDir "shortcut_install_last.json") -Encoding UTF8
$Result | ConvertTo-Json -Depth 6

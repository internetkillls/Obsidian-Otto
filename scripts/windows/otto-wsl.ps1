param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"
$Launcher = "/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-cli-wsl.sh"
$WslArgs = @("-d", "Ubuntu", "--", $Launcher) + $CliArgs

& wsl.exe @WslArgs
exit $LASTEXITCODE

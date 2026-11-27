# Start the bridge hidden at Windows login (current user only).
# Install:   powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1
# Remove:    powershell -ExecutionPolicy Bypass -File tools\install_autostart.ps1 -Remove
# Log file:  %LOCALAPPDATA%\mlbb_presence\bridge.log
param([switch]$Remove)

$startup = [Environment]::GetFolderPath('Startup')
$vbs = Join-Path $startup 'mlbb_presence.vbs'
if ($Remove) {
    if (Test-Path $vbs) { Remove-Item $vbs -Confirm:$false; "removed $vbs" } else { "not installed" }
    return
}

$repo = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
$logDir = Join-Path $env:LOCALAPPDATA 'mlbb_presence'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'bridge.log'

# cmd /c keeps the redirect; window style 0 = hidden. The log is replaced at each login.
$cmd = "cmd /c cd /d ""$repo"" && ""$python"" -u -m mlbb_presence > ""$log"" 2>&1"
$quoted = $cmd.Replace('"', '""')  # VBScript doubles quotes inside a string
$body = 'CreateObject("WScript.Shell").Run "' + $quoted + '", 0, False'
Set-Content -Path $vbs -Value $body -Encoding ASCII
"installed $vbs"
"log: $log"

param(
  [string]$ShortcutName = "Value Investment"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $PSScriptRoot "start-app.ps1"
$IconPath = Join-Path $Root "assets\value-investment.ico"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$DesktopDirectory = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopDirectory "$ShortcutName.lnk"

if (-not (Test-Path $IconPath)) {
  throw "Desktop shortcut icon not found: $IconPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $PowerShellExe
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`""
$shortcut.WorkingDirectory = $Root
$shortcut.Description = "Start the Value Investment workbench"
$shortcut.IconLocation = "$IconPath,0"
$shortcut.WindowStyle = 7
$shortcut.Save()

Write-Host "Desktop shortcut created: $ShortcutPath"

param(
  [int]$GracefulTimeoutSeconds = 12
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $Root "data\runtime"
$SessionFile = Join-Path $RuntimeDir "app-session.json"

function Test-PathInsideRuntimeDirectory {
  param([string]$CandidatePath)

  if (-not $CandidatePath) {
    return $false
  }

  $resolvedRuntime = [System.IO.Path]::GetFullPath($RuntimeDir).TrimEnd('\')
  $resolvedCandidateParent = [System.IO.Path]::GetDirectoryName(
    [System.IO.Path]::GetFullPath($CandidatePath)
  ).TrimEnd('\')
  return $resolvedCandidateParent -eq $resolvedRuntime
}

function Test-ControllerIdentity {
  param(
    [int]$ControllerProcessId
  )

  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ControllerProcessId" -ErrorAction SilentlyContinue
  if ($null -eq $process) {
    return $false
  }

  $expectedScript = (Join-Path $PSScriptRoot "dev.ps1").ToLowerInvariant()
  $commandLine = ([string]$process.CommandLine).ToLowerInvariant()
  return $commandLine.Contains($expectedScript)
}

if (-not (Test-Path $SessionFile)) {
  Write-Host "No managed Value Investment session is running."
  exit 0
}

try {
  $session = Get-Content $SessionFile -Raw | ConvertFrom-Json
}
catch {
  throw "The local app session file is unreadable: $SessionFile"
}

if ([System.IO.Path]::GetFullPath([string]$session.project_root) -ne [System.IO.Path]::GetFullPath($Root)) {
  throw "The session file belongs to another project directory."
}

$controllerProcessId = [int]$session.controller_pid
if (-not (Get-Process -Id $controllerProcessId -ErrorAction SilentlyContinue)) {
  Remove-Item $SessionFile -Force -ErrorAction SilentlyContinue
  Write-Host "Removed a stale Value Investment session file."
  exit 0
}

if (-not (Test-ControllerIdentity -ControllerProcessId $controllerProcessId)) {
  throw "PID $controllerProcessId no longer belongs to this project's controller."
}

$stopRequestFile = [string]$session.stop_request_file
if (-not (Test-PathInsideRuntimeDirectory -CandidatePath $stopRequestFile)) {
  throw "The session stop request path is outside the project runtime directory."
}

Set-Content -Path $stopRequestFile -Value "local-script" -Encoding ASCII
$deadline = [DateTime]::UtcNow.AddSeconds($GracefulTimeoutSeconds)
while ([DateTime]::UtcNow -lt $deadline) {
  if (-not (Get-Process -Id $controllerProcessId -ErrorAction SilentlyContinue)) {
    Write-Host "Value Investment frontend and backend stopped."
    exit 0
  }
  Start-Sleep -Milliseconds 250
}

if (-not (Test-ControllerIdentity -ControllerProcessId $controllerProcessId)) {
  throw "Controller identity changed while waiting for shutdown."
}

$taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
& $taskkill /PID $controllerProcessId /T /F *> $null
Remove-Item $SessionFile -Force -ErrorAction SilentlyContinue
Remove-Item $stopRequestFile -Force -ErrorAction SilentlyContinue
Write-Host "Value Investment process tree was force-stopped after the graceful timeout."

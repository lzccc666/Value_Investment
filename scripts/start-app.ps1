param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$DevScript = Join-Path $PSScriptRoot "dev.ps1"
$StopScript = Join-Path $PSScriptRoot "stop-app.ps1"
$RuntimeDir = Join-Path $Root "data\runtime"
$SessionFile = Join-Path $RuntimeDir "app-session.json"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

function Show-StartupError {
  param([string]$Message)

  try {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
      $Message,
      "Value Investment",
      [System.Windows.MessageBoxButton]::OK,
      [System.Windows.MessageBoxImage]::Error
    ) | Out-Null
  }
  catch {
    Write-Error $Message
  }
}

function Get-ActiveSession {
  if (-not (Test-Path $SessionFile)) {
    return $null
  }

  try {
    $session = Get-Content $SessionFile -Raw | ConvertFrom-Json
  }
  catch {
    Remove-Item $SessionFile -Force -ErrorAction SilentlyContinue
    return $null
  }

  if (Get-Process -Id ([int]$session.controller_pid) -ErrorAction SilentlyContinue) {
    return $session
  }

  Remove-Item $SessionFile -Force -ErrorAction SilentlyContinue
  return $null
}

function Test-PortInUse {
  param([int]$Port)

  return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Find-FreePort {
  param(
    [int]$PreferredPort,
    [int]$SearchCount = 20
  )

  for ($candidate = $PreferredPort; $candidate -lt ($PreferredPort + $SearchCount); $candidate++) {
    if (-not (Test-PortInUse -Port $candidate)) {
      return $candidate
    }
  }

  throw "No free local port found from $PreferredPort to $($PreferredPort + $SearchCount - 1)."
}

try {
  $activeSession = Get-ActiveSession
  if ($null -ne $activeSession) {
    Start-Process ([string]$activeSession.frontend_url)
    exit 0
  }

  New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
  $BackendPort = Find-FreePort -PreferredPort $BackendPort
  $FrontendPort = Find-FreePort -PreferredPort $FrontendPort

  $arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$DevScript`"",
    "-BackendPort", $BackendPort,
    "-FrontendPort", $FrontendPort
  )
  $controller = Start-Process `
    -FilePath $PowerShellExe `
    -ArgumentList $arguments `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

  $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
  $frontendUrl = "http://127.0.0.1:$FrontendPort"
  $healthUrl = "http://127.0.0.1:$BackendPort/api/health"
  $started = $false

  while ([DateTime]::UtcNow -lt $deadline) {
    if ($controller.HasExited) {
      throw "The local app controller exited before startup completed. Check the logs directory."
    }

    try {
      $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
      $frontend = Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing -TimeoutSec 2
      if ($health.status -eq "ok" -and $frontend.StatusCode -eq 200) {
        $started = $true
        break
      }
    }
    catch {
      Start-Sleep -Milliseconds 500
    }
  }

  if (-not $started) {
    & $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File $StopScript | Out-Null
    throw "Startup timed out after $StartupTimeoutSeconds seconds. Check the logs directory."
  }

  Start-Process $frontendUrl
}
catch {
  Show-StartupError -Message $_.Exception.Message
  exit 1
}

param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [switch]$Force,
  [switch]$BackendOnly,
  [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$LogsDir = Join-Path $Root "logs"

if ($BackendOnly -and $FrontendOnly) {
  throw "Use only one of -BackendOnly or -FrontendOnly."
}

function Test-PortInUse {
  param(
    [int]$Port
  )

  return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Stop-ProcessOnPort {
  param(
    [int]$Port
  )

  $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue

    if ($null -eq $process) {
      throw "Port $Port is held by PID $processId, but that process is not visible. Use another port or restart Windows."
    }

    Stop-Process -Id $processId -Force
  }
}

if ((-not $FrontendOnly) -and (-not (Test-Path $PythonExe))) {
  throw "Backend virtual environment not found. Run .\scripts\setup.ps1 first."
}

if ((-not $BackendOnly) -and (-not (Test-Path (Join-Path $FrontendDir "node_modules")))) {
  throw "Frontend dependencies not found. Run .\scripts\setup.ps1 first."
}

if ((-not $FrontendOnly) -and (Test-PortInUse -Port $BackendPort) -and $Force) {
  Stop-ProcessOnPort -Port $BackendPort
  Start-Sleep -Seconds 1
}

if ((-not $BackendOnly) -and (Test-PortInUse -Port $FrontendPort) -and $Force) {
  Stop-ProcessOnPort -Port $FrontendPort
  Start-Sleep -Seconds 1
}

if ((-not $FrontendOnly) -and (Test-PortInUse -Port $BackendPort)) {
  throw "Port $BackendPort is already in use. Stop the existing backend process or pass -BackendPort."
}

if ((-not $BackendOnly) -and (Test-PortInUse -Port $FrontendPort)) {
  throw "Port $FrontendPort is already in use. Stop the existing frontend process or pass -FrontendPort."
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$backendStdOutLog = Join-Path $LogsDir "backend.out.log"
$backendStdErrLog = Join-Path $LogsDir "backend.err.log"
$frontendStdOutLog = Join-Path $LogsDir "frontend.out.log"
$frontendStdErrLog = Join-Path $LogsDir "frontend.err.log"

if (-not $FrontendOnly) {
  $backendProcess = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", $BackendPort) `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput $backendStdOutLog `
    -RedirectStandardError $backendStdErrLog
}

$previousBackendPort = $env:VITE_BACKEND_PORT
$previousApiBaseUrl = $env:VITE_API_BASE_URL
$env:VITE_BACKEND_PORT = "$BackendPort"
$env:VITE_API_BASE_URL = "/api"

if (-not $BackendOnly) {
  try {
    $frontendProcess = Start-Process `
      -FilePath "npm.cmd" `
      -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", $FrontendPort) `
      -WorkingDirectory $FrontendDir `
      -WindowStyle Hidden `
      -PassThru `
      -RedirectStandardOutput $frontendStdOutLog `
      -RedirectStandardError $frontendStdErrLog
  }
  finally {
    $env:VITE_BACKEND_PORT = $previousBackendPort
    $env:VITE_API_BASE_URL = $previousApiBaseUrl
  }
}

if (-not $FrontendOnly) {
  Write-Host "Backend:  http://127.0.0.1:$BackendPort"
}
if (-not $BackendOnly) {
  Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
  Write-Host "API:      http://127.0.0.1:$BackendPort/api"
}
Write-Host "Logs:"
if (-not $FrontendOnly) {
  Write-Host "  $backendStdOutLog"
  Write-Host "  $backendStdErrLog"
}
if (-not $BackendOnly) {
  Write-Host "  $frontendStdOutLog"
  Write-Host "  $frontendStdErrLog"
}
Write-Host "Press Ctrl+C to stop."

try {
  while ($true) {
    if ((-not $FrontendOnly) -and $backendProcess.HasExited) {
      throw "Backend process exited with code $($backendProcess.ExitCode). Check $backendStdOutLog and $backendStdErrLog."
    }

    if ((-not $BackendOnly) -and $frontendProcess.HasExited) {
      throw "Frontend process exited with code $($frontendProcess.ExitCode). Check $frontendStdOutLog and $frontendStdErrLog."
    }

    Start-Sleep -Seconds 2
  }
}
finally {
  if ((-not $FrontendOnly) -and (-not $backendProcess.HasExited)) {
    Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
  }

  if ((-not $BackendOnly) -and (-not $frontendProcess.HasExited)) {
    Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
  }
}

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
$RuntimeDir = Join-Path $Root "data\runtime"
$SessionFile = Join-Path $RuntimeDir "app-session.json"
$IsManagedSession = (-not $BackendOnly) -and (-not $FrontendOnly)
$backendProcess = $null
$frontendProcess = $null
$sessionId = $null
$stopRequestFile = $null

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

function Stop-ProcessTree {
  param(
    [int]$TargetProcessId
  )

  if (-not (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue)) {
    return
  }

  $taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
  if (Test-Path $taskkill) {
    & $taskkill /PID $TargetProcessId /T /F *> $null
    return
  }

  Stop-Process -Id $TargetProcessId -Force -ErrorAction SilentlyContinue
}

function Restore-EnvironmentValue {
  param(
    [string]$Name,
    [AllowNull()][string]$Value
  )

  if ($null -eq $Value) {
    Remove-Item "Env:$Name" -ErrorAction SilentlyContinue
  }
  else {
    Set-Item "Env:$Name" $Value
  }
}

function Remove-CurrentSessionFile {
  if (-not $IsManagedSession -or -not (Test-Path $SessionFile)) {
    return
  }

  try {
    $currentSession = Get-Content $SessionFile -Raw | ConvertFrom-Json
    if ($currentSession.session_id -eq $sessionId) {
      Remove-Item $SessionFile -Force -ErrorAction SilentlyContinue
    }
  }
  catch {
    # Leave an unreadable session file for the next launcher to diagnose as stale.
  }
}

if ((-not $FrontendOnly) -and (-not (Test-Path $PythonExe))) {
  throw "Backend virtual environment not found. Run .\scripts\setup.ps1 first."
}

if ((-not $BackendOnly) -and (-not (Test-Path (Join-Path $FrontendDir "node_modules")))) {
  throw "Frontend dependencies not found. Run .\scripts\setup.ps1 first."
}

if ($IsManagedSession) {
  New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
  if (Test-Path $SessionFile) {
    $existingSession = $null
    try {
      $existingSession = Get-Content $SessionFile -Raw | ConvertFrom-Json
    }
    catch {
      Remove-Item $SessionFile -Force -ErrorAction SilentlyContinue
    }

    if ($null -ne $existingSession) {
      $existingController = Get-Process `
        -Id ([int]$existingSession.controller_pid) `
        -ErrorAction SilentlyContinue
      if ($null -ne $existingController) {
        throw "A managed Value Investment session is already running (PID $($existingSession.controller_pid))."
      }
      Remove-Item $SessionFile -Force -ErrorAction SilentlyContinue
    }
  }

  $sessionId = [guid]::NewGuid().ToString("N")
  $stopRequestFile = Join-Path $RuntimeDir "stop-$sessionId.request"
  Remove-Item $stopRequestFile -Force -ErrorAction SilentlyContinue
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

$previousEnvironment = @{
  VITE_BACKEND_PORT = $env:VITE_BACKEND_PORT
  VITE_API_BASE_URL = $env:VITE_API_BASE_URL
  VITE_LOCAL_CONTROL_TOKEN = $env:VITE_LOCAL_CONTROL_TOKEN
  VALUE_INVESTMENT_LOCAL_APP_CONTROL_ENABLED = $env:VALUE_INVESTMENT_LOCAL_APP_CONTROL_ENABLED
  VALUE_INVESTMENT_LOCAL_CONTROL_TOKEN = $env:VALUE_INVESTMENT_LOCAL_CONTROL_TOKEN
  VALUE_INVESTMENT_RUNTIME_DIRECTORY = $env:VALUE_INVESTMENT_RUNTIME_DIRECTORY
  VALUE_INVESTMENT_STOP_REQUEST_FILE = $env:VALUE_INVESTMENT_STOP_REQUEST_FILE
}

try {
  $env:VITE_BACKEND_PORT = "$BackendPort"
  $env:VITE_API_BASE_URL = "/api"

  if ($IsManagedSession) {
    $tokenBytes = New-Object byte[] 32
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
      $random.GetBytes($tokenBytes)
    }
    finally {
      $random.Dispose()
    }
    $controlToken = [Convert]::ToBase64String($tokenBytes)
    $env:VITE_LOCAL_CONTROL_TOKEN = $controlToken
    $env:VALUE_INVESTMENT_LOCAL_APP_CONTROL_ENABLED = "true"
    $env:VALUE_INVESTMENT_LOCAL_CONTROL_TOKEN = $controlToken
    $env:VALUE_INVESTMENT_RUNTIME_DIRECTORY = $RuntimeDir
    $env:VALUE_INVESTMENT_STOP_REQUEST_FILE = $stopRequestFile
  }

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

  if (-not $BackendOnly) {
    $frontendProcess = Start-Process `
      -FilePath "npm.cmd" `
      -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", $FrontendPort) `
      -WorkingDirectory $FrontendDir `
      -WindowStyle Hidden `
      -PassThru `
      -RedirectStandardOutput $frontendStdOutLog `
      -RedirectStandardError $frontendStdErrLog
  }

  if ($IsManagedSession) {
    $session = [ordered]@{
      version = 1
      session_id = $sessionId
      project_root = $Root
      controller_pid = $PID
      backend_pid = $backendProcess.Id
      frontend_pid = $frontendProcess.Id
      backend_port = $BackendPort
      frontend_port = $FrontendPort
      backend_url = "http://127.0.0.1:$BackendPort"
      frontend_url = "http://127.0.0.1:$FrontendPort"
      stop_request_file = $stopRequestFile
      started_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $temporarySessionFile = "$SessionFile.tmp-$sessionId"
    $session | ConvertTo-Json | Set-Content -Path $temporarySessionFile -Encoding UTF8
    Move-Item -Path $temporarySessionFile -Destination $SessionFile -Force
  }
}
catch {
  if ($null -ne $frontendProcess -and (-not $frontendProcess.HasExited)) {
    Stop-ProcessTree -TargetProcessId $frontendProcess.Id
  }
  if ($null -ne $backendProcess -and (-not $backendProcess.HasExited)) {
    Stop-ProcessTree -TargetProcessId $backendProcess.Id
  }
  if ($stopRequestFile) {
    Remove-Item $stopRequestFile -Force -ErrorAction SilentlyContinue
  }
  Remove-CurrentSessionFile
  throw
}
finally {
  foreach ($name in $previousEnvironment.Keys) {
    Restore-EnvironmentValue -Name $name -Value $previousEnvironment[$name]
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
    if ($IsManagedSession -and (Test-Path $stopRequestFile)) {
      Write-Host "Local shutdown requested."
      Start-Sleep -Milliseconds 900
      break
    }

    if ((-not $FrontendOnly) -and $backendProcess.HasExited) {
      throw "Backend process exited with code $($backendProcess.ExitCode). Check $backendStdOutLog and $backendStdErrLog."
    }

    if ((-not $BackendOnly) -and $frontendProcess.HasExited) {
      throw "Frontend process exited with code $($frontendProcess.ExitCode). Check $frontendStdOutLog and $frontendStdErrLog."
    }

    Start-Sleep -Milliseconds 500
  }
}
finally {
  if ($null -ne $frontendProcess -and (-not $frontendProcess.HasExited)) {
    Stop-ProcessTree -TargetProcessId $frontendProcess.Id
  }

  if ($null -ne $backendProcess -and (-not $backendProcess.HasExited)) {
    Stop-ProcessTree -TargetProcessId $backendProcess.Id
  }

  if ($stopRequestFile) {
    Remove-Item $stopRequestFile -Force -ErrorAction SilentlyContinue
  }
  Remove-CurrentSessionFile
}

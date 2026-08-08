param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
  throw "Backend virtual environment not found. Run .\scripts\setup.ps1 first."
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
  throw "Frontend dependencies not found. Run .\scripts\setup.ps1 first."
}

$backendJob = Start-Job -Name "value-investment-backend" -ScriptBlock {
  param($BackendDir, $BackendPort)
  Set-Location $BackendDir
  & .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port $BackendPort
} -ArgumentList $BackendDir, $BackendPort

$frontendJob = Start-Job -Name "value-investment-frontend" -ScriptBlock {
  param($FrontendDir, $FrontendPort)
  Set-Location $FrontendDir
  & npm run dev -- --host 127.0.0.1 --port $FrontendPort
} -ArgumentList $FrontendDir, $FrontendPort

Write-Host "Backend:  http://127.0.0.1:$BackendPort"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host "Press Ctrl+C to stop."

try {
  while ($true) {
    Receive-Job -Job $backendJob, $frontendJob
    Start-Sleep -Seconds 2
  }
}
finally {
  Stop-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
  Remove-Job -Job $backendJob, $frontendJob -Force -ErrorAction SilentlyContinue
}


$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$VenvDir = Join-Path $BackendDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvDir)) {
  python -m venv $VenvDir
}

$RequirementsPath = Join-Path $BackendDir "requirements-dev.txt"
& $PythonExe -m pip --disable-pip-version-check install -r $RequirementsPath
if (($LASTEXITCODE -ne 0) -and (-not $env:PIP_INDEX_URL)) {
  Write-Warning "Default PyPI install failed. Retrying with Tsinghua PyPI mirror."
  & $PythonExe -m pip --disable-pip-version-check install -r $RequirementsPath -i "https://pypi.tuna.tsinghua.edu.cn/simple"
}

if ($LASTEXITCODE -ne 0) {
  throw "Python dependency installation failed."
}

Push-Location $FrontendDir
npm install
if ($LASTEXITCODE -ne 0) {
  Pop-Location
  throw "Frontend dependency installation failed."
}
Pop-Location

Write-Host "Setup complete."

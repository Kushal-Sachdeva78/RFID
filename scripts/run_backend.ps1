# Set up .venv and run the RFID backend API server on Windows PowerShell.
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RepoRoot "rfid_system\backend"
$VenvDir = Join-Path $BackendDir ".venv"

Set-Location $BackendDir

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment in $VenvDir ..."
    python -m venv $VenvDir
}

$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    & $ActivateScript
}

Write-Host "Installing requirements ..."
pip install -r requirements.txt -r requirements-dev.txt

Write-Host "Starting backend server on http://127.0.0.1:8000 ..."
uvicorn main:app --reload

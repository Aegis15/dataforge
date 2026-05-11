Param(
    [switch]$All
)

$ErrorActionPreference = "Stop"

# Create venv if missing
if (-Not (Test-Path .\.venv)) {
    py -3.12 -m venv .venv
}

# Activate
$venvActivate = ".\.venv\Scripts\Activate.ps1"
if (-Not (Test-Path $venvActivate)) {
    throw "Virtual environment activation script not found: $venvActivate"
}
. $venvActivate

python -m pip install --upgrade pip

if ($All) {
    python -m pip install -e ".[all]"
} else {
    python -m pip install -e ".[dev]"
    if (Test-Path "playground/api/requirements.txt") {
        python -m pip install -r "playground/api/requirements.txt"
    }
}

Write-Host "DataForge setup complete." -ForegroundColor Green

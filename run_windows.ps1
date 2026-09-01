$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Environnement absent. Lancez d'abord : py -3 -m venv .venv puis .venv\Scripts\python.exe -m pip install -r requirements.txt"
}

& ".venv\Scripts\python.exe" "run.py" @args
exit $LASTEXITCODE

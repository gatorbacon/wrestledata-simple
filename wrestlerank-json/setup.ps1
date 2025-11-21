# PowerShell script to set up WrestleRank
Write-Host "Setting up WrestleRank development environment..."

# Check if virtual environment is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "ERROR: Virtual environment not activated!" -ForegroundColor Red
    Write-Host "Please run: .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "Then run this script again."
    exit 1
}

Write-Host "Installing the package in development mode..."
pip install -e .

Write-Host "Creating database..."
python -m wrestlerank.cli init

Write-Host "Setup complete! You can now use the wrestlerank command."
Write-Host "Try: python -m wrestlerank.cli version" 
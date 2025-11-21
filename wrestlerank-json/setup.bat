@echo off
echo Setting up WrestleRank development environment...

REM Check if virtual environment is activated
if "%VIRTUAL_ENV%"=="" (
    echo ERROR: Virtual environment not activated!
    echo Please run: call venv\Scripts\activate.bat
    echo Then run this script again.
    exit /b 1
)

echo Installing the package in development mode...
pip install -e .

echo Creating database...
python -m wrestlerank.cli init

echo Setup complete! You can now use the wrestlerank command.
echo Try: python -m wrestlerank.cli version 
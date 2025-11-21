@echo off
echo Creating fresh virtual environment...

REM Remove old venv if it exists
if exist venv rmdir /s /q venv

REM Create new virtual environment
python -m venv venv

echo Virtual environment created at: %CD%\venv

REM Activate the environment and install dependencies
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install click requests beautifulsoup4 tqdm

echo Dependencies installed successfully!
echo.
echo To activate this environment, run:
echo call venv\Scripts\activate.bat
echo.
echo Then run setup.bat to install the package 
@echo off
REM Check if virtual environment is activated
if "%VIRTUAL_ENV%"=="" (
    echo ERROR: Virtual environment not activated!
    echo Please run: call venv\Scripts\activate.bat
    exit /b 1
)

python -m wrestlerank.cli %* 
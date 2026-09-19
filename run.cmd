@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist .env (
    if exist .env.example (
        echo Initializing .env from .env.example...
        copy .env.example .env >nul
        start notepad .env
        echo .env created from .env.example. Please review keys in Notepad and run run.cmd again.
        exit /b 0
    )
)

if not exist .venv (
    echo Creating .venv with py -3...
    py -3.14 -m venv .venv 2>nul || py -3 -m venv .venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment with py -3.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo Installing/verifying requirements from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Error: Failed to install requirements.
    pause
    exit /b 1
)

echo Starting Streamlit application...
streamlit run app.py

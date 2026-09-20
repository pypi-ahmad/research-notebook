@echo off
setlocal
cd /d "%~dp0"

if not exist .env (
    copy .env.example .env >nul
    start "" notepad.exe .env
    exit /b 0
)

if not exist .venv (
    py -3 -m venv .venv || exit /b 1
)

.venv\Scripts\pip install -r requirements.txt || exit /b 1

set "STREAMLIT_PORT=8591"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%STREAMLIT_PORT% .*LISTENING"') do (
    echo Stopping the process listening on port %STREAMLIT_PORT% (PID %%P)...
    taskkill /F /PID %%P >nul 2>&1
)

.venv\Scripts\streamlit run app.py --server.port=%STREAMLIT_PORT%

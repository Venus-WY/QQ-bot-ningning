@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] venv not found. Please install deps first per README.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -X utf8 run_reload.py
pause

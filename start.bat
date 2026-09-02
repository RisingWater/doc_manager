@echo off
cd /d %~dp0
if not exist venv\Scripts\python.exe (
    echo [ERROR] venv not found.
    echo Run: python -m venv venv
    echo      venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
if not exist src\frontend\dist\index.html (
    echo [WARN] Frontend not built. Run: cd src\frontend ^&^& bun install ^&^& bun run build
)
echo Starting server at http://127.0.0.1:8000
venv\Scripts\python.exe -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000
pause

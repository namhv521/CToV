@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2)" >nul 2>&1
if not errorlevel 1 (
  start "" "http://127.0.0.1:8765"
  exit /b
)
".venv\Scripts\python.exe" -c "import fastapi,uvicorn,PIL,httpx,multipart,gtts,edge_tts,playwright" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)
start "" "http://127.0.0.1:8765"
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :error
exit /b
:error
echo Khong khoi dong duoc. Xem README.md de cai Python, dependencies va FFmpeg.
pause

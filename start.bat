@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import fastapi,uvicorn,PIL,httpx,multipart,playwright" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 goto :error
exit /b
:error
echo Khong khoi dong duoc CommentCut Studio. Xem README.md de cai Python, dependencies va FFmpeg.
pause

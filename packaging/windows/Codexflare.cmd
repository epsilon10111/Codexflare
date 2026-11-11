@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import webview" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements-windows.txt
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" tools\editor.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Codexflare could not start. Install Python 3.13 x64 and Microsoft Edge WebView2, then retry.
pause
exit /b 1

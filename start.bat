@echo off
REM Double-click to start the Quality-of-Life Tracker on Windows.
REM Needs Python 3.11 or newer from https://www.python.org/downloads/
REM (tick "Add python.exe to PATH" in the installer).
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
if not exist ".venv\Scripts\python.exe" (
  echo Setting up for the first time. This takes a minute...
  %PY% -m venv .venv || goto :nopython
  ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :fail
)
echo Starting. Your browser will open. Close this window to stop the app.
".venv\Scripts\python.exe" run.py
goto :end
:nopython
echo.
echo Python was not found. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then double-click this file again.
pause
goto :end
:fail
echo.
echo Something went wrong installing the app's parts. Check your internet connection and try again.
pause
:end

#!/bin/bash
# Double-click to start the Quality-of-Life Tracker on a Mac.
# Needs Python 3.11 or newer from https://www.python.org/downloads/
# If macOS says the file can't be opened, right-click it and choose Open once.
cd "$(dirname "$0")"
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "Python was not found. Install it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close."
  exit 1
fi
if [ ! -x ".venv/bin/python" ]; then
  echo "Setting up for the first time. This takes a minute..."
  "$PY" -m venv .venv && .venv/bin/python -m pip install --quiet --upgrade pip && \
    .venv/bin/python -m pip install --quiet -r requirements.txt || {
    echo "Something went wrong installing the app's parts. Check your internet connection and try again."
    read -r -p "Press Enter to close."; exit 1; }
fi
echo "Starting. Your browser will open. Close this window (or press Ctrl+C) to stop the app."
exec .venv/bin/python run.py

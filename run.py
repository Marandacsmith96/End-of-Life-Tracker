"""Start the Pet Quality-of-Life Tracker on your own computer.

Usage:
    python run.py

Then open http://127.0.0.1:5000 in a browser. Everything stays on this
machine; no internet connection is needed.
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

"""Which build is this? The packaging workflow writes app/BUILD with a date
and commit; from source there is no file and the app reports "source".
"""
from pathlib import Path

_STAMP = Path(__file__).with_name("BUILD")


def build_label() -> str:
    try:
        text = _STAMP.read_text(encoding="utf-8").strip()
    except OSError:
        return "running from source"
    return f"build {text}" if text else "running from source"

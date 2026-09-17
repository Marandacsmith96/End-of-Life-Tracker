# PyInstaller build recipe. Run from the project root:
#     pyinstaller pet_qol.spec
# The result is dist/PetQoLTracker/ with a PetQoLTracker executable inside.
# Data (database, photos, secret key) is kept in a data/ folder next to it.
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("app/templates", "app/templates"),
        ("app/static", "app/static"),
        ("app/schema.sql", "app"),
    ],
    hiddenimports=["matplotlib.backends.backend_agg"] + collect_submodules("reportlab"),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "IPython", "notebook", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PetQoLTracker",
    debug=False,
    strip=False,
    upx=False,
    console=True,   # keep a console so errors are visible; set False once happy
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="PetQoLTracker")

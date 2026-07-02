# -*- mode: python ; coding: utf-8 -*-
"""
Fichier de configuration PyInstaller pour IntermitDoc.
Exécuter : python -m PyInstaller intermitdoc.spec
"""
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# Collecter pymupdf et fitz en entier (DLLs + données)
datas_pymupdf, binaries_pymupdf, hiddenimports_pymupdf = collect_all('pymupdf')
datas_fitz, binaries_fitz, hiddenimports_fitz = collect_all('fitz')
datas_anthropic, binaries_anthropic, hiddenimports_anthropic = collect_all('anthropic')
datas_tkcal, binaries_tkcal, hiddenimports_tkcal = collect_all('tkcalendar')
datas_babel, binaries_babel, hiddenimports_babel = collect_all('babel')
datas_svttk, binaries_svttk, hiddenimports_svttk = collect_all('sv_ttk')

datas = datas_pymupdf + datas_fitz + datas_anthropic + datas_tkcal + datas_babel + datas_svttk
binaries = binaries_pymupdf + binaries_fitz + binaries_anthropic + binaries_tkcal + binaries_babel + binaries_svttk
hidden_imports = (
    hiddenimports_pymupdf
    + hiddenimports_fitz
    + hiddenimports_anthropic
    + hiddenimports_tkcal
    + hiddenimports_babel
    + hiddenimports_svttk
    + [
        'PIL._tkinter_finder', 'PIL.Image', 'PIL.ImageTk',
        'pytesseract', 'tkinter', 'tkinter.ttk', 'tkinter.filedialog',
        'tkinter.messagebox', 'tkinter.scrolledtext', 'tkinter.simpledialog',
        'unicodedata', 'json', 'threading', 'pathlib', 'io', 're', 'webbrowser',
        'tkcalendar', 'babel', 'babel.numbers',
        'sv_ttk', 'theme',
    ]
)

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'scipy', 'pandas', 'jupyter', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='IntermitDoc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

# COLLECT crée un dossier avec l'exe + toutes les DLLs
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IntermitDoc',
)

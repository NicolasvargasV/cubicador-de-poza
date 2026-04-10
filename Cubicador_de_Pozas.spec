# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules

# ── Datos estáticos ───────────────────────────────────────────────────────────
datas = [
    ('img', 'img'),
    # apiKey y projectId están embebidos en firebase_auth.py — no se necesita archivo externo
]

# ── rasterio ──────────────────────────────────────────────────────────────────
binaries = []
hiddenimports = []
datas      += collect_data_files('rasterio')
binaries   += collect_dynamic_libs('rasterio')
hiddenimports += collect_submodules('rasterio')

# ── firebase_admin + google-cloud ─────────────────────────────────────────────
hiddenimports += collect_submodules('firebase_admin')
hiddenimports += collect_submodules('google.cloud.firestore')
hiddenimports += collect_submodules('google.api_core')
hiddenimports += collect_submodules('google.auth')
datas += collect_data_files('firebase_admin')
datas += collect_data_files('google.cloud.firestore')

# ── Google Sheets / gspread ───────────────────────────────────────────────────
hiddenimports += collect_submodules('googleapiclient')
hiddenimports += collect_submodules('google_auth_httplib2')

# ── PySide6 ───────────────────────────────────────────────────────────────────
hiddenimports += ['PySide6.QtSvg', 'PySide6.QtPrintSupport']

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthooks\\rth_rasterio.py'],
    # Excluir módulos de desarrollo que no deben ir en el bundle
    excludes=['pytest', 'IPython', 'jupyter', 'notebook', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Cubicador_de_Pozas',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                  # Sin ventana de consola en producción
    icon='img\\app.ico',            # Ícono de la aplicación
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

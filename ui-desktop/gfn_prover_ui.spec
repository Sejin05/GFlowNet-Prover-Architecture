# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller Standalone Native Desktop Executable Configuration for GFlowNet-Prover UI."""

from pathlib import Path

block_cipher = None
project_dir = Path(SPECPATH)

a = Analysis(
    [str(project_dir / "src" / "main.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        (str(project_dir / "resources" / "styles" / "dark_theme.qss"), "resources/styles"),
        (str(project_dir / "resources" / "icons"), "resources/icons"),
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtNetwork",
        "pyqtgraph",
        "qasync",
        "tomli",
        "tomli_w",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="gfn-prover-ui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

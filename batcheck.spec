# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller pour batcheck.

Produit un executable autonome (un seul fichier) qui embarque :
  - le launcher + le serveur local
  - le package batcheck (modules host / ios / android)
  - le dossier web/ (l'interface)
  - pymobiledevice3 en entier, pour que l'iPhone soit lu des l'installation

adb (Android) n'est PAS embarque : c'est un binaire Google separe.
Android necessitera donc adb installe a part (l'UI le signale clairement).

Build :  pyinstaller batcheck.spec
Sortie :  dist/batcheck  (ou dist/batcheck.exe sous Windows)
"""

from PyInstaller.utils.hooks import collect_all

datas = [("web", "web")]
binaries = []
hiddenimports = []

# On embarque pymobiledevice3 et ses dependances de maniere exhaustive.
# collect_all attrape le code, les donnees et les imports caches.
for pkg in ("pymobiledevice3", "construct", "cryptography"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        # Si un paquet optionnel manque a la compilation, on continue :
        # le binaire marchera quand meme pour host + android.
        pass

block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    name="batcheck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # garde une fenetre console : utile pour voir l'URL et les logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Sur macOS, on emballe aussi en .app (necessaire pour produire un .dmg).
# PyInstaller ignore ce bloc sur les autres OS.
import sys as _sys
if _sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="batcheck.app",
        icon=None,
        bundle_identifier="game.popcorn.batcheck",
        info_plist={
            "CFBundleName": "batcheck",
            "CFBundleDisplayName": "batcheck",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            # batcheck ouvre juste un serveur local + navigateur : pas d'UI native.
            "LSBackgroundOnly": False,
        },
    )

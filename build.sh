#!/usr/bin/env bash
#
# Build local de batcheck en client autonome.
#   - Linux  -> dist/batcheck            (binaire)
#   - macOS  -> dist/batcheck.app + batcheck-macos.dmg
#
# Prerequis : Python 3.9+ et internet (pour installer les outils de build).
# Usage : ./build.sh
set -e
cd "$(dirname "$0")"

PY=python3
command -v $PY >/dev/null 2>&1 || PY=python

echo "==> environnement de build isole"
$PY -m venv .build-venv
# shellcheck disable=SC1091
source .build-venv/bin/activate

echo "==> installation des outils"
pip install --upgrade pip >/dev/null
pip install pyinstaller pymobiledevice3 >/dev/null

echo "==> compilation (PyInstaller)"
pyinstaller --noconfirm --clean batcheck.spec

OS="$(uname -s)"
if [ "$OS" = "Darwin" ]; then
  echo "==> creation du .dmg macOS"
  APP="dist/batcheck.app"
  DMG="dist/batcheck-macos.dmg"
  rm -f "$DMG"
  # Dossier de montage temporaire avec un lien vers /Applications
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "batcheck" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
  rm -rf "$STAGE"
  echo "==> OK : $DMG"
  echo "    (non signe : au 1er lancement, clic droit > Ouvrir pour passer Gatekeeper)"
else
  echo "==> OK : dist/batcheck"
fi

deactivate
echo "==> termine."

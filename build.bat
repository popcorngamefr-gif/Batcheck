@echo off
REM Build local de batcheck en client Windows autonome -> dist\batcheck.exe
REM Prerequis : Python 3.9+ et internet. Usage : double-clic ou build.bat
cd /d "%~dp0"

echo ==^> environnement de build isole
python -m venv .build-venv
call .build-venv\Scripts\activate.bat

echo ==^> installation des outils
python -m pip install --upgrade pip >nul
pip install pyinstaller pymobiledevice3 >nul

echo ==^> compilation (PyInstaller)
pyinstaller --noconfirm --clean batcheck.spec

echo ==^> OK : dist\batcheck.exe
call deactivate
pause

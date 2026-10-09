@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .build-venv
if errorlevel 1 exit /b 1
.build-venv\Scripts\python.exe -m pip install --disable-pip-version-check pyinstaller==6.16.0
if errorlevel 1 exit /b 1
.build-venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin --name WinImage-Studio desktop.py
if errorlevel 1 exit /b 1
echo Eseguibile creato: dist\WinImage-Studio.exe

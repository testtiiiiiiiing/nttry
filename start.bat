@echo off
cd /d "%~dp0"
py -3 -m winimage
if errorlevel 1 pause

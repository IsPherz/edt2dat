@echo off
REM Keep this folder named "edt2dat". Bat cds to the parent so "python -m edt2dat" works.
cd /d "%~dp0.."
python -m edt2dat %*
if errorlevel 1 pause

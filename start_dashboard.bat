@echo off
cd /d "%~dp0"
title MOTOSIRA - Dashboard - open http://localhost:5000
if not exist venv\Scripts\activate.bat goto nosetup
call venv\Scripts\activate.bat
python dashboard\app.py
pause
exit /b 0
:nosetup
echo Run setup_pc.bat first.
pause
exit /b 1

@echo off
cd /d "%~dp0"
title MOTOSIRA - Connection check
if not exist venv\Scripts\activate.bat goto nosetup
call venv\Scripts\activate.bat
python tools\check_connections.py
pause
exit /b 0
:nosetup
echo Run setup_pc.bat first.
pause
exit /b 1

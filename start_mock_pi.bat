@echo off
cd /d "%~dp0"
title MOTOSIRA - Simulated device (DEMO mode)
if not exist venv\Scripts\activate.bat goto nosetup
call venv\Scripts\activate.bat
python pi_side\mock_pi.py
pause
exit /b 0
:nosetup
echo Run setup_pc.bat first.
pause
exit /b 1

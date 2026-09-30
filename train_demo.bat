@echo off
cd /d "%~dp0"
title MOTOSIRA - Train DEMO model (simulated data)
if not exist venv\Scripts\activate.bat goto nosetup
call venv\Scripts\activate.bat
python tools\generate_mock_dataset.py && python model\train.py --mode mock
pause
exit /b 0
:nosetup
echo Run setup_pc.bat first.
pause
exit /b 1

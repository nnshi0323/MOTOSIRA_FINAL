@echo off
cd /d "%~dp0"
title MOTOSIRA - Train REAL model
if not exist venv\Scripts\activate.bat goto nosetup
call venv\Scripts\activate.bat
python tools\prepare_dataset.py && python tools\dataset_status.py && python model\train.py --mode real
pause
exit /b 0
:nosetup
echo Run setup_pc.bat first.
pause
exit /b 1

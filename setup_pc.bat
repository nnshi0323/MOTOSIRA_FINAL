@echo off
setlocal
cd /d "%~dp0"
title MOTOSIRA - PC setup
echo === MOTOSIRA PC setup (fresh environment) ===
set "PY="
py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info[:2] in [(3,12),(3,13)] else 1)" >nul 2>&1 && set "PY=python"
if not defined PY goto nopython
echo Using: %PY%
%PY% --version
if exist venv echo Removing old venv...
if exist venv rmdir /s /q venv
%PY% -m venv venv || goto fail
call venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto fail
echo Installing packages - prebuilt only, nothing compiles...
python -m pip install --only-binary=:all: -r requirements-pc.txt || goto fail
python tools\make_env.py || goto fail
echo.
echo Preparing the REAL dataset from raw_data ...
python tools\prepare_dataset.py
if not exist model\trained\mock\model.joblib goto trainmock
goto status
:trainmock
echo Building the DEMO model - simulated dataset...
python tools\generate_mock_dataset.py || goto fail
python model\train.py --mode mock || goto fail
:status
python tools\dataset_status.py
echo.
echo === Setup complete ===
echo Next: right-click start_broker.bat - Run as administrator, then start_dashboard.bat
pause
exit /b 0
:nopython
echo Python 3.12 or 3.13 was not found.
echo Install Python 3.12 from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
echo Python 3.14 is NOT supported yet - some packages have no Windows builds for it.
pause
exit /b 1
:fail
echo.
echo SETUP FAILED - read the error above. Check the internet connection and run setup_pc.bat again.
pause
exit /b 1

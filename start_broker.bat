@echo off
cd /d "%~dp0"
title MOTOSIRA - MQTT broker (keep open)
net session >nul 2>&1
if errorlevel 1 goto needadmin
set "MOSQ=%ProgramFiles%\mosquitto\mosquitto.exe"
if not exist "%MOSQ%" set "MOSQ=%ProgramFiles(x86)%\mosquitto\mosquitto.exe"
if not exist "%MOSQ%" goto nomosq
rem The Windows service only listens on localhost - stop it and run the network config instead.
net stop mosquitto >nul 2>&1
netsh advfirewall firewall show rule name="MOTOSIRA MQTT" >nul 2>&1 || netsh advfirewall firewall add rule name="MOTOSIRA MQTT" dir=in action=allow protocol=TCP localport=1883 profile=any >nul
netsh advfirewall firewall show rule name="MOTOSIRA Dashboard" >nul 2>&1 || netsh advfirewall firewall add rule name="MOTOSIRA Dashboard" dir=in action=allow protocol=TCP localport=5000 profile=any >nul
echo.
echo  ============================================================
echo   This laptop's IP address - on the Pi run:  ./run_pi.sh ip ADDRESS
ipconfig | findstr /R /C:"IPv4"
echo  ============================================================
echo  Broker running. KEEP THIS WINDOW OPEN. Ctrl+C to stop.
echo.
"%MOSQ%" -c "%~dp0mosquitto\motosira.conf" -v
pause
exit /b 0
:needadmin
echo Right-click start_broker.bat and choose "Run as administrator".
pause
exit /b 1
:nomosq
echo Mosquitto is not installed. Download the Windows 64-bit installer from
echo https://mosquitto.org/download/  - install with default options, then run this again.
pause
exit /b 1

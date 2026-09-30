# MOTOSIRA — Reset from zero (PC and Raspberry Pi)

Goal: remove every old copy/setting so nothing from earlier attempts interferes.
**Old folders are renamed, not deleted, until the new setup works** — recordings are never lost.

## PC (Windows)
1. Close every old MOTOSIRA window (dashboard, broker, mock Pi, VS Code terminals). Ctrl+C in each.
2. PowerShell **as administrator**:
   ```powershell
   net stop mosquitto
   sc config mosquitto start= demand
   ```
   (the service only listens on localhost; `start_broker.bat` runs the right configuration instead)
3. Rename old project folders (they contain their own venvs — nothing else was installed globally):
   ```powershell
   cd "C:\Users\Kyle Miro\Downloads"
   Rename-Item MOTOSIRA_v2 OLD_MOTOSIRA_v2
   Rename-Item MOTOSIRA_v2_prototype OLD_MOTOSIRA_v2_prototype
   ```
   Copy any recordings you want to keep from the old `raw_data\` folders (or Google Drive).
4. Unzip the new package to `C:\MOTOSIRA`, put your recordings in `C:\MOTOSIRA\raw_data\<class>\<motorcycle>\`.
5. Run `setup_pc.bat` (it always creates a brand-new venv). Continue with START_HERE.md section B.

## Raspberry Pi
1. Stop old programs: Ctrl+C in their terminals, or
   ```bash
   pkill -f pi_capture.py; pkill -f pi_display.py; pkill -f pi_app.py
   ```
2. Keep old recordings (if any), then rename the old project:
   ```bash
   cd /home/motosira_thesis
   ls                                   # see the old folder names
   mv MOTOSIRA_V2_PROTOTYPE OLD_MOTOSIRA_V2_PROTOTYPE
   ```
3. Remove leftovers from earlier `pip install --break-system-packages` attempts (outside any venv):
   ```bash
   python3 -m pip list --user                          # shows them (empty = nothing to do)
   python3 -m pip freeze --user | xargs -r python3 -m pip uninstall -y --break-system-packages
   python3 -m pip cache purge
   ```
4. Get the new code into `/home/motosira_thesis/MOTOSIRA`:
   ```bash
   git clone https://github.com/<you>/<new-repo>.git /home/motosira_thesis/MOTOSIRA
   cd /home/motosira_thesis/MOTOSIRA
   bash setup_pi.sh
   ```
   `setup_pi.sh` also repairs `/boot/firmware/config.txt`: it disables the old invalid
   `simple-audio-card ... INMP441` line, removes duplicate i2s lines and adds
   `dtparam=i2s=on` + `dtoverlay=googlevoicehat-soundcard` once. The LCD lines are untouched and a
   backup is saved next to the file (`config.txt.motosira-<date>`).
5. `sudo reboot`, then `arecord -l` (card **sndrpigooglevoi**) and `./run_pi.sh check`.

When the new setup works, delete the OLD_ folders.

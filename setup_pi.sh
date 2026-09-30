#!/usr/bin/env bash
# MOTOSIRA — Raspberry Pi 4 setup FROM ZERO (safe to re-run).
#   bash setup_pi.sh
# 1. system packages   2. brand-new venv with verified prebuilt packages (nothing compiles)
# 3. repairs /boot/firmware/config.txt for the INMP441 (LCD lines untouched, backup kept)
# 4. asks for the dashboard PC's IP   5. desktop shortcut for the LCD
set -e
cd "$(dirname "$0")"
PROJECT="$(pwd)"
echo "=== MOTOSIRA Pi setup in $PROJECT ==="

ARCH="$(uname -m)"
PYV="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "System: $ARCH, Python $PYV"
if [ "$ARCH" != "aarch64" ]; then
  echo "WARNING: this setup is verified for 64-bit Raspberry Pi OS (aarch64). You have $ARCH."
fi

echo; echo "== 1/5 System packages =="
sudo apt-get update
sudo apt-get install -y python3-venv python3-tk libportaudio2 libsndfile1 alsa-utils mosquitto-clients git

echo; echo "== 2/5 Fresh Python environment =="
rm -rf venv
python3 -m venv venv
# PIP_CONFIG_FILE=/dev/null ignores /etc/pip.conf (piwheels) so only verified PyPI wheels are used
export PIP_CONFIG_FILE=/dev/null
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install --only-binary=:all: --index-url https://pypi.org/simple -r requirements-pi.txt
venv/bin/python -c "import numpy, scipy, librosa, sklearn, sounddevice, paho.mqtt, tkinter; print('OK: numpy', numpy.__version__, '| scipy', scipy.__version__, '| librosa', librosa.__version__, '| scikit-learn', sklearn.__version__)"

echo; echo "== 3/5 INMP441 overlay in config.txt =="
CFG=/boot/firmware/config.txt; [ -f "$CFG" ] || CFG=/boot/config.txt
BEFORE="$(md5sum "$CFG" | cut -d' ' -f1)"
sudo venv/bin/python tools/fix_boot_config.py
AFTER="$(md5sum "$CFG" | cut -d' ' -f1)"

echo; echo "== 4/5 Dashboard PC address =="
echo "On the laptop, start_broker.bat prints its IPv4 address (e.g. 192.168.43.25)."
CURRENT="$(grep -s '^MOTOSIRA_BROKER=' .env | cut -d= -f2 || true)"
while true; do
  read -r -p "Laptop IP [${CURRENT:-press ENTER to set later}]: " IP
  IP="${IP:-$CURRENT}"
  if [ -z "$IP" ]; then venv/bin/python tools/make_env.py; echo "Set it later with: ./run_pi.sh ip <laptop IP>"; break; fi
  if venv/bin/python tools/make_env.py --broker "$IP"; then break; fi
done

echo; echo "== 5/5 Shortcuts =="
chmod +x run_pi.sh setup_pi.sh
mkdir -p "$HOME/Desktop"
cat > "$HOME/Desktop/MOTOSIRA.desktop" << DESK
[Desktop Entry]
Type=Application
Name=MOTOSIRA
Comment=Start the MOTOSIRA diagnostic screen
Exec=$PROJECT/run_pi.sh
Terminal=false
Icon=audio-input-microphone
DESK
chmod +x "$HOME/Desktop/MOTOSIRA.desktop"

echo
echo "=== Setup complete ==="
if [ "$BEFORE" != "$AFTER" ]; then
  echo "config.txt was changed -> REBOOT NOW:   sudo reboot"
  echo "After reboot:  arecord -l   (look for 'sndrpigooglevoi'),  then  ./run_pi.sh mictest"
else
  echo "config.txt already correct. Next:  ./run_pi.sh mictest   then   ./run_pi.sh check"
fi
echo "Start the LCD app:  ./run_pi.sh     (or double-tap MOTOSIRA on the desktop)"

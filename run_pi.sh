#!/usr/bin/env bash
# MOTOSIRA — run on the Raspberry Pi
#   ./run_pi.sh                 LCD app, fullscreen (touch START)
#   ./run_pi.sh window          LCD app in a normal window
#   ./run_pi.sh console         no screen (e.g. over SSH): ENTER = start
#   ./run_pi.sh mictest         test the INMP441 (5 s recording + levels)
#   ./run_pi.sh check           check packages, broker, mic, models
#   ./run_pi.sh ip <laptop IP>  set the dashboard PC address
#   ./run_pi.sh collect --class knocking [--seconds 30 --sessions 5]   record training data
#   ./run_pi.sh config          repair config.txt for the INMP441 (then reboot)
#   ./run_pi.sh update          git pull + reinstall packages
cd "$(dirname "$0")"
if [ ! -x venv/bin/python ]; then echo "Run setup first:  bash setup_pi.sh"; exit 1; fi
PY=venv/bin/python
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
MODE="${1:-app}"; [ $# -gt 0 ] && shift
case "$MODE" in
  app)      exec $PY pi_side/pi_app.py "$@" ;;
  window)   exec $PY pi_side/pi_app.py --windowed "$@" ;;
  console)  exec $PY pi_side/pi_app.py --console "$@" ;;
  mictest)  exec $PY pi_side/mic_test.py ;;
  check)    exec $PY tools/check_connections.py ;;
  ip)       [ -z "$1" ] && { echo "Usage: ./run_pi.sh ip <laptop IP>"; exit 1; }; exec $PY tools/make_env.py --broker "$1" ;;
  collect)  exec $PY pi_side/collect.py "$@" ;;
  config)   exec sudo $PY tools/fix_boot_config.py ;;
  update)   git pull --ff-only && PIP_CONFIG_FILE=/dev/null $PY -m pip install --only-binary=:all: --index-url https://pypi.org/simple -r requirements-pi.txt ;;
  *)        sed -n '2,12p' "$0" ;;
esac

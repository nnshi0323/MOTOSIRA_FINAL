# MOTOSIRA — Troubleshooting

Run the checker first — it names the broken link:
PC `check_connections.bat` · Pi `./run_pi.sh check`

## Pi / microphone
| Message | Fix |
|---|---|
| `INMP441 (googlevoicehat) card not found` / `arecord -l` empty | `sudo python3 tools/fix_boot_config.py` then `sudo reboot` |
| `returns only zeros` | wiring: SD→pin 38, SCK→pin 12, WS→pin 35, VDD→pin 1 (3.3 V), L/R→GND; solder the header |
| `could not be opened ... busy` | another program uses the mic (`arecord`, browser): close it; `pkill arecord` |
| peak around −60 dBFS (very quiet) | L/R not grounded, or mic far from the engine |
| app opens on the wrong screen / not at all over SSH | run it from the Pi's own terminal, or `./run_pi.sh console` |
| `setup_pi.sh` pip error "metadata-generation-failed" | an old requirements file: `git pull`, then `bash setup_pi.sh` (it installs only prebuilt wheels) |
| `needs 64-bit Raspberry Pi OS` | reflash with Raspberry Pi OS (64-bit) |

## Network
| Symptom | Fix |
|---|---|
| Pi: `PC: OFFLINE` / check says cannot reach broker | both on the same Wi-Fi/hotspot; `./run_pi.sh ip <PC IP>`; `start_broker.bat` running as administrator |
| works at home, not at school | school Wi-Fi isolates devices → use a phone hotspot |
| PC IP changed | `start_broker.bat` prints it; update the Pi with `./run_pi.sh ip <new IP>` |
| `Port 1883 already in use` | another broker running: close it or reboot the PC |

## Dashboard / training
| Symptom | Fix |
|---|---|
| "No Raspberry Pi online" | Pi app not running, or wrong broker IP on the Pi |
| "No simulated device online" | run `start_mock_pi.bat` |
| REAL result says NOT CLASSIFIED | no REAL model yet → record ≥2 classes, run `train_real.bat` |
| train says "Only one class has data" | record at least one fault class (knocking/misfire/valve_ticking) |
| train warns "OPTIMISTIC" | each class needs ≥2 separate recordings for a proper split |
| login fails | user/password are in `.env` (`MOTOSIRA_USER`, `MOTOSIRA_PASS`) |
| `setup_pc.bat`: Python not found | install Python 3.12 64-bit, tick "Add python.exe to PATH" |

## Changing the dashboard password (before public demos)
```powershell
venv\Scripts\activate
python -c "from werkzeug.security import generate_password_hash as g; print(g('NEW-PASSWORD'))"
```
Paste the output into `.env` as `MOTOSIRA_PASS_HASH=...` and restart the dashboard.

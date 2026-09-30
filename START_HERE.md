# MOTOSIRA — START HERE
**Motorcycle Sound-based Identification & Reporting Assistant** · Team 16, Holy Angel University

```
 INMP441 ──I2S──> Raspberry Pi 4 ──MQTT (Wi-Fi/hotspot)──> Dashboard PC (Windows)
 (engine block,   record 3 s @48 kHz                        Random Forest classification
  ~30 cm)         low-pass filter + MFCC                    session database, PDF/CSV reports
                  3.5" LCD touchscreen  <──── result ─────  web dashboard (REAL / DEMO switch)
                  microSD session log
                  offline fallback (EDGE)
```

## Two modes (switch at the top of the dashboard)
| Mode | Audio | Model | Use it for |
|---|---|---|---|
| **REAL** | Raspberry Pi + INMP441 | trained on YOUR recordings (`model/training_data/`) | the actual system |
| **DEMO** | simulated device on the PC | trained on a SIMULATED dataset (`model/mock_data/`) | showing the full pipeline before enough real fault recordings exist |

Real microphone audio is only ever classified by the REAL model. DEMO results are labeled "simulated" everywhere (dashboard, LCD, PDF) — never present them as real results.

---
## A. First-time setup — PC (Windows)
Starting over? Do **docs/RESET_FROM_ZERO.md** first.
1. Install **Python 3.12 (64-bit)** from python.org — tick **"Add python.exe to PATH"**.
2. Install **Mosquitto** (Windows 64-bit) from https://mosquitto.org/download/
3. Unzip this folder to e.g. `C:\MOTOSIRA` (short path, no spaces is safest).
4. Double-click **`setup_pc.bat`** (≈5 min). It creates the venv, installs prebuilt packages, writes `.env`, builds and trains the DEMO model, and prepares your real recordings.

## B. Every time — PC
Laptop and Pi must be on the **same network**. At school use a **phone hotspot** (campus Wi-Fi usually blocks device-to-device traffic).
1. Right-click **`start_broker.bat` → Run as administrator** (keep open). It prints this PC's IP.
2. Double-click **`start_dashboard.bat`** → browser opens http://localhost:5000 · login **admin / motosira123**
3. DEMO without the Pi: double-click **`start_mock_pi.bat`**, choose **DEMO** in the dashboard, press **START DIAGNOSIS**.
4. Problems? Double-click **`check_connections.bat`**.

## C. First-time setup — Raspberry Pi 4 (64-bit OS)
1. Wire the INMP441 with the Pi **powered off** — **docs/WIRING.md**.
2. Put the code on the Pi at `/home/motosira_thesis/MOTOSIRA` (GitHub clone — section F — or copy this folder), then:
   ```bash
   cd /home/motosira_thesis/MOTOSIRA
   bash setup_pi.sh        # asks for the PC's IP (from start_broker.bat)
   sudo reboot
   ```
3. After reboot: `arecord -l` must list **sndrpigooglevoi**. Then:
   ```bash
   cd /home/motosira_thesis/MOTOSIRA
   ./run_pi.sh mictest     # 5 s test recording: tap the mic, the peak must rise
   ./run_pi.sh check       # packages, broker, microphone, models
   ./run_pi.sh             # MOTOSIRA app on the LCD (or double-tap MOTOSIRA on the desktop)
   ```

## D. Every time — Pi
```bash
cd /home/motosira_thesis/MOTOSIRA
./run_pi.sh             # app on the LCD (touch START, or START from the dashboard in REAL mode)
./run_pi.sh console     # same, over SSH without a screen
./run_pi.sh ip 192.168.x.x   # PC address changed (new network / hotspot)
```

## E. Training (details: docs/TRAINING_GUIDE.md)
```
Record  ->  raw_data/<class>/<motorcycle>/*.wav   (phone or ./run_pi.sh collect ...)
PC:     train_real.bat   (cuts 3 s clips, filters by quality, trains, saves metrics + confusion matrix)
```
The REAL model needs **at least two classes** (e.g. normal + knocking). The dashboard reloads new models automatically.
To give the Pi a copy for offline EDGE mode: commit + push on the PC, then `./run_pi.sh update` on the Pi.

## F. Put it on GitHub (new repository)
```powershell
cd C:\MOTOSIRA
git init
git add .
git status          # must NOT list .env, venv\ or .wav files
git commit -m "MOTOSIRA prototype"
git branch -M main
git remote add origin https://github.com/<you>/<new-repo>.git
git push -u origin main
```
On the Pi: `git clone https://github.com/<you>/<new-repo>.git /home/motosira_thesis/MOTOSIRA` (recordings travel via Google Drive, not Git).

## Documents
- **docs/DEFENSE_DAY.md** — Oct 3 runbook, demo script, backup plans
- **docs/WIRING.md** — INMP441 + LCD pins
- **docs/TRAINING_GUIDE.md** — how training and testing work, what to report
- **docs/ARCHITECTURE.md** — design, thesis traceability, items to disclose in the paper
- **docs/RESET_FROM_ZERO.md** — clean slate on PC and Pi
- **docs/TROUBLESHOOTING.md**

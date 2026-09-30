# MOTOSIRA — Defense Day Runbook (Oct 3 prototype defense)

## The night before
- [ ] Laptop charged + charger; Pi power supply (official 5 V 3 A); mic wired and soldered
- [ ] **Phone hotspot** ready (school Wi-Fi usually blocks laptop ↔ Pi traffic)
- [ ] Connect laptop AND Pi to the hotspot once, run `start_broker.bat`, note the laptop IP,
      then on the Pi `./run_pi.sh ip <laptop IP>` and `./run_pi.sh check` → all OK
- [ ] Run one DEMO and one REAL diagnosis end to end; open a PDF
- [ ] `train_real.bat` if you recorded new data; confusion-matrix PNG copied into the slides
- [ ] Dashboard runs without internet (it does — nothing loads from the web)

## Setup at the venue (10 min)
1. Hotspot on. Laptop and Pi join it.
2. Laptop: `start_broker.bat` (Run as administrator) → note the IPv4 address.
3. Pi: `cd /home/motosira_thesis/MOTOSIRA` → `./run_pi.sh ip <address>` (only if it changed) → `./run_pi.sh`
4. Laptop: `start_dashboard.bat` → login. Top bar must show **Broker OK** and **Pi + INMP441 OK** in REAL mode.
5. Laptop: `start_mock_pi.bat` (for the DEMO part).

## Demo script (≈6 minutes)
1. **Architecture (30 s)** — Pi records and extracts MFCC; laptop classifies, logs, reports; result back to the LCD.
2. **DEMO mode (2 min)** — "Because real fault recordings are still being collected, we first show the
   complete pipeline with a simulated device." Pick *Simulate: Knocking* → START → KNOCKING, severity 3/3.
   Repeat with Misfire. Point at: stepper, confidence, severity, latency, waveform. Open the PDF (says DEMO).
3. **REAL mode (2 min)** — switch to REAL. Mic at the engine block (or any sound source). Press START on the
   LCD. Show: live capture, signal quality GOOD/CHECK NOISE, SNR, end-to-end latency, LCD result,
   session in History, PDF. If the REAL model has only some classes, say so plainly.
4. **Training evidence (1 min)** — Model & Dataset page: split by recording, per-class metrics, confusion
   matrix, per-motorcycle accuracy, dataset progress toward 83 clips per cell.
5. **Robustness (30 s)** — optional: turn the hotspot off → Pi still answers in **EDGE** mode (needs the REAL
   model copied to the Pi) and keeps logging to microSD.

## If something fails
| Problem | Fix (fast) |
|---|---|
| Pi shows PC: OFFLINE | same hotspot? `./run_pi.sh ip <laptop IP>`; broker window open? `./run_pi.sh check` |
| Dashboard: "No Raspberry Pi online" | Pi app not running, or wrong IP (above) |
| LCD shows HARDWARE NOT READY | read the message; usually overlay/wiring → `./run_pi.sh mictest` |
| Everything network fails | Do the whole demo in DEMO mode on the laptop alone; show the Pi app with `./run_pi.sh window` + EDGE mode |
| Browser page blank | refresh; check the dashboard window for errors; restart `start_dashboard.bat` |
| Port 1883 busy | close other broker windows, or reboot the laptop |

## Honest answers for likely panel questions
- **"Is this real?"** DEMO is labeled simulated everywhere; REAL uses the INMP441 and a model trained only on
  mechanic-verified recordings. Real audio is never classified by the demo model.
- **"Why does the PC classify, not the Pi?"** Central logging, reports and the dashboard live on the PC; the
  Pi keeps a copy of the REAL model and classifies itself when the PC is unreachable (EDGE mode).
- **"Where is the ADC / MCP3008?"** The INMP441 is a digital I2S microphone: the analog-to-digital conversion
  is inside the microphone, so no external ADC is needed.
- **"How do you know accuracy is not inflated?"** Test clips come from recordings never used in training
  (split by recording).
- **"Latency?"** Measured every cycle (device + PC + end-to-end) and averaged on the dashboard; target 1–3 s.
- **"Repair suggestions?"** Out of the approved scope (fault identification only); listed as future work.

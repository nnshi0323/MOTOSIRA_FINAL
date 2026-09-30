# MOTOSIRA — Training & Testing Guide

## The idea in plain words
1. Every 3-second clip becomes **80 numbers**: 40 MFCC coefficients (how the sound's energy is spread
   across frequencies, the way the ear hears it), each summarized by its **mean** and **standard
   deviation** over the clip. Knocking, misfire, valve ticking and normal produce different patterns.
2. A **Random Forest** (hundreds of decision trees that vote) learns which patterns belong to which
   condition. The share of trees that agree is the **confidence**.
3. We **test** on recordings the model never saw, to know how good it really is.

The Pi, the simulated device and training all use the same code (`common/audio.py`), so live
features are always computed exactly like training features.

## REAL dataset — step by step
**1. Record** (licensed mechanic confirms each fault — thesis [118]). Honda TMX 125 Alpha first (staged design).
- With the Pi (same mic as the final device — preferred):
  ```bash
  ./run_pi.sh collect --class knocking --model honda_tmx_125_alpha --seconds 30 --sessions 5
  ./run_pi.sh collect --ambient            # optional: 2–3 min shop noise, engine OFF
  ```
  Copy `raw_data/` from the Pi to the PC (USB stick or Google Drive).
- With a phone: put the WAV files in `raw_data/<class>/<motorcycle>/`.
  Class folders: `normal`, `knocking`, `misfire`, `valve_ticking`. Motorcycle folders:
  `honda_tmx_125_alpha`, `rusi_macho_125`, `suzuki_smash_carb`.
  Do not mix phone and INMP441 recordings in one class without saying so in the paper — the mics sound different.

**2. Train** — double-click `train_real.bat` (or run the three commands):
```powershell
python tools\prepare_dataset.py     # cut 3 s clips, skip first 0.5 s, reject noisy/silent clips
python tools\dataset_status.py      # progress toward ~83 clips per class per motorcycle
python model\train.py --mode real   # tune, test, save
```
Rejected clips go to `raw_data\_rejected\` — listen to a few to confirm they really are bad.

**3. Small fault sets** — multiply REAL clips (never invent sounds):
```powershell
python tools\augment_recordings.py --class knocking --model honda_tmx_125_alpha --count 5 --noise-dir raw_data\_ambient
python model\train.py --mode real
```
Report both numbers: "N real clips from R recordings, augmented to M".

## How the testing works (what train.py prints)
- **Split by recording.** All clips cut from one recording go entirely to training OR to testing.
  Otherwise near-identical clips appear on both sides and accuracy looks falsely high. With only one
  recording per class this is impossible — the script then warns "OPTIMISTIC" (record more sessions).
- **Hyper-parameter tuning** with grouped cross-validation on the training part (thesis [105]).
- **Held-out test** on the remaining recordings: accuracy, per-class precision / recall / F1,
  confusion matrix, and accuracy **per motorcycle model** (thesis [122]).
  - Precision: when it says "knocking", how often it is right (low = false alarms)
  - Recall: of the real knocking clips, how many it caught (low = missed faults)
- Saved in `model/trained/real/`: `model.joblib`, `meta.json`, `metrics.json`, `confusion_matrix.png`
  (put this image in the slides). The final model is refit on all data after testing.
- Training refuses to run with fewer than 2 classes or fewer than 5 clips per class — a one-class
  model would answer the same thing for every sound.

## After training
- The dashboard reloads the model within ~3 s (no restart). The banner shows the new model.
- Give the Pi the model for offline (EDGE) mode: commit and push `model/trained/real/`, then on the Pi
  `./run_pi.sh update` — or copy the folder by USB.
- Latency is measured on every diagnosis (Pi feature time, PC classification time, end-to-end). The
  Dashboard page shows the mean end-to-end latency — report it against the 1–3 s target.

## DEMO dataset
`train_demo.bat` regenerates 360 simulated clips (30 per class per motorcycle) and trains the DEMO
model. Its near-100 % accuracy is expected (simulated sounds are easy) and is **not** a result.

## What to write in the methodology (engineering choices not fixed by the thesis)
- Features: 40 MFCC, mean + std over the clip (80 values); analysis at 22,050 Hz; 3 s clips.
- Preprocessing: DC removal; 4th-order Butterworth low-pass at 8 kHz (software).
- Signal-quality gate: GOOD if SNR ≥ 12 dB, peak < −1 dBFS and > −50 dBFS (team thresholds).
- Segmentation: consecutive 3 s windows, first 0.5 s skipped, tail < 3 s dropped.
- Random Forest with class_weight="balanced"; grid over trees (150/300), depth (None/16), min leaf (1/3).
- Split by source recording (StratifiedGroupKFold); metric for tuning: macro F1.
- Software versions: see `requirements-pi.lock.txt` / `requirements-pc.lock.txt`.

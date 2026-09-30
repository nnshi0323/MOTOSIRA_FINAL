# MOTOSIRA — Architecture & Thesis Traceability

## Components
| Where | File | Role |
|---|---|---|
| shared | `config.py` | all settings; per-machine values from `.env` |
| shared | `common/audio.py` | THE audio pipeline: DC removal → 8 kHz low-pass → signal quality → 40 MFCC (mean+std) |
| shared | `common/classifier.py` | loads `model/trained/<mode>/model.joblib`, classifies; no random fallback |
| shared | `common/mqtt.py`, `common/protocol.py` | MQTT client (auto-reconnect) and message formats |
| Pi | `pi_side/pi_app.py` | LCD app: hardware check, motorcycle select, START, result, microSD log, EDGE fallback |
| Pi | `pi_side/mic.py` | INMP441 via googlevoicehat (48 kHz, 2 ch, S32 → left channel, 24-bit) |
| Pi | `pi_side/collect.py` | record labeled training sessions |
| PC | `dashboard/app.py` | Flask + Socket.IO + MQTT: classify, store (SQLite), PDF/CSV, START command |
| PC | `pi_side/mock_pi.py`, `common/mock_audio.py` | simulated device for DEMO mode |
| PC | `model/train.py` | grouped split, CV tuning, metrics per class and per motorcycle |
| PC | `tools/*.py` | dataset preparation, augmentation, status, checks, config.txt repair |

## MQTT topics
| Topic | Direction | Content |
|---|---|---|
| `motosira/audio` | device → PC | 80 MFCC features, signal quality, SNR, peak, envelope, RPM, feature time |
| `motosira/result` | PC → device | condition, confidence, severity, probabilities, PC time |
| `motosira/ack` | device → PC | end-to-end latency measured on the device |
| `motosira/command` | PC → device | "capture" (START from the dashboard) |
| `motosira/status` | device → PC | heartbeat every 3 s; MQTT last-will marks the device offline |

## Thesis traceability
| Thesis requirement | Implementation | Status |
|---|---|---|
| Obj 1: INMP441, ~30 cm from engine block, optional RPM | `mic.py`, WIRING.md; RPM optional on GPIO26 | software ready; hardware to verify |
| Obj 2 / [50]: low-pass filter + MFCC 13–40 (librosa) | `common/audio.py` (40 MFCC) | done |
| Obj 3: Random Forest, 4 classes, ~1,000 recordings, TMX first | `train.py`, dataset tools, status table | pipeline done; dataset in progress |
| [105]: CV hyper-parameter tuning, joblib export | GridSearchCV + StratifiedGroupKFold, joblib | done |
| Obj 4: LCD shows condition, confidence, severity, RPM, latency | `pi_app.py` (480×320) | done |
| Flowchart: hardware ready? → error message | LCD "HARDWARE NOT READY" screen + RETRY | done |
| Flowchart: select motorcycle model | LCD buttons + dashboard selector | done |
| Obj 5: session log with timestamps + latency on microSD | `logs/pi_sessions.csv` on the Pi | done |
| Obj 5: exportable report PDF/CSV per session | dashboard PDF per session, CSV export | done |
| [114]: Flask + SocketIO dashboard, MQTT (paho + Mosquitto) | `dashboard/app.py` | done |
| [122]: accuracy, P/R/F1, confusion matrix, per model, mean latency | `train.py` metrics, dashboard stats | done |
| [136]: dataset balance across classes and models | balance table in train/status output | done |
| Scope: fault identification only | severity only; no repair guidance anywhere | done |

## Deviations / choices to disclose in the paper
1. **Classification runs on the dashboard PC**, not the Pi (thesis [61], [107] say Pi). The Pi extracts
   features and keeps a copy of the REAL model for offline EDGE classification.
2. **No MCP3008 ADC / analog amplifier / hardware low-pass** (thesis [54], [59], [112]): the INMP441 is a
   digital I2S microphone. Filtering is done in software (8 kHz Butterworth).
3. Numeric parameters not in the thesis: signal-quality thresholds, 8 kHz cutoff, mean+std pooling, 3 s clips,
   22,050 Hz analysis rate, confidence warning at 60 %.
4. Software versions differ from the thesis text (Python 3.12 on PC / 3.13 on Pi; librosa 1.0.0) — see lock files.
5. DEMO mode uses a simulated dataset purely to demonstrate the pipeline; no reported metric comes from it.

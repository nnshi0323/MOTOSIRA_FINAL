"""
MOTOSIRA — central configuration (shared by the Dashboard PC and the Raspberry Pi)
Motorcycle Sound-based Identification & Reporting Assistant

Per-machine values (broker IP, password, mic device) live in .env so the SAME
code runs on both machines. Everything else is defined here, in one place.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass


def _env(name, default):
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


# ── Paths ──────────────────────────────────────────────────────────
MODEL_DIR = os.path.join(BASE_DIR, "model")
TRAINED_DIR = os.path.join(MODEL_DIR, "trained")          # trained/<mode>/model.joblib
REAL_DATA_DIR = os.path.join(MODEL_DIR, "training_data")  # real, mechanic-verified clips
MOCK_DATA_DIR = os.path.join(MODEL_DIR, "mock_data")      # SIMULATED clips (demo only)
RAW_DIR = os.path.join(BASE_DIR, "raw_data")              # long raw recordings
LOG_DIR = os.path.join(BASE_DIR, "logs")
DB_PATH = os.path.join(BASE_DIR, "dashboard", "motosira.db")
PI_SESSION_LOG = os.path.join(LOG_DIR, "pi_sessions.csv")  # on the Pi's microSD (Obj. 5)

# ── Modes ──────────────────────────────────────────────────────────
# REAL: Raspberry Pi + INMP441 audio, classified by the model trained on REAL recordings.
# MOCK: simulated device audio, classified by the model trained on the SIMULATED dataset.
#       MOCK exists only to demonstrate the pipeline; it is never real diagnosis.
MODES = ("real", "mock")
MODE_LABELS = {"real": "REAL", "mock": "DEMO (simulated)"}
DATA_DIRS = {"real": REAL_DATA_DIR, "mock": MOCK_DATA_DIR}
DEFAULT_MODE = _env("MOTOSIRA_DEFAULT_MODE", "mock")
SOURCE_TO_MODE = {"inmp441": "real", "mock": "mock"}     # which model judges which audio

# ── Motorcycles (thesis scope) ─────────────────────────────────────
MOTORCYCLE_MODELS = ["Honda TMX 125 Alpha", "Rusi Macho 125", "Suzuki Smash Carb"]
PRIMARY_MODEL = MOTORCYCLE_MODELS[0]   # staged design: primary platform first


def model_slug(name):
    return name.lower().replace(" ", "_")


SLUG_TO_MODEL = {model_slug(m): m for m in MOTORCYCLE_MODELS}

# ── Fault classes and severity (Obj. 3 and 4) ──────────────────────
CLASSES = ["normal", "knocking", "misfire", "valve_ticking"]
CLASS_LABELS = {"normal": "NORMAL", "knocking": "KNOCKING",
                "misfire": "MISFIRE", "valve_ticking": "VALVE TICKING"}
# Severity only — repair guidance is out of scope (fault identification only).
SEVERITY = {
    "normal":        {"level": 0, "text": "No fault detected"},
    "valve_ticking": {"level": 1, "text": "Minor severity"},
    "misfire":       {"level": 2, "text": "Moderate severity"},
    "knocking":      {"level": 3, "text": "Critical severity"},
}

DATASET_TARGET_PER_CLASS_PER_MODEL = 83   # ~1,000 recordings / (4 classes x 3 models)

# ── Audio: capture (INMP441 via googlevoicehat-soundcard overlay) ──
# That driver exposes the mic ONLY as 48 kHz, stereo, S32_LE; the INMP441 (L/R -> GND)
# is on the LEFT channel, as 24-bit data in the top bits of each 32-bit frame.
CAPTURE_RATE = int(_env("MOTOSIRA_CAPTURE_RATE", "48000"))
CAPTURE_CHANNELS = int(_env("MOTOSIRA_CAPTURE_CHANNELS", "2"))
MIC_DEVICE = _env("MOTOSIRA_MIC_DEVICE", "")            # optional: index or name substring
MIC_NAME_HINTS = ("googlevoicehat", "voicehat", "sndrpigooglevoi", "i2s", "inmp441")
MIC_GAIN = float(_env("MOTOSIRA_MIC_GAIN", "1.0"))      # keep identical for training and live

# ── Audio: analysis ────────────────────────────────────────────────
SAMPLE_RATE = 22050        # analysis rate (everything is resampled to this)
DURATION = 3               # seconds per diagnostic capture / training clip
LOWPASS_CUTOFF_HZ = 8000   # keeps knock/tick energy (2–8 kHz); removes hiss above
N_MFCC = 40                # thesis range 13–40
# Feature vector = mean and standard deviation of each MFCC over time (2 x N_MFCC).
N_FEATURES = 2 * N_MFCC
ENVELOPE_POINTS = 64       # downsampled waveform sent to the dashboard for display

# Signal quality (engineering thresholds; not specified in the thesis — disclose)
SIGNAL_CLIP_DBFS = -1.0
SIGNAL_GOOD_SNR_DB = 12.0
SIGNAL_TOO_QUIET_DBFS = -50.0
CONFIDENCE_WARN = 0.60     # below this the result is flagged "low confidence — re-record"

# ── Latency target (thesis: 1–3 s per diagnostic cycle) ────────────
LATENCY_TARGET_MS = 3000

# ── MQTT ───────────────────────────────────────────────────────────
MQTT_BROKER = _env("MOTOSIRA_BROKER", "localhost")   # Pi: the dashboard PC's LAN IP
MQTT_PORT = int(_env("MOTOSIRA_BROKER_PORT", "1883"))
TOPIC_AUDIO = "motosira/audio"       # device -> PC : MFCC features + signal metrics
TOPIC_RESULT = "motosira/result"     # PC -> device : classification result
TOPIC_COMMAND = "motosira/command"   # PC -> device : "capture" requests from the dashboard
TOPIC_STATUS = "motosira/status"     # device -> PC : heartbeat (mic ok, online/offline)
TOPIC_ACK = "motosira/ack"           # device -> PC : measured end-to-end latency
DEVICE_ID = _env("MOTOSIRA_DEVICE_ID", "pi-01")
RESULT_TIMEOUT_S = 6.0               # Pi waits this long for the PC before edge fallback

# ── Optional RPM sensor (Hall effect) ──────────────────────────────
# Disabled by default. GPIO17 is used by the Waveshare 3.5" touch panel, so the
# sensor pin defaults to GPIO26 (physical pin 37), which is free.
RPM_SENSOR_ENABLED = _env("MOTOSIRA_RPM_ENABLED", "0") == "1"
RPM_GPIO_PIN = int(_env("MOTOSIRA_RPM_GPIO", "26"))
RPM_MAGNETS_PER_REV = 1

# ── Dashboard ──────────────────────────────────────────────────────
DASHBOARD_PORT = int(_env("MOTOSIRA_DASHBOARD_PORT", "5000"))

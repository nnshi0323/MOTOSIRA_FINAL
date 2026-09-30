"""
MOTOSIRA — the ONE audio pipeline.

Used by the Raspberry Pi (live capture), the simulated device (mock_pi.py) and
model training (model/train.py). Because all three call these same functions,
training features and live features are always computed identically.

Pipeline: mono float audio @ 22,050 Hz -> remove DC offset -> low-pass filter
          -> signal quality (SNR, peak) -> MFCC (40) -> mean + std over time (80)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # type: ignore
from scipy.signal import butter, sosfilt  # type: ignore

import config

_SOS = None


def _lowpass_sos():
    global _SOS
    if _SOS is None:
        nyquist = config.SAMPLE_RATE / 2
        _SOS = butter(4, min(config.LOWPASS_CUTOFF_HZ / nyquist, 0.99), btype="low", output="sos")
    return _SOS


def i2s_frames_to_float(frames_int32):
    """INMP441 via googlevoicehat: 24-bit samples in the top bits of 32-bit frames.
    Right-shift out the 8 padding bits, then scale the 24-bit value to [-1, 1]."""
    x = np.asarray(frames_int32, dtype=np.int32)
    return (np.right_shift(x, 8).astype(np.float32) / float(2 ** 23)).clip(-1.0, 1.0)


def resample(audio, orig_sr, target_sr=config.SAMPLE_RATE):
    if orig_sr == target_sr:
        return np.asarray(audio, dtype=np.float32)
    import librosa  # type: ignore
    return librosa.resample(np.asarray(audio, dtype=np.float32), orig_sr=orig_sr,
                            target_sr=target_sr).astype(np.float32)


def fit_length(audio, seconds=config.DURATION, sr=config.SAMPLE_RATE):
    n = int(seconds * sr)
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) >= n:
        return audio[:n]
    return np.pad(audio, (0, n - len(audio)))


def load_wav(path, sr=config.SAMPLE_RATE):
    """Load any WAV as mono float32 at the analysis rate (handles int16/int32/float)."""
    import soundfile as sf  # type: ignore
    audio, file_sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    return resample(audio, file_sr, sr)


def preprocess(audio):
    """DC removal + low-pass filter. Input: mono float32 at SAMPLE_RATE."""
    audio = np.asarray(audio, dtype=np.float32) * config.MIC_GAIN
    audio = audio - float(np.mean(audio)) if len(audio) else audio
    return sosfilt(_lowpass_sos(), audio).astype(np.float32)


def signal_quality(audio):
    """Returns (label, snr_db, peak_dbfs). label is 'GOOD' or 'CHECK NOISE'.
    SNR = overall RMS vs. the quietest 10% of 1024-sample frames (noise-floor estimate)."""
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) == 0:
        return "CHECK NOISE", 0.0, -120.0
    peak = float(np.max(np.abs(audio))) + 1e-12
    peak_dbfs = 20 * np.log10(peak)
    rms = float(np.sqrt(np.mean(audio ** 2))) + 1e-12
    frame = 1024
    n = len(audio) // frame
    if n >= 2:
        frames = audio[: n * frame].reshape(n, frame)
        frame_rms = np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-12
        floor = float(np.percentile(frame_rms, 10))
    else:
        floor = rms
    snr_db = 20 * np.log10(rms / (floor + 1e-12))
    good = (peak_dbfs < config.SIGNAL_CLIP_DBFS and snr_db >= config.SIGNAL_GOOD_SNR_DB
            and peak_dbfs > config.SIGNAL_TOO_QUIET_DBFS)
    return ("GOOD" if good else "CHECK NOISE"), round(float(snr_db), 1), round(float(peak_dbfs), 1)


def quality_reason(snr_db, peak_dbfs):
    if peak_dbfs >= config.SIGNAL_CLIP_DBFS:
        return "clipping — too loud / mic too close"
    if peak_dbfs <= config.SIGNAL_TOO_QUIET_DBFS:
        return "almost silent — check mic wiring/placement"
    if snr_db < config.SIGNAL_GOOD_SNR_DB:
        return "noisy / unsteady signal"
    return ""


def mfcc_features(filtered):
    """80-value feature vector: mean and std of 40 MFCCs over time."""
    import librosa  # type: ignore
    m = librosa.feature.mfcc(y=np.asarray(filtered, dtype=np.float32),
                             sr=config.SAMPLE_RATE, n_mfcc=config.N_MFCC)
    return np.concatenate([m.mean(axis=1), m.std(axis=1)]).astype(np.float32)


def envelope(audio, points=config.ENVELOPE_POINTS):
    """Downsampled RMS envelope (0..1) so the dashboard can draw the REAL waveform."""
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) < points:
        return [0.0] * points
    chunks = np.array_split(audio, points)
    env = np.array([float(np.sqrt(np.mean(c ** 2))) for c in chunks])
    top = env.max()
    return [round(float(v / top), 3) if top > 0 else 0.0 for v in env]


def analyze(audio):
    """Full pipeline for one clip. Returns a dict (features + metrics)."""
    clip = fit_length(audio)
    filtered = preprocess(clip)
    label, snr_db, peak_dbfs = signal_quality(filtered)
    return {
        "features": mfcc_features(filtered),
        "signal_quality": label,
        "quality_reason": quality_reason(snr_db, peak_dbfs),
        "snr_db": snr_db,
        "peak_dbfs": peak_dbfs,
        "envelope": envelope(filtered),
    }


def warm_up():
    """First librosa call is slow (lazy imports/JIT). Run once at startup so the
    first real diagnosis meets the latency target."""
    analyze(np.random.default_rng(0).normal(0, 0.05, config.SAMPLE_RATE * config.DURATION))

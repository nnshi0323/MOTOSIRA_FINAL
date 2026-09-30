"""
MOTOSIRA — SIMULATED engine sounds for DEMO mode only.

These are NOT recordings and must never be reported as real results. They exist
so the full pipeline (capture -> MFCC -> Random Forest -> dashboard/LCD/report)
can be demonstrated before enough real fault recordings exist.

Model: single-cylinder 4-stroke engine at idle. One combustion pulse every two
crank revolutions (firing rate = RPM / 120 Hz), each pulse a decaying burst of
filtered noise, plus a harmonic hum, mechanical noise and shop background noise.
  knocking      : sharp metallic ringing (3–5 kHz) on many firing events
  misfire       : ~25–40 % of firing events missing (irregular gaps)
  valve_ticking : light regular clicks at valve-train rate (RPM / 60 Hz)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # type: ignore
from scipy.signal import butter, sosfilt  # type: ignore

import config

# Idle RPM per bike (simulation parameters, not measurements)
IDLE_RPM = {"Honda TMX 125 Alpha": 1400, "Rusi Macho 125": 1500, "Suzuki Smash Carb": 1600}


def _band(noise, lo, hi, sr):
    sos = butter(2, [lo / (sr / 2), min(hi / (sr / 2), 0.99)], btype="band", output="sos")
    return sosfilt(sos, noise)


def generate(condition, bike=config.PRIMARY_MODEL, seed=None,
             seconds=config.DURATION, sr=config.SAMPLE_RATE):
    if condition not in config.CLASSES:
        raise ValueError(f"unknown condition {condition}")
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    rpm = IDLE_RPM.get(bike, 1400) * rng.uniform(0.93, 1.07)
    fire_hz = rpm / 120.0

    # Harmonic hum of the firing rhythm
    hum = np.zeros(n)
    for k in range(1, 30):
        hum += (1.0 / k) * np.sin(2 * np.pi * fire_hz * k * t + rng.uniform(0, 2 * np.pi))
    hum *= 0.008

    # Combustion pulses
    pulses = np.zeros(n)
    period = int(sr / fire_hz)
    burst_len = int(0.03 * sr)
    burst_env = np.exp(-np.linspace(0, 7, burst_len))
    fired = []
    pos = int(rng.uniform(0, period))
    while pos + burst_len < n:
        jitter = int(rng.normal(0, 0.01) * period)
        start = min(max(0, pos + jitter), n - burst_len)
        skip = condition == "misfire" and rng.random() < rng.uniform(0.25, 0.40)
        if not skip:
            burst = _band(rng.normal(0, 1, burst_len), 80, 1500, sr) * burst_env
            pulses[start:start + burst_len] += 1.3 * burst * rng.uniform(0.8, 1.2)
            fired.append(start)
        pos += period

    extra = np.zeros(n)
    if condition == "knocking":
        ring_len = int(0.012 * sr)
        tt = np.arange(ring_len) / sr
        for start in fired:
            if rng.random() < 0.75:
                f = rng.uniform(3000, 5000)
                ring = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 450)
                s = start + int(0.004 * sr)
                if s + ring_len < n:
                    extra[s:s + ring_len] += 0.8 * ring * rng.uniform(0.7, 1.2)
    elif condition == "valve_ticking":
        click_len = int(0.003 * sr)
        tick_hz = rpm / 60.0
        tick_period = int(sr / tick_hz)
        pos = int(rng.uniform(0, tick_period))
        while pos + click_len < n:
            click = _band(rng.normal(0, 1, click_len), 2000, 7000, sr) * np.exp(-np.linspace(0, 5, click_len))
            extra[pos:pos + click_len] += 0.22 * click
            pos += tick_period + int(rng.normal(0, 0.003) * tick_period)

    mech = _band(rng.normal(0, 1, n), 200, 6000, sr) * 0.004
    shop = rng.normal(0, rng.uniform(0.001, 0.006), n)     # background noise varies per clip
    audio = hum + pulses + extra + mech + shop
    audio = audio / (np.max(np.abs(audio)) + 1e-9) * rng.uniform(0.3, 0.6)
    return audio.astype(np.float32)

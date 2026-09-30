"""
MOTOSIRA — multiply a SMALL set of REAL clips with realistic variation.

Every output is a transformed copy of a real recording (pitch shift ±1.5 semitones,
time stretch ±8 %, gain ±3 dB, background noise, small time shift). No fault sound
is invented. Augmented files are named aug_<source>_<n>.wav, so training keeps them
in the SAME group as their source recording (they never leak into the test set
as a different recording). Every file is listed in a manifest for disclosure.

    python tools/augment_recordings.py --class knocking --model honda_tmx_125_alpha --count 5
    python tools/augment_recordings.py --class knocking --model honda_tmx_125_alpha --count 5 --noise-dir raw_data/_ambient

Report "N real clips from R recordings, augmented to M" in the paper.
"""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # type: ignore
import soundfile as sf  # type: ignore

import config
from common import audio


def augment_once(y, sr, noise_bank, rng):
    import librosa  # type: ignore
    p = {}
    p["pitch_semitones"] = round(rng.uniform(-1.5, 1.5), 2)
    y = librosa.effects.pitch_shift(y, sr=sr, n_steps=p["pitch_semitones"])
    p["time_stretch"] = round(rng.uniform(0.92, 1.08), 3)
    y = audio.fit_length(librosa.effects.time_stretch(y, rate=p["time_stretch"]))
    p["gain_db"] = round(rng.uniform(-3, 3), 2)
    y = y * (10 ** (p["gain_db"] / 20))
    p["noise_snr_db"] = round(rng.uniform(15, 30), 1)
    if noise_bank:
        noise = noise_bank[rng.randrange(len(noise_bank))]
        start = rng.randrange(max(1, len(noise) - len(y)))
        noise = audio.fit_length(noise[start:start + len(y)])
        p["noise_source"] = "real ambient recording"
    else:
        noise = np.random.default_rng(rng.randrange(1 << 30)).normal(0, 1, len(y)).astype(np.float32)
        p["noise_source"] = "white noise (no --noise-dir given)"
    sig = float(np.sqrt(np.mean(y ** 2))) + 1e-9
    nrm = float(np.sqrt(np.mean(noise ** 2))) + 1e-9
    y = y + noise * (sig / (10 ** (p["noise_snr_db"] / 20)) / nrm)
    p["shift_ms"] = int(rng.uniform(-150, 150))
    y = np.roll(y, int(p["shift_ms"] * sr / 1000))
    return np.clip(y, -1, 1).astype(np.float32), p


def main(label, slug, count, noise_dir):
    folder = os.path.join(config.REAL_DATA_DIR, label, slug)
    sources = sorted(f for f in os.listdir(folder) if f.lower().endswith(".wav") and not f.startswith("aug_")) \
        if os.path.isdir(folder) else []
    if not sources:
        print(f"No real clips in {folder}. Run tools/prepare_dataset.py first.")
        return 1
    noise_bank = []
    if noise_dir:
        for f in sorted(os.listdir(noise_dir)):
            if f.lower().endswith(".wav"):
                noise_bank.append(audio.load_wav(os.path.join(noise_dir, f)))
    rng = random.Random(42)
    manifest = []
    for src in sources:
        y = audio.load_wav(os.path.join(folder, src))
        for i in range(count):
            out, params = augment_once(y, config.SAMPLE_RATE, noise_bank, rng)
            name = f"aug_{os.path.splitext(src)[0]}_{i:02d}.wav"
            sf.write(os.path.join(folder, name), out, config.SAMPLE_RATE, subtype="PCM_16")
            manifest.append({"file": name, "source": src, "params": params})
    os.makedirs(config.LOG_DIR, exist_ok=True)
    path = os.path.join(config.LOG_DIR, f"augmentation_{label}_{slug}_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"class": label, "motorcycle": config.SLUG_TO_MODEL[slug], "real_clips": len(sources),
                   "augmented_clips": len(manifest), "items": manifest}, fh, indent=2)
    print(f"{len(sources)} real clips -> {len(manifest)} augmented clips in {os.path.relpath(folder, config.BASE_DIR)}")
    print(f"Manifest: {os.path.relpath(path, config.BASE_DIR)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--class", dest="label", required=True, choices=config.CLASSES)
    ap.add_argument("--model", required=True, choices=sorted(config.SLUG_TO_MODEL))
    ap.add_argument("--count", type=int, default=5, help="augmented copies per real clip")
    ap.add_argument("--noise-dir", default=None, help="folder of real ambient shop-noise WAVs")
    a = ap.parse_args()
    sys.exit(main(a.label, a.model, a.count, a.noise_dir))

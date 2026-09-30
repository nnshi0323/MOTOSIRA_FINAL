"""
MOTOSIRA — microphone test on the Pi (./run_pi.sh mictest).

Lists input devices, opens the INMP441, records 5 s, prints level/SNR and saves
logs/mic_test.wav so you can copy it to the PC and listen.
Tap or talk near the mic while it records: the peak should rise well above -50 dBFS.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # type: ignore
import soundfile as sf  # type: ignore

import config
from common import audio
from pi_side.mic import Mic, MicError


def main():
    mic = Mic()
    try:
        print("Input devices:")
        for i, name, ch, rate in mic.list_inputs():
            print(f"  [{i}] {name}  ({ch} ch, {rate} Hz)")
        info = mic.open()
    except MicError as exc:
        print(f"\nHARDWARE NOT READY: {exc}")
        return 1
    print(f"\nUsing: {info['name']} @ {info['rate']} Hz, {info['channels']} ch (left channel = INMP441)")
    print("Recording 5 s — tap or talk near the mic...")
    clip = mic.record(5)
    q, snr, peak = audio.signal_quality(audio.preprocess(clip))
    rms_db = 20 * np.log10(float(np.sqrt(np.mean(clip ** 2))) + 1e-12)
    os.makedirs(config.LOG_DIR, exist_ok=True)
    path = os.path.join(config.LOG_DIR, "mic_test.wav")
    sf.write(path, clip, config.SAMPLE_RATE, subtype="PCM_16")
    print(f"\nPeak {peak} dBFS | RMS {rms_db:.1f} dBFS | SNR {snr} dB | quality {q} {audio.quality_reason(snr, peak)}")
    print(f"Saved {path}")
    if peak <= config.SIGNAL_TOO_QUIET_DBFS:
        print("Almost silent: check SD->pin 38, SCK->pin 12, WS->pin 35, VDD->3.3V (pin 1), L/R->GND.")
    else:
        print("Microphone OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
MOTOSIRA — record REAL training data with the INMP441 (run on the Pi).

    python pi_side/collect.py --class knocking --model honda_tmx_125_alpha
    python pi_side/collect.py --class normal   --model honda_tmx_125_alpha --seconds 45 --sessions 3
    python pi_side/collect.py --ambient        # shop noise only (engine OFF), for augmentation

Each session is a LONG recording (default 30 s = 9 training clips). Before a
session is kept, the licensed mechanic must confirm the condition (thesis [118]).
Files go to raw_data/<class>/<model>/pi_<date>_<time>.wav on the Pi.
Then copy raw_data/ to the PC and run:  python tools/prepare_dataset.py
Stop recording as soon as the engine stops — trailing silence gets rejected.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import soundfile as sf  # type: ignore

import config
from common import audio
from pi_side.mic import Mic, MicError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--class", dest="label", choices=config.CLASSES)
    ap.add_argument("--model", choices=sorted(config.SLUG_TO_MODEL), default=config.model_slug(config.PRIMARY_MODEL))
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--sessions", type=int, default=5)
    ap.add_argument("--ambient", action="store_true", help="record background shop noise (engine off)")
    a = ap.parse_args()
    if not a.ambient and not a.label:
        ap.error("--class is required (or use --ambient)")

    mic = Mic()
    try:
        info = mic.open()
    except MicError as exc:
        print(f"HARDWARE NOT READY: {exc}")
        return 1
    out_dir = os.path.join(config.RAW_DIR, "_ambient") if a.ambient else \
        os.path.join(config.RAW_DIR, a.label, a.model)
    os.makedirs(out_dir, exist_ok=True)
    what = "AMBIENT SHOP NOISE (engine OFF)" if a.ambient else f"{a.label.upper()} — {config.SLUG_TO_MODEL[a.model]}"
    print(f"\n=== MOTOSIRA data collection: {what} ===")
    print(f"Mic: {info['name']} @ {info['rate']} Hz | {a.seconds} s per session | saving to {out_dir}")
    if not a.ambient:
        print("Mic ~30 cm from the engine block, engine running at the target RPM.\n")
    kept = 0
    for n in range(1, a.sessions + 1):
        if input(f"[{n}/{a.sessions}] ENTER to record (or q to stop): ").strip().lower() == "q":
            break
        print(f"  recording {a.seconds} s ...")
        clip = mic.record(a.seconds)
        q, snr, peak = audio.signal_quality(audio.preprocess(clip))
        print(f"  quality {q}  SNR {snr} dB  peak {peak} dBFS  {audio.quality_reason(snr, peak)}")
        prompt = "  Keep it? [y/N]: " if a.ambient else f"  Mechanic confirms {a.label.upper()}? Keep it? [y/N]: "
        if input(prompt).strip().lower() != "y":
            print("  discarded\n")
            continue
        name = f"pi_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        sf.write(os.path.join(out_dir, name), clip, config.SAMPLE_RATE, subtype="PCM_16")
        kept += 1
        print(f"  saved {name}\n")
    print(f"{kept} session(s) saved in {out_dir}")
    print("Next on the PC: copy raw_data/ over, then  python tools/prepare_dataset.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

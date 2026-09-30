"""
MOTOSIRA — generate the SIMULATED dataset for DEMO mode.

    python tools/generate_mock_dataset.py            # 30 clips per class per motorcycle (360 total)
    python tools/generate_mock_dataset.py --per-cell 50

Writes model/mock_data/<class>/<motorcycle_slug>/mock_sNNNN_000.wav
These files are synthetic. They are kept completely separate from the real
dataset (model/training_data/) and are only used to train the DEMO model.
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import soundfile as sf  # type: ignore

import config
from common import mock_audio


def main(per_cell):
    root = config.MOCK_DATA_DIR
    for label in config.CLASSES:                    # regenerate from scratch
        shutil.rmtree(os.path.join(root, label), ignore_errors=True)
    seed = 1000
    total = 0
    for label in config.CLASSES:
        for bike in config.MOTORCYCLE_MODELS:
            folder = os.path.join(root, label, config.model_slug(bike))
            os.makedirs(folder, exist_ok=True)
            for _ in range(per_cell):
                seed += 1
                audio = mock_audio.generate(label, bike=bike, seed=seed)
                sf.write(os.path.join(folder, f"mock_s{seed:05d}_000.wav"), audio,
                         config.SAMPLE_RATE, subtype="PCM_16")
                total += 1
        print(f"  {label:<14} {per_cell * len(config.MOTORCYCLE_MODELS)} clips")
    print(f"\n{total} SIMULATED clips written to {os.path.relpath(root, config.BASE_DIR)}/")
    print("Next:  python model/train.py --mode mock")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=30, help="clips per class per motorcycle")
    main(ap.parse_args().per_cell)

"""
MOTOSIRA — dataset progress (REAL and DEMO datasets, and trained models).

    python tools/dataset_status.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from common.classifier import ModelStore


def count(root, label, slug, prefix=None):
    folder = os.path.join(root, label, slug)
    if not os.path.isdir(folder):
        return 0
    return sum(1 for f in os.listdir(folder) if f.lower().endswith(".wav")
               and (prefix is None or f.startswith(prefix)))


def table(title, root, show_raw=False):
    print(f"\n{title}  (target {config.DATASET_TARGET_PER_CLASS_PER_MODEL} clips per cell)")
    print(f"  {'class':<15}" + "".join(f"{m[:20]:>22}" for m in config.MOTORCYCLE_MODELS))
    for label in config.CLASSES:
        row = f"  {label:<15}"
        for m in config.MOTORCYCLE_MODELS:
            slug = config.model_slug(m)
            n = count(root, label, slug)
            aug = count(root, label, slug, "aug_")
            cell = f"{n}" + (f" ({aug} aug)" if aug else "")
            if show_raw:
                cell += f" | raw {count(config.RAW_DIR, label, slug)}"
            row += f"{cell:>22}"
        print(row)


if __name__ == "__main__":
    table("REAL dataset  model/training_data/  (clips | raw recordings waiting in raw_data/)",
          config.REAL_DATA_DIR, show_raw=True)
    table("DEMO dataset  model/mock_data/  (SIMULATED)", config.MOCK_DATA_DIR)
    store = ModelStore()
    print("\nTrained models:")
    for mode in config.MODES:
        i = store.info(mode)
        if i["trained"]:
            print(f"  {config.MODE_LABELS[mode]:<18} trained {i['trained_at']} | {i['samples']} clips from "
                  f"{i['recordings']} recordings | test acc {i['test_accuracy']:.1%} | split: {i['split']} "
                  f"| classes: {', '.join(i['classes'])}")
        else:
            print(f"  {config.MODE_LABELS[mode]:<18} NOT TRAINED")

"""
MOTOSIRA — Random Forest training and evaluation (thesis Obj. 3; methodology [105], [122])

    python model/train.py --mode real     # REAL recordings in model/training_data/
    python model/train.py --mode mock     # SIMULATED dataset in model/mock_data/ (demo only)

Dataset layout:  <data dir>/<class>/<motorcycle_slug>/*.wav   (3-second clips)

What it does
  1. Extracts features with common/audio.py — the SAME code the Pi uses live.
  2. Holds out a TEST set split BY SOURCE RECORDING (clips cut from one recording
     never appear in both train and test, so accuracy is not inflated).
  3. Tunes Random Forest hyper-parameters with grouped cross-validation.
  4. Reports accuracy, per-class precision/recall/F1 and a confusion matrix,
     in aggregate AND per motorcycle model; saves a PNG for the slides.
  5. Refits the tuned model on all data and saves it to model/trained/<mode>/.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # type: ignore

import config
from common import audio
from common.classifier import model_paths


def group_of(stem, label, slug):
    """Clips cut from the same source recording share a group id."""
    # e.g. "normal_20260825132535_004"      -> "20260825132535"
    #      "aug_normal_20260825132535_004_02" -> "20260825132535"  (same group as its source)
    #      "knocking_pi_20261001_101500_003"  -> "pi_20261001_101500"
    s, prev = stem, None
    while s != prev:
        prev = s
        for prefix in ("aug_", "mock_", f"{label}_"):
            if s.startswith(prefix):
                s = s[len(prefix):]
        if re.search(r"_\d{1,3}$", s):          # clip / augmentation index (1–3 digits)
            s = re.sub(r"_\d{1,3}$", "", s)
    return f"{slug}/{s}"


def load_dataset(mode):
    root = config.DATA_DIRS[mode]
    X, y, groups, bikes, files = [], [], [], [], []
    for label in config.CLASSES:
        for slug in sorted(config.SLUG_TO_MODEL):
            folder = os.path.join(root, label, slug)
            if not os.path.isdir(folder):
                continue
            wavs = sorted(f for f in os.listdir(folder) if f.lower().endswith(".wav"))
            for i, name in enumerate(wavs):
                path = os.path.join(folder, name)
                try:
                    feats = audio.analyze(audio.load_wav(path))["features"]
                except Exception as exc:
                    print(f"  skipped {path}: {exc}")
                    continue
                X.append(feats)
                y.append(label)
                groups.append(group_of(os.path.splitext(name)[0], label, slug))
                bikes.append(config.SLUG_TO_MODEL[slug])
                files.append(os.path.relpath(path, config.BASE_DIR))
                if (i + 1) % 50 == 0:
                    print(f"  {label}/{slug}: {i + 1}/{len(wavs)}")
    return np.array(X), np.array(y), np.array(groups), np.array(bikes), files


def print_balance(y, bikes, groups):
    print("\nDataset (clips / source recordings) — target ~%d clips per cell:" %
          config.DATASET_TARGET_PER_CLASS_PER_MODEL)
    head = f"  {'class':<15}" + "".join(f"{m[:20]:>24}" for m in config.MOTORCYCLE_MODELS)
    print(head)
    for label in config.CLASSES:
        row = f"  {label:<15}"
        for m in config.MOTORCYCLE_MODELS:
            mask = (y == label) & (bikes == m)
            row += f"{f'{int(mask.sum())} / {len(set(groups[mask]))}':>24}"
        print(row)


def choose_splitters(y, groups):
    """Grouped split when every class has >= 2 source recordings; otherwise fall back
    to a clip-level split and say so loudly."""
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold  # type: ignore
    min_groups = min(len(set(groups[y == c])) for c in set(y))
    min_clips = min(int((y == c).sum()) for c in set(y))
    if min_groups >= 2:
        k = min(5, min_groups)
        return "grouped", StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=42), k
    k = min(5, min_clips)
    print("\n  WARNING: a class has only ONE source recording, so clips from the same")
    print("  recording will appear in both train and test. Accuracy will be OPTIMISTIC.")
    print("  Record more separate sessions per class before reporting results.")
    return "clip-level (optimistic)", StratifiedKFold(n_splits=k, shuffle=True, random_state=42), k


def save_confusion_png(cm, labels, title, path):
    import matplotlib  # type: ignore
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
    fig, ax = plt.subplots(figsize=(6.4, 5.4), dpi=150)
    ax.imshow(cm, cmap="Oranges")
    names = [config.CLASS_LABELS.get(l, l) for l in labels]
    ax.set_xticks(range(len(labels)), names, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)), names)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual (ground truth)")
    ax.set_title(title, fontsize=10)
    top = cm.max() if cm.size else 1
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > top / 2 else "black", fontsize=12)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def train(mode):
    import joblib  # type: ignore
    import sklearn  # type: ignore
    import librosa  # type: ignore
    from sklearn.ensemble import RandomForestClassifier  # type: ignore
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix  # type: ignore
    from sklearn.model_selection import GridSearchCV  # type: ignore
    from sklearn.pipeline import Pipeline  # type: ignore
    from sklearn.preprocessing import StandardScaler  # type: ignore

    synthetic = mode == "mock"
    print(f"=== MOTOSIRA training — {config.MODE_LABELS[mode]} ===")
    if synthetic:
        print("NOTE: SIMULATED dataset. Metrics demonstrate the pipeline only — never report them as results.")
    print(f"Loading {os.path.relpath(config.DATA_DIRS[mode], config.BASE_DIR)} ...")
    t0 = time.time()
    X, y, groups, bikes, files = load_dataset(mode)
    if len(X) == 0:
        print("\nNo clips found.")
        if mode == "mock":
            print("Run:  python tools/generate_mock_dataset.py")
        else:
            print("Put raw recordings in raw_data/<class>/<motorcycle_slug>/ and run:")
            print("      python tools/prepare_dataset.py")
        return 1
    print(f"Feature extraction: {len(X)} clips in {time.time() - t0:.1f}s")
    print_balance(y, bikes, groups)

    present = [c for c in config.CLASSES if c in set(y)]
    if len(present) < 2:
        print(f"\nOnly one class has data ({present}). A classifier needs at least two classes;")
        print("a one-class model would answer that class for EVERY sound. No model saved.")
        print("Record real fault clips (knocking / misfire / valve_ticking), then re-run.")
        return 1
    counts = Counter(y)
    if min(counts.values()) < 5:
        print(f"\nEvery class needs at least 5 clips (have {dict(counts)}). No model saved.")
        return 1
    missing = [c for c in config.CLASSES if c not in present]
    if missing:
        print(f"\nNOTE: no data yet for {missing}. This model can only answer {present}.")

    split_method, outer, k = choose_splitters(y, groups)
    train_idx, test_idx = next(outer.split(X, y, groups))
    Xtr, ytr, gtr = X[train_idx], y[train_idx], groups[train_idx]
    Xte, yte, bte = X[test_idx], y[test_idx], bikes[test_idx]
    print(f"\nSplit: {split_method}; train {len(train_idx)} clips, test {len(test_idx)} clips "
          f"(1/{k} of the data held out)")

    _, inner, k_in = choose_splitters(ytr, gtr) if len(set(ytr)) >= 2 else (None, None, 0)
    pipe = Pipeline([("scale", StandardScaler()),
                     ("rf", RandomForestClassifier(class_weight="balanced", random_state=42, n_jobs=-1))])
    grid = {"rf__n_estimators": [150, 300], "rf__max_depth": [None, 16], "rf__min_samples_leaf": [1, 3]}
    search = GridSearchCV(pipe, grid, cv=inner, scoring="f1_macro", n_jobs=1)
    print(f"Hyper-parameter tuning: {len(grid['rf__n_estimators']) * 4} settings x {k_in}-fold CV ...")
    search.fit(Xtr, ytr, groups=gtr)
    print(f"  best: {search.best_params_}  (CV macro-F1 {search.best_score_:.3f})")

    best = search.best_estimator_
    pred = best.predict(Xte)
    acc = accuracy_score(yte, pred)
    labels = [c for c in present if c in set(yte) | set(pred)]
    report = classification_report(yte, pred, labels=labels,
                                   target_names=[config.CLASS_LABELS[c] for c in labels],
                                   zero_division=0, output_dict=True)
    cm = confusion_matrix(yte, pred, labels=labels)
    per_bike = {}
    for m in config.MOTORCYCLE_MODELS:
        mask = bte == m
        if mask.any():
            per_bike[m] = {"test_clips": int(mask.sum()),
                           "accuracy": round(float(accuracy_score(yte[mask], pred[mask])), 4)}

    print(f"\nTEST accuracy (held-out): {acc:.2%}")
    print(classification_report(yte, pred, labels=labels,
                                target_names=[config.CLASS_LABELS[c] for c in labels], zero_division=0))
    print("Confusion matrix (rows = actual, cols = predicted):", [config.CLASS_LABELS[c] for c in labels])
    print(cm)
    for m, v in per_bike.items():
        print(f"  {m:<22} accuracy {v['accuracy']:.2%} on {v['test_clips']} test clips")

    # Final model: tuned settings, refit on ALL data
    final = search.best_estimator_.set_params()
    final.fit(X, y)

    p = model_paths(mode)
    os.makedirs(p["dir"], exist_ok=True)
    joblib.dump(final, p["model"])
    title = f"MOTOSIRA {'DEMO (SIMULATED DATA)' if synthetic else 'REAL DATA'} — test acc {acc:.1%}"
    save_confusion_png(cm, labels, title, p["confusion_png"])
    meta = {
        "mode": mode, "synthetic": synthetic, "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "classes": [str(c) for c in final.classes_], "n_samples": int(len(X)),
        "n_recordings": int(len(set(groups))), "n_features": int(X.shape[1]),
        "test_accuracy": round(float(acc), 4), "cv_accuracy": round(float(search.best_score_), 4),
        "cv_metric": "macro F1", "split_method": split_method, "best_params": search.best_params_,
        "feature_config": {"sample_rate": config.SAMPLE_RATE, "duration_s": config.DURATION,
                           "n_mfcc": config.N_MFCC, "stats": "mean+std", "lowpass_hz": config.LOWPASS_CUTOFF_HZ},
        "versions": {"scikit-learn": sklearn.__version__, "librosa": librosa.__version__,
                     "numpy": np.__version__},
        "counts": {f"{c}|{m}": int(((y == c) & (bikes == m)).sum())
                   for c in config.CLASSES for m in config.MOTORCYCLE_MODELS},
    }
    with open(p["meta"], "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    with open(p["metrics"], "w", encoding="utf-8") as fh:
        json.dump({"test_accuracy": acc, "report": report, "confusion_matrix": cm.tolist(),
                   "labels": labels, "per_motorcycle": per_bike, "test_files": [files[i] for i in test_idx]},
                  fh, indent=2)
    print(f"\nSaved: {os.path.relpath(p['dir'], config.BASE_DIR)}/ (model.joblib, meta.json, "
          f"metrics.json, confusion_matrix.png)")
    print("The dashboard picks up the new model automatically within a few seconds.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Train the MOTOSIRA Random Forest")
    ap.add_argument("--mode", choices=config.MODES, required=True,
                    help="real = your recordings; mock = simulated demo dataset")
    sys.exit(train(ap.parse_args().mode))

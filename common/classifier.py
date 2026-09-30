"""
MOTOSIRA — trained-model loader and classifier (used by the dashboard AND the Pi).

Each mode has its own model folder:
    model/trained/real/  model.joblib + meta.json + metrics.json + confusion_matrix.png
    model/trained/mock/  (same files, trained on the SIMULATED dataset)

There is NO random fallback: if a model is missing, classify() returns None and
the UI says the model is not trained.
"""
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # type: ignore

import config


def model_paths(mode):
    folder = os.path.join(config.TRAINED_DIR, mode)
    return {
        "dir": folder,
        "model": os.path.join(folder, "model.joblib"),
        "meta": os.path.join(folder, "meta.json"),
        "metrics": os.path.join(folder, "metrics.json"),
        "confusion_png": os.path.join(folder, "confusion_matrix.png"),
    }


class ModelStore:
    def __init__(self):
        self._models = {}
        self._meta = {}
        self._mtime = {}
        self._lock = threading.Lock()
        for mode in config.MODES:
            self.load(mode)

    def load(self, mode):
        p = model_paths(mode)
        with self._lock:
            self._models.pop(mode, None)
            self._meta.pop(mode, None)
            if not os.path.exists(p["model"]):
                return False
            try:
                import joblib  # type: ignore
                meta = {}
                if os.path.exists(p["meta"]):
                    with open(p["meta"], encoding="utf-8") as fh:
                        meta = json.load(fh)
                if meta.get("n_features", config.N_FEATURES) != config.N_FEATURES:
                    print(f"[model] {mode} model expects {meta.get('n_features')} features but the pipeline "
                          f"produces {config.N_FEATURES}. Retrain: python model/train.py --mode {mode}")
                    return False
                model = joblib.load(p["model"])
                model.predict_proba(np.zeros((1, config.N_FEATURES), dtype=np.float32))  # warm-up
                self._models[mode] = model
                self._meta[mode] = meta
                self._mtime[mode] = os.path.getmtime(p["model"])
                print(f"[model] loaded {mode.upper()} model: classes={[str(c) for c in self._models[mode].classes_]}")
                return True
            except Exception as exc:
                print(f"[model] could not load {mode} model ({exc}). Retrain it with model/train.py.")
                return False

    def reload_if_changed(self):
        """Pick up a freshly trained model without restarting the dashboard."""
        for mode in config.MODES:
            path = model_paths(mode)["model"]
            if os.path.exists(path) and os.path.getmtime(path) != self._mtime.get(mode):
                self.load(mode)
            elif not os.path.exists(path) and mode in self._models:
                self.load(mode)

    def available(self, mode):
        return mode in self._models

    def info(self, mode):
        meta = self._meta.get(mode, {})
        return {
            "mode": mode,
            "trained": self.available(mode),
            "classes": list(self._models[mode].classes_) if self.available(mode) else [],
            "samples": meta.get("n_samples"),
            "recordings": meta.get("n_recordings"),
            "test_accuracy": meta.get("test_accuracy"),
            "cv_accuracy": meta.get("cv_accuracy"),
            "trained_at": meta.get("trained_at"),
            "synthetic": meta.get("synthetic", mode == "mock"),
            "split": meta.get("split_method"),
        }

    def classify(self, mode, features):
        """Returns (label, confidence, {class: prob}) or None if no model."""
        with self._lock:
            model = self._models.get(mode)
            if model is None:
                return None
            x = np.asarray(features, dtype=np.float32).reshape(1, -1)
            probs = model.predict_proba(x)[0]
            classes = [str(c) for c in model.classes_]
        best = int(np.argmax(probs))
        return classes[best], round(float(probs[best]), 3), {c: round(float(p), 3) for c, p in zip(classes, probs)}


def severity_of(label):
    return config.SEVERITY.get(label, {"level": None, "text": ""})

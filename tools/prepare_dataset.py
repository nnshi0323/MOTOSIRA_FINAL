"""
MOTOSIRA — turn RAW recordings into training clips (REAL dataset).

    raw_data/<class>/<motorcycle_slug>/*.wav        long recordings (phone or Pi --collect)
        -> cut into 3 s clips (skip first 0.5 s, drop tail < 3 s, never pad)
        -> quality filter with the SAME signal_quality() used live
    model/training_data/<class>/<motorcycle_slug>/<class>_<source>_<nnn>.wav

    python tools/prepare_dataset.py              # process new raw files only
    python tools/prepare_dataset.py --redo       # rebuild everything from raw_data
    python tools/prepare_dataset.py --dry-run    # show counts, write nothing

Rejected clips go to raw_data/_rejected/ so you can listen and double-check.
A JSON report (per file and per clip) is written to logs/ for the paper.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import soundfile as sf  # type: ignore

import config
from common import audio

SKIP_START_S = 0.5
REJECT_DIR = os.path.join(config.RAW_DIR, "_rejected")


def main(redo, dry_run):
    report = {"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "clip_seconds": config.DURATION,
              "skip_start_s": SKIP_START_S,
              "quality_rule": (f"GOOD if SNR >= {config.SIGNAL_GOOD_SNR_DB} dB, peak < {config.SIGNAL_CLIP_DBFS} "
                               f"dBFS and > {config.SIGNAL_TOO_QUIET_DBFS} dBFS (after DC removal + "
                               f"{config.LOWPASS_CUTOFF_HZ} Hz low-pass)"),
              "files": [], "totals": {"raw_files": 0, "segments": 0, "kept": 0, "rejected": 0}}
    clip_n = int(config.DURATION * config.SAMPLE_RATE)
    for label in config.CLASSES:
        for slug in sorted(config.SLUG_TO_MODEL):
            src_dir = os.path.join(config.RAW_DIR, label, slug)
            if not os.path.isdir(src_dir):
                continue
            raws = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".wav"))
            if not raws:
                continue
            out_dir = os.path.join(config.REAL_DATA_DIR, label, slug)
            rej_dir = os.path.join(REJECT_DIR, label, slug)
            print(f"\n[{label} / {config.SLUG_TO_MODEL[slug]}] {len(raws)} raw file(s)")
            for name in raws:
                stem = os.path.splitext(name)[0]
                done = glob.glob(os.path.join(out_dir, f"{label}_{stem}_*.wav")) + \
                    glob.glob(os.path.join(rej_dir, f"{label}_{stem}_*.wav"))
                if done and not redo:
                    print(f"  {name:<32} already processed (use --redo to rebuild)")
                    continue
                if not dry_run:
                    for f in done:
                        os.remove(f)
                    os.makedirs(out_dir, exist_ok=True)
                    os.makedirs(rej_dir, exist_ok=True)
                wav = audio.load_wav(os.path.join(src_dir, name))
                start = int(SKIP_START_S * config.SAMPLE_RATE)
                kept = rejected = 0
                clips_log = []
                i = 0
                while start + clip_n <= len(wav):
                    clip = wav[start:start + clip_n]
                    q, snr, peak = audio.signal_quality(audio.preprocess(clip))
                    out_name = f"{label}_{stem}_{i:03d}.wav"
                    ok = q == "GOOD"
                    if not dry_run:
                        sf.write(os.path.join(out_dir if ok else rej_dir, out_name), clip,
                                 config.SAMPLE_RATE, subtype="PCM_16")
                    kept += ok
                    rejected += not ok
                    clips_log.append({"clip": out_name, "kept": ok, "snr_db": snr, "peak_dbfs": peak,
                                      "reason": audio.quality_reason(snr, peak)})
                    start += clip_n
                    i += 1
                dur = len(wav) / config.SAMPLE_RATE
                print(f"  {name:<32} {dur:6.1f}s -> {i:3d} clips | kept {kept:3d} | rejected {rejected:3d}")
                report["files"].append({"class": label, "motorcycle": config.SLUG_TO_MODEL[slug],
                                        "source": name, "duration_s": round(dur, 2), "segments": i,
                                        "kept": kept, "rejected": rejected, "clips": clips_log})
                t = report["totals"]
                t["raw_files"] += 1
                t["segments"] += i
                t["kept"] += kept
                t["rejected"] += rejected
    t = report["totals"]
    print(f"\nTOTAL: {t['raw_files']} raw file(s) -> {t['segments']} clips -> "
          f"{t['kept']} kept, {t['rejected']} rejected")
    if t["segments"] and not dry_run:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        path = os.path.join(config.LOG_DIR, f"dataset_report_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"Report: {os.path.relpath(path, config.BASE_DIR)}")
        print(f"Rejected clips (listen to double-check): {os.path.relpath(REJECT_DIR, config.BASE_DIR)}/")
    print("Next:  python tools/dataset_status.py   then   python model/train.py --mode real")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo", action="store_true", help="re-process files that were already processed")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.redo and not a.dry_run:
        shutil.rmtree(REJECT_DIR, ignore_errors=True)
    main(a.redo, a.dry_run)

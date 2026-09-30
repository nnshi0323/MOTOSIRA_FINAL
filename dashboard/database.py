"""
MOTOSIRA — session storage (SQLite) on the dashboard PC.
Every diagnosis is stored with its mode (real/mock), source device, results,
signal metrics and the latency breakdown (Pi features, PC classification, end-to-end).
"""
import json
import os
import sqlite3
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

_lock = threading.Lock()

COLUMNS = ["id", "created_at", "capture_id", "device", "source", "mode", "bike", "classification",
           "confidence", "severity", "probabilities", "signal_quality", "quality_reason", "snr_db",
           "peak_dbfs", "rpm", "feature_ms", "pc_ms", "e2e_ms", "model_trained", "simulated_condition",
           "envelope"]


def _conn():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with _lock, _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL, capture_id TEXT UNIQUE,
            device TEXT, source TEXT, mode TEXT, bike TEXT, classification TEXT, confidence REAL,
            severity INTEGER, probabilities TEXT, signal_quality TEXT, quality_reason TEXT,
            snr_db REAL, peak_dbfs REAL, rpm INTEGER, feature_ms INTEGER, pc_ms INTEGER,
            e2e_ms INTEGER, model_trained INTEGER, simulated_condition TEXT, envelope TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mode_time ON diagnoses(mode, created_at)")


def insert(row):
    row = dict(row)
    row["probabilities"] = json.dumps(row.get("probabilities") or {})
    row["envelope"] = json.dumps(row.get("envelope") or [])
    cols = [c for c in COLUMNS if c != "id" and c in row]
    with _lock, _conn() as c:
        cur = c.execute(f"INSERT OR IGNORE INTO diagnoses ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [row[k] for k in cols])
        return cur.lastrowid


def set_e2e(row_id, e2e_ms):
    with _lock, _conn() as c:
        c.execute("UPDATE diagnoses SET e2e_ms=? WHERE id=?", (int(e2e_ms), int(row_id)))


def _decode(r):
    d = dict(r)
    d["probabilities"] = json.loads(d.get("probabilities") or "{}")
    d["envelope"] = json.loads(d.get("envelope") or "[]")
    d["time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(d["created_at"]))
    return d


def get(row_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM diagnoses WHERE id=?", (int(row_id),)).fetchone()
    return _decode(r) if r else None


def recent(limit=50, mode=None):
    q, args = "SELECT * FROM diagnoses", []
    if mode:
        q += " WHERE mode=?"
        args.append(mode)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(int(limit))
    with _conn() as c:
        return [_decode(r) for r in c.execute(q, args).fetchall()]


def stats(mode):
    with _conn() as c:
        by_class = dict(c.execute("SELECT COALESCE(classification,'unclassified'), COUNT(*) FROM diagnoses "
                                  "WHERE mode=? GROUP BY classification", (mode,)).fetchall())
        lat = c.execute("SELECT AVG(e2e_ms), MIN(e2e_ms), MAX(e2e_ms), COUNT(e2e_ms) FROM diagnoses "
                        "WHERE mode=? AND e2e_ms IS NOT NULL", (mode,)).fetchone()
        total = c.execute("SELECT COUNT(*) FROM diagnoses WHERE mode=?", (mode,)).fetchone()[0]
    return {"total": total, "by_class": by_class,
            "latency": {"mean_ms": round(lat[0]) if lat[0] else None, "min_ms": lat[1], "max_ms": lat[2],
                        "n": lat[3]}}


def all_rows(mode=None):
    return list(reversed(recent(100000, mode)))

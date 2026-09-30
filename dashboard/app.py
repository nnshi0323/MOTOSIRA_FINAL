"""
MOTOSIRA — Dashboard PC server (Flask + Socket.IO + MQTT).

    python dashboard/app.py          then open http://localhost:5000

* receives MFCC features from the Pi (REAL) or the simulated device (DEMO) over MQTT
* classifies with the model that matches the audio source (real audio is NEVER
  judged by the DEMO model), stores the session, sends the result back
* the dashboard's START button asks the active device to capture
* PDF report per session, CSV export of all sessions
"""
import csv
import io
import json
import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402  (loads .env first)
from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for  # type: ignore  # noqa: E402
from flask_socketio import SocketIO  # type: ignore  # noqa: E402

import auth  # noqa: E402
import database as db  # noqa: E402
from common.classifier import ModelStore, model_paths, severity_of  # noqa: E402
from common.mqtt import Link  # noqa: E402
from reports import build_pdf  # noqa: E402

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or "motosira-dev-key"
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

STATE_FILE = os.path.join(config.LOG_DIR, "dashboard_state.json")
TARGET_OF_MODE = {"real": "inmp441", "mock": "mock"}
store = ModelStore()
devices = {}                     # device id -> last status message (+ last_seen)
state = {"mode": config.DEFAULT_MODE if config.DEFAULT_MODE in config.MODES else "mock",
         "bike": config.PRIMARY_MODEL}


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
        if saved.get("mode") in config.MODES:
            state["mode"] = saved["mode"]
        if saved.get("bike") in config.MOTORCYCLE_MODELS:
            state["bike"] = saved["bike"]
    except (OSError, ValueError):
        pass


def save_state():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


# ─────────────────────────────── MQTT side ───────────────────────────────
def on_audio(msg):
    source = msg.get("source")
    mode = config.SOURCE_TO_MODE.get(source)
    feats = msg.get("features")
    if mode is None or not isinstance(feats, list) or len(feats) != config.N_FEATURES:
        print(f"[dashboard] ignored malformed audio message from {msg.get('device')}")
        return
    t0 = time.time()
    out = store.classify(mode, feats)
    pc_ms = int((time.time() - t0) * 1000)
    label, conf, probs = out if out else (None, None, {})
    sev = severity_of(label) if label else {"level": None, "text": ""}
    row = {
        "created_at": time.time(), "capture_id": msg.get("capture_id") or uuid.uuid4().hex,
        "device": msg.get("device"), "source": source, "mode": mode,
        "bike": msg.get("bike") if msg.get("bike") in config.MOTORCYCLE_MODELS else state["bike"],
        "classification": label, "confidence": conf, "severity": sev["level"], "probabilities": probs,
        "signal_quality": msg.get("signal_quality"), "quality_reason": msg.get("quality_reason"),
        "snr_db": msg.get("snr_db"), "peak_dbfs": msg.get("peak_dbfs"), "rpm": msg.get("rpm"),
        "feature_ms": msg.get("feature_ms"), "pc_ms": pc_ms, "e2e_ms": None,
        "model_trained": int(out is not None), "simulated_condition": msg.get("simulated_condition"),
        "envelope": msg.get("envelope") or [],
    }
    row_id = db.insert(row)
    result = {"id": row_id, "capture_id": row["capture_id"], "device": row["device"], "mode": mode,
              "classification": label, "confidence": conf, "severity": sev["level"],
              "severity_text": sev["text"], "probabilities": probs, "pc_ms": pc_ms,
              "model_trained": out is not None,
              "low_confidence": bool(conf is not None and conf < config.CONFIDENCE_WARN),
              "note": "" if out else f"{config.MODE_LABELS[mode]} model not trained yet"}
    link.publish(config.TOPIC_RESULT, result)
    full = db.get(row_id) if row_id else dict(row, id=None, time=time.strftime("%Y-%m-%d %H:%M:%S"))
    socketio.emit("result", dict(full, severity_text=sev["text"], low_confidence=result["low_confidence"]))
    print(f"[dashboard] #{row_id} {row['device']} ({config.MODE_LABELS[mode]}) {row['bike']}: "
          f"{(label or 'NOT CLASSIFIED').upper()} {'' if conf is None else f'{conf:.0%}'} "
          f"signal={row['signal_quality']} pc={pc_ms}ms")


def on_ack(msg):
    if msg.get("id") and msg.get("e2e_ms") is not None:
        db.set_e2e(msg["id"], msg["e2e_ms"])
        socketio.emit("ack", {"id": msg["id"], "e2e_ms": msg["e2e_ms"]})


def on_status(msg):
    dev = msg.get("device")
    if not dev:
        return
    devices[dev] = dict(msg, last_seen=time.time() if msg.get("online", True) else 0)
    socketio.emit("devices", device_list())


def device_list():
    now = time.time()
    out = []
    for dev, s in sorted(devices.items()):
        online = bool(s.get("online", True)) and now - s.get("last_seen", 0) < 10
        out.append({"device": dev, "source": s.get("source"), "online": online, "mic": s.get("mic"),
                    "busy": s.get("busy"), "edge_model": s.get("edge_model"), "rpm_sensor": s.get("rpm_sensor")})
    return out


def on_link_state(up):
    socketio.emit("broker", {"connected": up})


link = Link("dashboard", subscriptions={config.TOPIC_AUDIO: on_audio, config.TOPIC_ACK: on_ack,
                                        config.TOPIC_STATUS: on_status}, on_state=on_link_state)


def housekeeping():
    """Pick up newly trained models; refresh device online/offline status."""
    while True:
        before = {m: store.available(m) for m in config.MODES}
        store.reload_if_changed()
        if before != {m: store.available(m) for m in config.MODES}:
            socketio.emit("state", public_state())
        socketio.emit("devices", device_list())
        time.sleep(3)


def public_state():
    return {"mode": state["mode"], "bike": state["bike"], "modes": config.MODE_LABELS,
            "bikes": config.MOTORCYCLE_MODELS, "classes": config.CLASS_LABELS,
            "severity": config.SEVERITY, "models": {m: store.info(m) for m in config.MODES},
            "broker": {"connected": link.connected, "host": config.MQTT_BROKER, "port": config.MQTT_PORT},
            "devices": device_list(), "latency_target_ms": config.LATENCY_TARGET_MS,
            "confidence_warn": config.CONFIDENCE_WARN, "duration_s": config.DURATION}


# ─────────────────────────────── web side ───────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if auth.check(request.form.get("username", "").strip(), request.form.get("password", "")):
            session["user"] = request.form["username"].strip()
            return redirect(url_for("index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@auth.login_required
def index():
    return render_template("index.html")


@app.route("/api/state")
@auth.login_required
def api_state():
    return jsonify(public_state())


@app.route("/api/mode", methods=["POST"])
@auth.login_required
def api_mode():
    mode = (request.get_json(silent=True) or {}).get("mode")
    if mode not in config.MODES:
        return jsonify({"error": "unknown mode"}), 400
    state["mode"] = mode
    save_state()
    socketio.emit("state", public_state())
    return jsonify(public_state())


@app.route("/api/bike", methods=["POST"])
@auth.login_required
def api_bike():
    bike = (request.get_json(silent=True) or {}).get("bike")
    if bike not in config.MOTORCYCLE_MODELS:
        return jsonify({"error": "unknown motorcycle"}), 400
    state["bike"] = bike
    save_state()
    socketio.emit("state", public_state())
    return jsonify({"bike": bike})


@app.route("/api/capture", methods=["POST"])
@auth.login_required
def api_capture():
    data = request.get_json(silent=True) or {}
    target = TARGET_OF_MODE[state["mode"]]
    online = [d for d in device_list() if d["source"] == target and d["online"]]
    if not link.connected:
        return jsonify({"ok": False, "error": "MQTT broker not connected — start start_broker.bat"}), 503
    if not online:
        who = "Raspberry Pi (run ./run_pi.sh on the Pi)" if target == "inmp441" else \
            "simulated device (run start_mock_pi.bat)"
        return jsonify({"ok": False, "error": f"No {who} online."}), 409
    simulate = data.get("simulate") if data.get("simulate") in ["random"] + config.CLASSES else "random"
    cmd = {"action": "capture", "target": target, "bike": state["bike"], "simulate": simulate,
           "request_id": uuid.uuid4().hex}
    link.publish(config.TOPIC_COMMAND, cmd)
    return jsonify({"ok": True, "device": online[0]["device"], "request_id": cmd["request_id"]})


@app.route("/api/history")
@auth.login_required
def api_history():
    mode = request.args.get("mode")
    return jsonify(db.recent(int(request.args.get("limit", 50)), mode if mode in config.MODES else None))


@app.route("/api/stats")
@auth.login_required
def api_stats():
    return jsonify({m: db.stats(m) for m in config.MODES})


@app.route("/api/diagnosis/<int:row_id>")
@auth.login_required
def api_diagnosis(row_id):
    rec = db.get(row_id)
    return (jsonify(rec), 200) if rec else (jsonify({"error": "not found"}), 404)


@app.route("/api/report/<int:row_id>.pdf")
@auth.login_required
def api_report(row_id):
    rec = db.get(row_id)
    if not rec:
        return jsonify({"error": "not found"}), 404
    pdf = build_pdf(rec, store.info(rec["mode"]))
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=motosira_report_{row_id}.pdf"})


@app.route("/api/export.csv")
@auth.login_required
def api_export():
    mode = request.args.get("mode")
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = ["id", "time", "mode", "source", "device", "bike", "classification", "confidence", "severity",
            "signal_quality", "quality_reason", "snr_db", "peak_dbfs", "rpm", "feature_ms", "pc_ms", "e2e_ms",
            "simulated_condition"]
    w.writerow(cols)
    for r in db.all_rows(mode if mode in config.MODES else None):
        w.writerow([r.get(c) if r.get(c) is not None else "" for c in cols])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=motosira_sessions.csv"})


@app.route("/api/model/<mode>/confusion.png")
@auth.login_required
def api_confusion(mode):
    path = model_paths(mode)["confusion_png"] if mode in config.MODES else ""
    if not path or not os.path.exists(path):
        return jsonify({"error": "no confusion matrix — train this model first"}), 404
    return send_file(path, mimetype="image/png")


@app.route("/api/model/<mode>/metrics")
@auth.login_required
def api_metrics(mode):
    path = model_paths(mode)["metrics"] if mode in config.MODES else ""
    if not path or not os.path.exists(path):
        return jsonify({"error": "not trained"}), 404
    with open(path, encoding="utf-8") as fh:
        m = json.load(fh)
    m.pop("test_files", None)
    return jsonify(m)


def main():
    db.init_db()
    load_state()
    link.start()
    threading.Thread(target=housekeeping, daemon=True).start()
    print("=== MOTOSIRA Dashboard ===")
    for m in config.MODES:
        i = store.info(m)
        print(f"  {config.MODE_LABELS[m]:<18} model: " + (f"trained {i['trained_at']} ({', '.join(i['classes'])})"
                                                          if i["trained"] else "NOT TRAINED"))
    print(f"  Active mode: {config.MODE_LABELS[state['mode']]}   Broker: {config.MQTT_BROKER}:{config.MQTT_PORT}")
    print(f"  Open http://localhost:{config.DASHBOARD_PORT}  (login from .env)")
    socketio.run(app, host="0.0.0.0", port=config.DASHBOARD_PORT, debug=False, use_reloader=False,
                 allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()

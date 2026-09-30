"""
MOTOSIRA — Raspberry Pi application (3.5" TFT LCD, 480x320 touchscreen).

Flow (thesis Figure 3): hardware check -> ready screen -> select motorcycle ->
START -> record 3 s -> filter + MFCC -> send to PC -> result on the LCD
(condition, confidence, severity, RPM, latency) -> session saved to microSD.

If the PC does not answer within a few seconds (Wi-Fi down), the Pi classifies
on its own with the REAL model copy in model/trained/real/ ("EDGE" result).

    python pi_side/pi_app.py                    # fullscreen on the LCD
    python pi_side/pi_app.py --windowed         # normal window (testing)
    python pi_side/pi_app.py --console          # no screen (SSH)
    python pi_side/pi_app.py --fake-mic x.wav   # use a WAV file instead of the INMP441
"""
import argparse
import csv
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from common import audio
from common.classifier import ModelStore, severity_of
from common.mqtt import Link
from common.protocol import audio_message, offline_will, status_message
from pi_side.mic import Mic, MicError, RPMReader

SOURCE = "inmp441"
SHORT = {"Honda TMX 125 Alpha": "TMX 125 α", "Rusi Macho 125": "Macho 125", "Suzuki Smash Carb": "Smash"}


class FakeMic:
    """Plays a WAV file in 3-second slices instead of the INMP441 (testing without hardware)."""

    def __init__(self, path):
        self.path = path
        self.pos = 0
        self.audio = audio.load_wav(path)
        self.name = f"FAKE ({os.path.basename(path)})"

    def open(self):
        return {"device": "fake", "name": self.name, "rate": config.SAMPLE_RATE, "channels": 1}

    def record(self, seconds=config.DURATION):
        n = int(seconds * config.SAMPLE_RATE)
        if self.pos + n > len(self.audio):
            self.pos = 0
        clip = self.audio[self.pos:self.pos + n]
        self.pos += n
        time.sleep(seconds)          # behave like a real recording
        return clip


class Controller:
    def __init__(self, fake_mic=None):
        self.events = queue.Queue()
        self.mic = FakeMic(fake_mic) if fake_mic else Mic()
        self.rpm = RPMReader()
        self.store = ModelStore()               # local REAL model copy for EDGE fallback
        self.bike = config.PRIMARY_MODEL
        self.busy = False
        self.mic_ok = False
        self.mic_msg = "checking microphone..."
        self.linked = False
        self._pending = {}
        self._lock = threading.Lock()
        self.link = Link("pi", subscriptions={config.TOPIC_RESULT: self._on_result,
                                              config.TOPIC_COMMAND: self._on_command},
                         will=(config.TOPIC_STATUS, offline_will(config.DEVICE_ID, SOURCE)),
                         on_state=self._on_link)

    # ── lifecycle ──
    def start(self):
        self.link.start()
        threading.Thread(target=self.check_hardware, daemon=True).start()
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def emit(self, kind, **data):
        self.events.put((kind, data))

    def check_hardware(self):
        self.emit("hw", ok=None, msg="Checking microphone...")
        try:
            info = self.mic.open()
            audio.warm_up()
            self.mic_ok, self.mic_msg = True, "ok"
            self.emit("hw", ok=True, msg=f"Mic: {info['name']} @ {info['rate']} Hz")
            print(f"[pi] microphone ready: {info}")
        except MicError as exc:
            self.mic_ok, self.mic_msg = False, str(exc)
            self.emit("hw", ok=False, msg=str(exc))
            print(f"[pi] HARDWARE NOT READY: {exc}")
        except Exception as exc:  # unexpected driver errors
            self.mic_ok, self.mic_msg = False, f"Microphone error: {exc}"
            self.emit("hw", ok=False, msg=self.mic_msg)
            print(f"[pi] HARDWARE NOT READY: {exc}")
        self._send_status()

    def _heartbeat(self):
        while True:
            self._send_status()
            self.store.reload_if_changed()
            time.sleep(3)

    def _send_status(self):
        if self.linked:
            self.link.publish(config.TOPIC_STATUS, status_message(
                config.DEVICE_ID, SOURCE, mic="ok" if self.mic_ok else self.mic_msg, busy=self.busy,
                bike=self.bike, extra={"edge_model": self.store.available("real"),
                                       "rpm_sensor": self.rpm.status}), qos=0)

    def _on_link(self, up):
        self.linked = up
        self.emit("link", up=up)
        if up:
            threading.Thread(target=self._send_status, daemon=True).start()

    # ── MQTT handlers (MQTT thread) ──
    def _on_result(self, data):
        with self._lock:
            slot = self._pending.get(data.get("capture_id"))
        if slot:
            slot["result"] = data
            slot["event"].set()

    def _on_command(self, data):
        if data.get("action") != "capture" or data.get("target") not in (SOURCE, "any"):
            return
        if data.get("device") not in (None, config.DEVICE_ID):
            return
        if data.get("bike") in config.MOTORCYCLE_MODELS:
            self.set_bike(data["bike"])
        self.capture(request_id=data.get("request_id"))

    # ── actions ──
    def set_bike(self, bike):
        self.bike = bike
        self.emit("bike", bike=bike)

    def capture(self, request_id=None):
        if self.busy:
            return False
        if not self.mic_ok:
            self.emit("hw", ok=False, msg=self.mic_msg)
            return False
        self.busy = True
        threading.Thread(target=self._run, args=(request_id,), daemon=True).start()
        return True

    def _run(self, request_id):
        try:
            self.emit("state", state="RECORDING")
            self.rpm.start()
            samples = self.mic.record(config.DURATION)
            t_end = time.time()
            rpm = self.rpm.read()
            self.emit("state", state="ANALYZING")
            t0 = time.time()
            analysis = audio.analyze(samples)
            feature_ms = (time.time() - t0) * 1000
            msg = audio_message(config.DEVICE_ID, SOURCE, self.bike, analysis, feature_ms,
                                rpm=rpm, request_id=request_id)
            slot = {"event": threading.Event(), "result": None}
            with self._lock:
                self._pending[msg["capture_id"]] = slot
            sent = self.linked and self.link.publish(config.TOPIC_AUDIO, msg)
            if sent:
                slot["event"].wait(config.RESULT_TIMEOUT_S)
            with self._lock:
                self._pending.pop(msg["capture_id"], None)
            result = slot["result"]
            if result is not None:
                result = dict(result, classified_by="pc")
            else:
                result = self._edge(msg, sent)
            e2e_ms = int((time.time() - t_end) * 1000)
            result.update({"e2e_ms": e2e_ms, "feature_ms": int(feature_ms), "rpm": rpm, "bike": self.bike,
                           "signal_quality": analysis["signal_quality"],
                           "quality_reason": analysis["quality_reason"], "snr_db": analysis["snr_db"]})
            if result["classified_by"] == "pc":
                self.link.publish(config.TOPIC_ACK, {"capture_id": msg["capture_id"], "id": result.get("id"),
                                                     "device": config.DEVICE_ID, "e2e_ms": e2e_ms})
            self._log(msg["capture_id"], result)
            self.emit("result", **result)
        except Exception as exc:
            print(f"[pi] capture failed: {exc}")
            self.emit("error", msg=f"Capture failed: {exc}")
        finally:
            self.busy = False
            self._send_status()

    def _edge(self, msg, sent):
        why = "PC did not answer" if sent else "not connected to PC"
        out = self.store.classify("real", msg["features"])
        if out is None:
            return {"classification": None, "classified_by": "none",
                    "note": f"{why}; no local REAL model on the Pi"}
        label, conf, probs = out
        sev = severity_of(label)
        return {"classification": label, "confidence": conf, "severity": sev["level"],
                "severity_text": sev["text"], "classified_by": "edge", "mode": "real",
                "low_confidence": conf < config.CONFIDENCE_WARN, "note": f"EDGE: {why}"}

    def _log(self, capture_id, r):
        """Session log on the Pi's microSD (thesis Obj. 5)."""
        os.makedirs(config.LOG_DIR, exist_ok=True)
        new = not os.path.exists(config.PI_SESSION_LOG)
        with open(config.PI_SESSION_LOG, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["timestamp", "device", "bike", "classification", "confidence", "severity",
                            "signal_quality", "snr_db", "rpm", "feature_ms", "pc_ms", "e2e_ms",
                            "classified_by", "capture_id"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), config.DEVICE_ID, r.get("bike"),
                        r.get("classification") or "", r.get("confidence") or "", r.get("severity", ""),
                        r.get("signal_quality"), r.get("snr_db"), r.get("rpm") or "", r.get("feature_ms"),
                        r.get("pc_ms") or "", r.get("e2e_ms"), r.get("classified_by"), capture_id])


# ─────────────────────────── LCD user interface ───────────────────────────
BG, PANEL, LINE = "#14120F", "#1F1B15", "#332C1F"
AMBER, GREEN, RED, RUST, TEXT, MUTED = "#FFB020", "#4CE66B", "#FF3B30", "#E8752C", "#F3EEE2", "#8C8372"
COLOR = {"normal": GREEN, "valve_ticking": AMBER, "misfire": RUST, "knocking": RED}


class LcdUI:
    def __init__(self, ctl, fullscreen=True):
        import tkinter as tk
        self.tk, self.ctl = tk, ctl
        self.root = tk.Tk()
        self.root.title("MOTOSIRA")
        self.root.configure(bg=BG)
        self.root.geometry("480x320+0+0")
        if fullscreen:
            self.root.attributes("-fullscreen", True)
            self.root.config(cursor="none")
        f = "DejaVu Sans"
        self.F = {"xs": (f, 8), "s": (f, 10), "m": (f, 12, "bold"), "l": (f, 15, "bold"), "xl": (f, 26, "bold")}
        self.countdown = 0
        self._build()
        self.root.bind("<space>", lambda e: self.start())
        self.root.bind("<Return>", lambda e: self.start())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        for i, bike in enumerate(config.MOTORCYCLE_MODELS, 1):
            self.root.bind(str(i), lambda e, b=bike: self.ctl.set_bike(b))
        self.root.after(100, self._poll)

    def _label(self, parent, text, font, fg=TEXT, **kw):
        return self.tk.Label(parent, text=text, font=self.F[font], fg=fg, bg=kw.pop("bg", BG), **kw)

    def _build(self):
        tk = self.tk
        top = tk.Frame(self.root, bg=PANEL, height=30)
        top.pack(fill="x")
        self._label(top, "MOTOSIRA", "m", AMBER, bg=PANEL).pack(side="left", padx=8, pady=4)
        self.link_lbl = self._label(top, "PC: connecting", "xs", MUTED, bg=PANEL)
        self.link_lbl.pack(side="right", padx=8)
        self.mic_lbl = self._label(top, "MIC: checking", "xs", MUTED, bg=PANEL)
        self.mic_lbl.pack(side="right", padx=4)

        bikes = tk.Frame(self.root, bg=BG)
        bikes.pack(fill="x", padx=6, pady=(6, 2))
        self.bike_btns = {}
        for bike in config.MOTORCYCLE_MODELS:
            b = tk.Button(bikes, text=SHORT[bike], font=self.F["s"], relief="flat", bd=0,
                          activebackground=AMBER, command=lambda x=bike: self.ctl.set_bike(x))
            b.pack(side="left", expand=True, fill="x", padx=2, ipady=5)
            self.bike_btns[bike] = b
        self._paint_bikes()

        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill="both", expand=True)
        self.big = self._label(mid, "READY", "xl", AMBER)
        self.big.pack(pady=(8, 0))
        self.sub = self._label(mid, "Mic ~30 cm from engine block, engine at idle", "s", MUTED, wraplength=460)
        self.sub.pack()

        cells = tk.Frame(self.root, bg=BG)
        cells.pack(fill="x", padx=6)
        self.vals = {}
        for key, cap in (("conf", "CONFIDENCE"), ("sev", "SEVERITY"), ("rpm", "RPM"),
                         ("lat", "LATENCY"), ("sig", "SIGNAL")):
            c = tk.Frame(cells, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            c.pack(side="left", expand=True, fill="both", padx=2)
            self._label(c, cap, "xs", MUTED, bg=PANEL).pack(pady=(2, 0))
            v = self._label(c, "—", "m", TEXT, bg=PANEL)
            v.pack(pady=(0, 3))
            self.vals[key] = v

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=6, pady=6)
        self.start_btn = tk.Button(bottom, text="START DIAGNOSIS", font=self.F["l"], bg=AMBER, fg="#1a1200",
                                   activebackground="#ffc85a", relief="flat", bd=0, command=self.start)
        self.start_btn.pack(side="left", expand=True, fill="x", ipady=8)
        tk.Button(bottom, text="EXIT", font=self.F["xs"], bg=PANEL, fg=MUTED, relief="flat", bd=0,
                  command=self.root.destroy).pack(side="right", padx=(6, 0), ipady=8, ipadx=6)

        # Hardware-not-ready overlay (thesis flowchart: "Hardware Ready? NO -> Display Error Message")
        self.err = tk.Frame(self.root, bg="#2A0906")
        self._label(self.err, "HARDWARE NOT READY", "l", RED, bg="#2A0906").pack(pady=(24, 8))
        self.err_msg = self._label(self.err, "", "s", TEXT, bg="#2A0906", wraplength=440, justify="left")
        self.err_msg.pack(padx=16)
        row = tk.Frame(self.err, bg="#2A0906")
        row.pack(side="bottom", pady=14)
        tk.Button(row, text="RETRY", font=self.F["m"], bg=AMBER, fg="#1a1200", relief="flat",
                  command=lambda: threading.Thread(target=self.ctl.check_hardware, daemon=True).start()
                  ).pack(side="left", padx=8, ipadx=16, ipady=6)
        tk.Button(row, text="EXIT", font=self.F["s"], bg=PANEL, fg=MUTED, relief="flat",
                  command=self.root.destroy).pack(side="left", padx=8, ipadx=10, ipady=6)

    def _paint_bikes(self):
        for bike, b in self.bike_btns.items():
            on = bike == self.ctl.bike
            b.configure(bg=AMBER if on else PANEL, fg="#1a1200" if on else TEXT)

    def start(self):
        if self.ctl.capture():
            self.start_btn.configure(state="disabled", bg=LINE)

    def _tick(self):
        if self.countdown > 0:
            self.big.configure(text=f"RECORDING {self.countdown}", fg=AMBER)
            self.countdown -= 1
            self.root.after(1000, self._tick)

    def _poll(self):
        try:
            while True:
                kind, d = self.ctl.events.get_nowait()
                getattr(self, f"_on_{kind}", lambda **k: None)(**d)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    # ── event handlers ──
    def _on_hw(self, ok, msg):
        if ok is False:
            self.err_msg.configure(text=msg)
            self.err.place(x=0, y=0, relwidth=1, relheight=1)
            self.mic_lbl.configure(text="MIC: ERROR", fg=RED)
        elif ok:
            self.err.place_forget()
            self.mic_lbl.configure(text="MIC: OK", fg=GREEN)
            self.big.configure(text="READY", fg=AMBER)
            self.sub.configure(text="Select motorcycle, then START", fg=MUTED)
        else:
            self.mic_lbl.configure(text="MIC: checking", fg=MUTED)

    def _on_link(self, up):
        self.link_lbl.configure(text="PC: ONLINE" if up else "PC: OFFLINE", fg=GREEN if up else RUST)

    def _on_bike(self, bike):
        self._paint_bikes()

    def _on_state(self, state):
        for v in self.vals.values():
            v.configure(text="—", fg=TEXT)
        if state == "RECORDING":
            self.start_btn.configure(state="disabled", bg=LINE)
            self.sub.configure(text=f"Capturing engine sound — {self.ctl.bike}", fg=MUTED)
            self.countdown = config.DURATION
            self._tick()
        else:
            self.countdown = 0
            self.big.configure(text="ANALYZING…", fg=AMBER)
            self.sub.configure(text="Low-pass filter → MFCC → Random Forest", fg=MUTED)

    def _on_error(self, msg):
        self.big.configure(text="ERROR", fg=RED)
        self.sub.configure(text=msg, fg=RED)
        self.start_btn.configure(state="normal", bg=AMBER)

    def _on_result(self, **r):
        self.start_btn.configure(state="normal", bg=AMBER)
        label = r.get("classification")
        notes = []
        if label:
            self.big.configure(text=config.CLASS_LABELS[label], fg=COLOR.get(label, TEXT))
            conf = r.get("confidence") or 0
            self.vals["conf"].configure(text=f"{conf * 100:.0f}%", fg=RUST if conf < config.CONFIDENCE_WARN else TEXT)
            self.vals["sev"].configure(text=f"{r.get('severity')}/3", fg=COLOR.get(label, TEXT))
            notes.append(r.get("severity_text", ""))
            if r.get("low_confidence"):
                notes.append("Low confidence — re-record")
        else:
            self.big.configure(text="NOT CLASSIFIED", fg=MUTED)
            notes.append(r.get("note") or "Model not trained yet")
        self.vals["rpm"].configure(text=str(r["rpm"]) if r.get("rpm") else "N/A")
        e2e = r.get("e2e_ms") or 0
        self.vals["lat"].configure(text=f"{e2e / 1000:.2f}s", fg=GREEN if e2e <= config.LATENCY_TARGET_MS else RUST)
        good = r.get("signal_quality") == "GOOD"
        self.vals["sig"].configure(text="GOOD" if good else "NOISE", fg=GREEN if good else RUST)
        if not good:
            notes.append(f"Check noise: {r.get('quality_reason')}")
        if r.get("classified_by") == "edge":
            notes.append("EDGE mode (PC offline)")
        if r.get("mode") == "mock":
            notes.append("DEMO model")
        self.sub.configure(text=" · ".join(n for n in notes if n), fg=MUTED)

    def run(self):
        self.root.mainloop()


class ConsoleUI:
    def __init__(self, ctl):
        self.ctl = ctl

    def run(self):
        print("\nMOTOSIRA Pi (console). ENTER = start diagnosis, 1/2/3 = motorcycle, q = quit\n")
        threading.Thread(target=self._keys, daemon=True).start()
        while True:
            kind, d = self.ctl.events.get()
            if kind == "quit":
                return
            if kind == "result":
                label = d.get("classification")
                if label:
                    print(f"  RESULT [{d['classified_by'].upper()}] {config.CLASS_LABELS[label]} "
                          f"{d['confidence'] * 100:.0f}%  severity {d['severity']}/3  signal {d['signal_quality']} "
                          f"SNR {d['snr_db']} dB  RPM {d.get('rpm') or 'N/A'}  latency {d['e2e_ms']} ms")
                else:
                    print(f"  NOT CLASSIFIED — {d.get('note')}  (signal {d['signal_quality']}, "
                          f"latency {d['e2e_ms']} ms)")
            else:
                print(f"  [{kind}] {d}")

    def _keys(self):
        for line in sys.stdin:
            line = line.strip().lower()
            if line == "q":
                self.ctl.emit("quit")
                return
            if line in ("1", "2", "3"):
                self.ctl.set_bike(config.MOTORCYCLE_MODELS[int(line) - 1])
            elif not self.ctl.capture():
                print("  (busy or microphone not ready)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--console", action="store_true", help="no GUI (SSH)")
    ap.add_argument("--windowed", action="store_true", help="window instead of fullscreen")
    ap.add_argument("--fake-mic", help="WAV file used instead of the INMP441 (testing)")
    a = ap.parse_args()
    print(f"MOTOSIRA Pi app — device {config.DEVICE_ID}, broker {config.MQTT_BROKER}:{config.MQTT_PORT}")
    ctl = Controller(fake_mic=a.fake_mic)
    ui = None
    if not a.console:
        try:
            ui = LcdUI(ctl, fullscreen=not a.windowed)
        except Exception as exc:
            print(f"No display available ({exc}); using console mode.")
    ctl.start()
    (ui or ConsoleUI(ctl)).run()
    ctl.link.stop()


if __name__ == "__main__":
    main()

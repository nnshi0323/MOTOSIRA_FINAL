"""
MOTOSIRA — SIMULATED device for DEMO mode (runs on the dashboard PC, no hardware).

It behaves exactly like the Pi on the network: answers the dashboard's START
button, runs the SAME filter + MFCC code, sends features over MQTT, receives
the result and reports end-to-end latency. Audio comes from common/mock_audio.py
(synthetic), and the dashboard classifies it with the DEMO model only.

    python pi_side/mock_pi.py                 # wait for START from the dashboard
    python pi_side/mock_pi.py --auto 6        # also send a capture every 6 s
"""
import argparse
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from common import audio, mock_audio
from common.mqtt import Link
from common.protocol import audio_message, offline_will, status_message

SOURCE = "mock"
DEVICE = "mock-01"


class MockDevice:
    def __init__(self):
        self.busy = False
        self.bike = config.PRIMARY_MODEL
        self._pending = {}
        self.link = Link("mock", subscriptions={config.TOPIC_COMMAND: self.on_command,
                                                config.TOPIC_RESULT: self.on_result},
                         will=(config.TOPIC_STATUS, offline_will(DEVICE, SOURCE)))

    def start(self):
        self.link.start()
        audio.warm_up()
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def _heartbeat(self):
        while True:
            if self.link.connected:
                self.link.publish(config.TOPIC_STATUS, status_message(
                    DEVICE, SOURCE, busy=self.busy, bike=self.bike, extra={"simulated": True}), qos=0)
            time.sleep(3)

    def on_command(self, data):
        if data.get("action") == "capture" and data.get("target") in (SOURCE, "any"):
            if data.get("bike") in config.MOTORCYCLE_MODELS:
                self.bike = data["bike"]
            self.capture(data.get("simulate") or "random", data.get("request_id"))

    def on_result(self, data):
        slot = self._pending.get(data.get("capture_id"))
        if slot:
            slot["r"] = data
            slot["e"].set()

    def capture(self, simulate="random", request_id=None):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._run, args=(simulate, request_id), daemon=True).start()

    def _run(self, simulate, request_id):
        try:
            condition = random.choice(config.CLASSES) if simulate == "random" else simulate
            print(f"[mock] simulating {condition.upper()} on {self.bike} ({config.DURATION} s)...")
            clip = mock_audio.generate(condition, bike=self.bike)
            time.sleep(config.DURATION)                      # same timing as a real capture
            t_end = time.time()
            t0 = time.time()
            analysis = audio.analyze(clip)
            feature_ms = (time.time() - t0) * 1000
            msg = audio_message(DEVICE, SOURCE, self.bike, analysis, feature_ms,
                                request_id=request_id, simulated_condition=condition)
            slot = {"e": threading.Event(), "r": None}
            self._pending[msg["capture_id"]] = slot
            if not self.link.publish(config.TOPIC_AUDIO, msg):
                print("[mock] not connected to broker")
            slot["e"].wait(config.RESULT_TIMEOUT_S)
            self._pending.pop(msg["capture_id"], None)
            e2e = int((time.time() - t_end) * 1000)
            r = slot["r"]
            if r is None:
                print("[mock] no answer from dashboard (is it running?)")
                return
            self.link.publish(config.TOPIC_ACK, {"capture_id": msg["capture_id"], "id": r.get("id"),
                                                 "device": DEVICE, "e2e_ms": e2e})
            got = r.get("classification") or "NOT CLASSIFIED"
            print(f"[mock]   -> {str(got).upper()} ({(r.get('confidence') or 0) * 100:.0f}%)  "
                  f"latency {e2e} ms")
        finally:
            self.busy = False


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", type=float, default=0, help="seconds between automatic captures (0 = off)")
    ap.add_argument("--simulate", default="random", choices=["random"] + config.CLASSES)
    a = ap.parse_args()
    print(f"MOTOSIRA SIMULATED device '{DEVICE}' — broker {config.MQTT_BROKER}:{config.MQTT_PORT}")
    print("Waiting for START from the dashboard (DEMO mode). Ctrl+C to stop.")
    dev = MockDevice()
    dev.start()
    try:
        while True:
            if a.auto > 0:
                time.sleep(a.auto)
                dev.capture(a.simulate)
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        dev.link.stop()

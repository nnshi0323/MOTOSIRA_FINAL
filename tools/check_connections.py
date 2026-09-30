"""
MOTOSIRA — connection check. Run on the PC or the Pi; it says exactly what is wrong.

    python tools/check_connections.py
"""
import os
import platform
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

OK, WARN, FAIL = "[ OK ]", "[WARN]", "[FAIL]"
fails = 0
IS_PI = os.path.exists("/proc/device-tree/model") and "raspberry" in open(
    "/proc/device-tree/model", errors="ignore").read().lower()


def say(level, msg):
    global fails
    fails += level == FAIL
    print(f"{level} {msg}")


def check_python():
    v = sys.version_info
    say(OK if v >= (3, 11) else FAIL, f"Python {v.major}.{v.minor}.{v.micro} ({platform.machine()})")
    need = ["numpy", "scipy", "librosa", "sklearn", "joblib", "soundfile", "paho.mqtt", "dotenv"]
    need += ["sounddevice"] if IS_PI else ["flask", "flask_socketio", "reportlab", "matplotlib"]
    missing = []
    for mod in need:
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    say(FAIL if missing else OK, f"packages: {'missing ' + ', '.join(missing) if missing else 'all installed'}")
    if missing:
        print("       Fix: run setup_pi.sh (Pi) or setup_pc.bat (PC) again.")


def check_env():
    path = os.path.join(config.BASE_DIR, ".env")
    say(OK if os.path.exists(path) else WARN,
        f".env {'found' if os.path.exists(path) else 'missing — run tools/make_env.py'}; "
        f"broker = {config.MQTT_BROKER}:{config.MQTT_PORT}")
    if IS_PI and config.MQTT_BROKER in ("localhost", "127.0.0.1"):
        say(WARN, "On the Pi the broker must be the PC's IP: python tools/make_env.py --broker <PC IP>")


def check_broker():
    try:
        with socket.create_connection((config.MQTT_BROKER, config.MQTT_PORT), timeout=3):
            pass
    except OSError as exc:
        say(FAIL, f"cannot reach {config.MQTT_BROKER}:{config.MQTT_PORT} ({exc})")
        print("       PC: is start_broker.bat running (as administrator)?")
        print("       Pi: is MOTOSIRA_BROKER the PC's IP, and are both on the SAME Wi-Fi/hotspot?")
        print("       School Wi-Fi often blocks device-to-device traffic: use a phone hotspot.")
        return
    say(OK, f"TCP connection to broker {config.MQTT_BROKER}:{config.MQTT_PORT}")
    from common.mqtt import Link
    got = threading.Event()
    topic = f"motosira/selftest/{os.getpid()}"
    link = Link("check", subscriptions={topic: lambda d: got.set()}).start()
    if not link.wait_connected(5):
        say(FAIL, "broker reachable but MQTT handshake failed (check mosquitto.conf: allow_anonymous true)")
        return
    time.sleep(0.3)
    link.publish(topic, {"ping": 1})
    say(OK if got.wait(3) else FAIL, "MQTT publish/subscribe round trip")
    seen = {}
    link.subscriptions[config.TOPIC_STATUS] = lambda d: seen.__setitem__(d.get("device"), d)
    link.client.subscribe(config.TOPIC_STATUS)
    time.sleep(7)          # devices send a heartbeat every 3 s
    for dev, st in seen.items():
        if st.get("online", True):
            say(OK, f"device online: {dev} ({st.get('source')}), mic: {st.get('mic')}")
    if not seen:
        say(WARN, "no MOTOSIRA device heartbeat seen yet (start the Pi app or start_mock_pi.bat)")
    link.stop()


def check_mic():
    if not IS_PI:
        return
    try:
        with open("/boot/firmware/config.txt", encoding="utf-8", errors="ignore") as fh:
            cfg = fh.read()
    except OSError:
        cfg = ""
    lines = [l.strip() for l in cfg.splitlines() if l.strip() and not l.strip().startswith("#")]
    ov = [l for l in lines if "googlevoicehat-soundcard" in l]
    bad = [l for l in lines if "simple-audio-card" in l]
    say(OK if ov else FAIL, "config.txt: dtoverlay=googlevoicehat-soundcard " + ("present" if ov else "MISSING"))
    if bad:
        say(FAIL, f"config.txt has an invalid overlay line: {bad[0]}")
    if not ov or bad:
        print("       Fix: sudo python3 tools/fix_boot_config.py && sudo reboot")
    try:
        from pi_side.mic import Mic, MicError
        m = Mic()
        info = m.open()
        say(OK, f"INMP441 capturing: {info['name']} @ {info['rate']} Hz x{info['channels']}")
        from common import audio
        clip = m.record(1.0)
        q, snr, peak = audio.signal_quality(audio.preprocess(clip))
        say(OK if peak > config.SIGNAL_TOO_QUIET_DBFS else WARN,
            f"1 s test: peak {peak} dBFS, SNR {snr} dB (tap the mic to see the peak rise)")
    except MicError as exc:
        say(FAIL, f"microphone: {exc}")
    except Exception as exc:
        say(FAIL, f"microphone error: {exc}")


def check_models():
    from common.classifier import ModelStore
    store = ModelStore()
    for mode in config.MODES:
        i = store.info(mode)
        say(OK if i["trained"] else WARN,
            f"{config.MODE_LABELS[mode]} model: " + (f"trained {i['trained_at']}" if i["trained"] else "not trained"))


if __name__ == "__main__":
    print(f"=== MOTOSIRA connection check ({'Raspberry Pi' if IS_PI else 'PC'}) ===")
    check_python()
    check_env()
    check_broker()
    check_mic()
    check_models()
    print("=" * 40)
    print("All required checks passed." if fails == 0 else f"{fails} problem(s) — fix the [FAIL] lines above.")
    sys.exit(1 if fails else 0)

"""
MOTOSIRA — MQTT message formats (one place, used by the Pi, mock device and dashboard).

motosira/audio   device -> PC   features of one 3-second capture
motosira/result  PC -> device   classification result for that capture
motosira/ack     device -> PC   end-to-end latency measured on the device
motosira/command PC -> device   {"action": "capture", "target": "inmp441"|"mock", ...}
motosira/status  device -> PC   heartbeat every 3 s; "online": false is the MQTT last will
"""
import time
import uuid

PROTOCOL_VERSION = 3


def audio_message(device, source, bike, analysis, feature_ms, rpm=None, request_id=None,
                  simulated_condition=None):
    return {
        "v": PROTOCOL_VERSION,
        "capture_id": uuid.uuid4().hex,
        "request_id": request_id,
        "device": device,
        "source": source,                       # "inmp441" (real) or "mock" (simulated)
        "bike": bike,
        "features": [round(float(v), 5) for v in analysis["features"]],
        "signal_quality": analysis["signal_quality"],
        "quality_reason": analysis["quality_reason"],
        "snr_db": analysis["snr_db"],
        "peak_dbfs": analysis["peak_dbfs"],
        "envelope": analysis["envelope"],
        "rpm": rpm,
        "feature_ms": int(feature_ms),
        "captured_at": time.time(),
        "simulated_condition": simulated_condition,
    }


def status_message(device, source, online=True, mic="ok", busy=False, bike=None, extra=None):
    msg = {"v": PROTOCOL_VERSION, "device": device, "source": source, "online": online,
           "mic": mic, "busy": busy, "bike": bike, "ts": time.time()}
    if extra:
        msg.update(extra)
    return msg


def offline_will(device, source):
    return {"v": PROTOCOL_VERSION, "device": device, "source": source, "online": False, "ts": None}

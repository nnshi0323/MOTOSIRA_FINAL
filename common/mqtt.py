"""
MOTOSIRA — shared MQTT helper (paho-mqtt 2.x, Callback API v2).

Every program (dashboard, Pi app, simulated device, checker) connects through
this module, so reconnect behaviour is identical everywhere:
  * start order does not matter (keeps retrying until the broker is up)
  * reconnects automatically after Wi-Fi drops or a broker restart
  * subscriptions are re-applied on every (re)connect
"""
import json
import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt  # type: ignore

import config


class Link:
    """Small wrapper: Link(name, subscriptions={topic: handler}, will=(topic, payload))."""

    def __init__(self, name, subscriptions=None, will=None, on_state=None):
        self.name = name
        self.subscriptions = subscriptions or {}
        self.on_state = on_state            # callback(bool connected)
        self.connected = False
        self._lock = threading.Lock()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"motosira-{name}-{uuid.uuid4().hex[:6]}")
        self.client.reconnect_delay_set(min_delay=1, max_delay=5)
        if will:
            self.client.will_set(will[0], json.dumps(will[1]), qos=1, retain=False)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    # ── callbacks ──
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[{self.name}] MQTT refused: {reason_code}")
            return
        self.connected = True
        for topic in self.subscriptions:
            client.subscribe(topic, qos=1)
        print(f"[{self.name}] MQTT connected to {config.MQTT_BROKER}:{config.MQTT_PORT}")
        if self.on_state:
            self.on_state(True)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        was = self.connected
        self.connected = False
        if was:
            print(f"[{self.name}] MQTT disconnected ({reason_code}) — reconnecting automatically...")
        if self.on_state:
            self.on_state(False)

    def _on_message(self, client, userdata, msg):
        handler = self.subscriptions.get(msg.topic)
        if handler is None:
            return
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            print(f"[{self.name}] ignored non-JSON message on {msg.topic}")
            return
        try:
            handler(data)
        except Exception as exc:  # never let one bad message kill the MQTT thread
            print(f"[{self.name}] error handling {msg.topic}: {exc}")

    # ── public API ──
    def start(self):
        """Non-blocking. Retries in the background until the broker is reachable."""
        self.client.connect_async(config.MQTT_BROKER, config.MQTT_PORT, keepalive=20)
        self.client.loop_start()
        return self

    def wait_connected(self, timeout):
        end = time.time() + timeout
        while time.time() < end and not self.connected:
            time.sleep(0.1)
        return self.connected

    def publish(self, topic, data, qos=1, retain=False):
        with self._lock:
            info = self.client.publish(topic, json.dumps(data), qos=qos, retain=retain)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

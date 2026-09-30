"""
MOTOSIRA — INMP441 microphone access (Raspberry Pi 4, googlevoicehat-soundcard overlay).

The overlay exposes the INMP441 as ALSA card "sndrpigooglevoi" that ONLY supports
48 kHz, 2 channels, S32_LE. With L/R tied to GND the mic is on the LEFT channel,
as 24-bit data in the top bits of each 32-bit frame. This module:
  * finds that device (or the one named in MOTOSIRA_MIC_DEVICE)
  * opens it in a format it accepts (48k/2ch first, then fallbacks)
  * returns mono float32 audio resampled to 22,050 Hz for the shared pipeline
  * explains failures in plain words (missing overlay, wiring, busy device)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # type: ignore

import config
from common import audio

FORMATS = [(config.CAPTURE_RATE, config.CAPTURE_CHANNELS), (48000, 2), (48000, 1), (44100, 2), (44100, 1)]


class MicError(Exception):
    pass


class Mic:
    def __init__(self):
        self.device = None
        self.name = None
        self.rate = None
        self.channels = None

    @staticmethod
    def _sd():
        try:
            import sounddevice as sd  # type: ignore
            return sd
        except OSError as exc:  # PortAudio library missing
            raise MicError(f"PortAudio not available ({exc}). Run setup_pi.sh (installs libportaudio2).")

    def list_inputs(self):
        sd = self._sd()
        return [(i, d["name"], d["max_input_channels"], int(d["default_samplerate"]))
                for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]

    def find(self):
        inputs = self.list_inputs()
        want = config.MIC_DEVICE
        if want:
            for i, name, *_ in inputs:
                if (want.isdigit() and i == int(want)) or want.lower() in name.lower():
                    return i, name
            raise MicError(f"MOTOSIRA_MIC_DEVICE='{want}' not found. Inputs: {[n for _, n, *_ in inputs]}")
        for i, name, *_ in inputs:
            if any(h in name.lower() for h in config.MIC_NAME_HINTS):
                return i, name
        if not inputs:
            raise MicError("No microphone found. Check /boot/firmware/config.txt has "
                           "'dtoverlay=googlevoicehat-soundcard', reboot, then run 'arecord -l'.")
        raise MicError("INMP441 (googlevoicehat) card not found. Inputs seen: "
                       f"{[n for _, n, *_ in inputs]}. Run: sudo python3 tools/fix_boot_config.py, then reboot.")

    def _read(self, seconds, rate, channels):
        sd = self._sd()
        frames = int(seconds * rate)
        block = sd.rec(frames, samplerate=rate, channels=channels, dtype="int32", device=self.device)
        sd.wait()
        return block[:, 0] if block.ndim > 1 else block.reshape(-1)

    def open(self):
        """Find the mic and confirm it delivers real audio. Raises MicError with advice."""
        self.device, self.name = self.find()
        last = None
        for rate, ch in dict.fromkeys(FORMATS):
            try:
                raw = self._read(0.4, rate, ch)
                self.rate, self.channels = rate, ch
                break
            except Exception as exc:
                last = exc
                if "busy" in str(exc).lower() or "unavailable" in str(exc).lower():
                    time.sleep(0.5)
        else:
            raise MicError(f"Mic found ({self.name}) but could not be opened: {last}. "
                           "Close other programs using it (arecord, browser tabs) and retry.")
        if not np.any(raw):
            raise MicError("Mic opened but returns only zeros. Check wiring: SD->pin 38 (GPIO20), "
                           "SCK->pin 12 (GPIO18), WS->pin 35 (GPIO19), VDD->pin 1 (3.3V), L/R->GND.")
        return {"device": self.device, "name": self.name, "rate": self.rate, "channels": self.channels}

    def record(self, seconds=config.DURATION):
        """Mono float32 at config.SAMPLE_RATE."""
        if self.rate is None:
            self.open()
        raw = self._read(seconds, self.rate, self.channels)
        return audio.resample(audio.i2s_frames_to_float(raw), self.rate, config.SAMPLE_RATE)


class RPMReader:
    """Optional Hall-effect RPM sensor (disabled unless MOTOSIRA_RPM_ENABLED=1).
    Counts pulses during the capture window using gpiozero, if available."""

    def __init__(self):
        self.device = None
        self.count = 0
        self.status = "disabled"
        if not config.RPM_SENSOR_ENABLED:
            return
        try:
            from gpiozero import DigitalInputDevice  # type: ignore
            self.device = DigitalInputDevice(config.RPM_GPIO_PIN, pull_up=True)
            self.device.when_deactivated = self._pulse
            self.status = f"GPIO{config.RPM_GPIO_PIN}"
        except Exception as exc:
            self.status = f"unavailable ({exc})"

    def _pulse(self):
        self.count += 1

    def start(self):
        self.count = 0
        self._t0 = time.time()

    def read(self):
        if self.device is None:
            return None
        minutes = max(time.time() - self._t0, 1e-3) / 60.0
        return int(round(self.count / config.RPM_MAGNETS_PER_REV / minutes))

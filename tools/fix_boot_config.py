"""
MOTOSIRA — repair /boot/firmware/config.txt for the INMP441 (run on the Pi with sudo).

    sudo python3 tools/fix_boot_config.py            # apply (backup is made first)
    sudo python3 tools/fix_boot_config.py --check    # only report, change nothing

What it does:
  * backs up config.txt to config.txt.motosira-<timestamp>
  * comments out invalid 'simple-audio-card' lines (not a real overlay; this is why
    the INMP441 was never detected) and duplicate i2s / googlevoicehat lines
  * adds exactly one 'dtparam=i2s=on' + 'dtoverlay=googlevoicehat-soundcard' under [all]
  * leaves everything else (LCD/display, HDMI, camera...) untouched
Reboot afterwards:  sudo reboot   then check:  arecord -l   (card "sndrpigooglevoi")
"""
import argparse
import os
import shutil
import sys
import time

CANDIDATES = ["/boot/firmware/config.txt", "/boot/config.txt"]
MARK = "# --- MOTOSIRA: INMP441 I2S microphone (googlevoicehat-soundcard) ---"


def find_config(path=None):
    if path:
        return path
    for p in CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("config.txt not found (is this a Raspberry Pi?)")


def fix(text):
    out, changes = [], []
    for line in text.splitlines():
        s = line.strip()
        low = s.lower()
        active = s and not s.startswith("#")
        if active and "simple-audio-card" in low:
            out.append("#" + line + "   # disabled by MOTOSIRA (not a valid overlay)")
            changes.append(f"disabled invalid line: {s}")
        elif active and (low.startswith("dtparam=i2s") or "googlevoicehat" in low):
            out.append("#" + line + "   # moved to MOTOSIRA block")
            changes.append(f"commented duplicate: {s}")
        elif s == MARK:
            continue
        else:
            out.append(line)
    while out and out[-1].strip() == "":
        out.pop()
    out += ["", MARK, "[all]", "dtparam=i2s=on", "dtoverlay=googlevoicehat-soundcard", ""]
    changes.append("added: dtparam=i2s=on + dtoverlay=googlevoicehat-soundcard under [all]")
    return "\n".join(out), changes


def status(text):
    act = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    return {"overlay": sum("googlevoicehat-soundcard" in l for l in act),
            "i2s": sum(l.startswith("dtparam=i2s=on") for l in act),
            "invalid": [l for l in act if "simple-audio-card" in l]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--file", help="config file path (default: auto-detect)")
    a = ap.parse_args()
    path = find_config(a.file)
    with open(path, encoding="utf-8", errors="ignore") as fh:
        text = fh.read()
    st = status(text)
    ok = st["overlay"] == 1 and st["i2s"] == 1 and not st["invalid"]
    print(f"{path}: googlevoicehat overlay x{st['overlay']}, i2s=on x{st['i2s']}, invalid lines {len(st['invalid'])}")
    if a.check:
        print("OK — no change needed." if ok else "Needs fixing: sudo python3 tools/fix_boot_config.py")
        return 0 if ok else 1
    if ok:
        print("Already correct. Nothing changed.")
        return 0
    if os.geteuid() != 0 and not a.file:
        raise SystemExit("Run with sudo:  sudo python3 tools/fix_boot_config.py")
    new, changes = fix(text)
    backup = f"{path}.motosira-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    print(f"Backup: {backup}")
    for c in changes:
        print("  -", c)
    print("\nDone. Now reboot:  sudo reboot     then check:  arecord -l")
    return 0


if __name__ == "__main__":
    sys.exit(main())

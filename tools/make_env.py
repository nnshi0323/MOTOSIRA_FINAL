"""
MOTOSIRA — create or update .env (called by setup_pc.bat and setup_pi.sh).

    python tools/make_env.py                          # PC: broker = localhost
    python tools/make_env.py --broker 192.168.100.8   # Pi: broker = the PC's IP
    python tools/make_env.py --show

Existing values are kept unless you pass a new one. The broker value is
validated so a typo can't silently break the connection.
"""
import argparse
import ipaddress
import os
import re
import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, ".env")
DEFAULTS = {
    "SECRET_KEY": None,                      # generated
    "MOTOSIRA_USER": "admin",
    "MOTOSIRA_PASS": "motosira123",
    "MOTOSIRA_PASS_HASH": "",
    "MOTOSIRA_BROKER": "localhost",
    "MOTOSIRA_BROKER_PORT": "1883",
    "MOTOSIRA_DEVICE_ID": "pi-01",
    "MOTOSIRA_DEFAULT_MODE": "mock",
    "MOTOSIRA_MIC_DEVICE": "",
    "MOTOSIRA_MIC_GAIN": "1.0",
    "MOTOSIRA_RPM_ENABLED": "0",
}


def valid_host(value):
    if value == "localhost":
        return True
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}", value)) and "." in value


def read():
    data = {}
    if os.path.exists(ENV):
        with open(ENV, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    data = read()
    if a.broker is not None:
        b = a.broker.strip()
        if not valid_host(b):
            raise SystemExit(f"'{b}' is not a valid IP address or host name. Example: 192.168.100.8")
        data["MOTOSIRA_BROKER"] = b
    elif data.get("MOTOSIRA_BROKER") and not valid_host(data["MOTOSIRA_BROKER"]):
        print(f"WARNING: .env has an invalid MOTOSIRA_BROKER ('{data['MOTOSIRA_BROKER']}'); reset to localhost.")
        data["MOTOSIRA_BROKER"] = "localhost"
    for k, v in DEFAULTS.items():
        if k not in data:
            data[k] = secrets.token_hex(24) if k == "SECRET_KEY" else v
    if not a.show:
        with open(ENV, "w", encoding="utf-8") as fh:
            fh.write("# MOTOSIRA settings for THIS machine — never commit this file\n")
            for k in list(DEFAULTS) + [k for k in data if k not in DEFAULTS]:
                fh.write(f"{k}={data[k]}\n")
    print(f".env: {ENV}")
    print(f"  login    : {data['MOTOSIRA_USER']} / {data['MOTOSIRA_PASS']}"
          + ("  (hash set)" if data.get("MOTOSIRA_PASS_HASH") else ""))
    print(f"  broker   : {data['MOTOSIRA_BROKER']}:{data['MOTOSIRA_BROKER_PORT']}")
    print(f"  device id: {data['MOTOSIRA_DEVICE_ID']}   default mode: {data['MOTOSIRA_DEFAULT_MODE']}")


if __name__ == "__main__":
    main()

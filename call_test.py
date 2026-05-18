#!/usr/bin/env python3
"""
call_test.py - Quick API test
Sends 10 random IPv4 addresses to POST /lookup and prints results.
"""
import json
import os
import random

import requests

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
def load_config(path):
    cfg = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

_config  = load_config(os.path.join(os.path.dirname(__file__), "config.env"))
BASE_URL = f"http://localhost:{_config.get('SERVER_PORT', '8080')}"

# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
def main():
    ips = [".".join(str(random.randint(0, 255)) for _ in range(4)) for _ in range(10)]

    print(f"Target : {BASE_URL}")
    print(f"IPs    : {ips}")
    print()

    resp = requests.post(f"{BASE_URL}/lookup", json={"ips": ips}, timeout=10)
    results = resp.json()["results"]

    for r in results:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print()

if __name__ == "__main__":
    main()

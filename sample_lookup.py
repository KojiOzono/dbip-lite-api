#!/usr/bin/env python3
"""
sample_lookup.py - DB-IP Lite sample viewer

Sends 100 random IPv4 addresses to POST /lookup
and prints each result for quick visual inspection.
"""
import json
import os
import random
import time
import urllib.request

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

_config    = load_config(os.path.join(os.path.dirname(__file__), "config.env"))
BASE_URL   = f"http://localhost:{_config.get('SERVER_PORT', '8080')}"
TOTAL      = 100
BATCH_SIZE = 100

# ─────────────────────────────────────────
# Random IPv4 generator
# ─────────────────────────────────────────
def random_ipv4() -> str:
    return ".".join(str(random.randint(0, 255)) for _ in range(4))

# ─────────────────────────────────────────
# POST /lookup
# ─────────────────────────────────────────
def bulk_lookup(ips: list) -> list:
    data = json.dumps({"ips": ips}).encode("utf-8")
    req  = urllib.request.Request(
        f"{BASE_URL}/lookup",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["results"]

# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
def main():
    print(f"Sending {TOTAL} random IPv4 addresses to POST /lookup")
    print(f"Target: {BASE_URL}")
    print()

    ips           = [random_ipv4() for _ in range(TOTAL)]
    batches       = TOTAL // BATCH_SIZE
    total_elapsed = 0.0

    for i in range(batches):
        batch = ips[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        t0 = time.time()
        try:
            results = bulk_lookup(batch)
            elapsed = time.time() - t0
            total_elapsed += elapsed
            print(f"  batch {i+1}/{batches} | {elapsed*1000:.1f}ms")
            for r in results:
                print(f"    {r}")
        except Exception as e:
            print(f"  batch {i+1}/{batches} | FAILED: {e}")

    print()
    print(f"Total elapsed: {total_elapsed*1000:.1f}ms")

if __name__ == "__main__":
    main()
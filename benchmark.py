#!/usr/bin/env python3
"""
benchmark.py - DB-IP Lite load test

Generates random IPv4 addresses and sends them in batches
to POST /lookup, measuring throughput and response time.
"""
import json
import os
import random
import time
import urllib.error
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
TOTAL      = 10_000
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
    print(f"Sending {TOTAL:,} random IPv4 addresses in batches of {BATCH_SIZE}")
    print(f"Target: {BASE_URL}")
    print()

    ips = [random_ipv4() for _ in range(TOTAL)]

    total_ok       = 0
    total_error    = 0
    total_notfound = 0
    total_elapsed  = 0.0
    batches        = TOTAL // BATCH_SIZE

    for i in range(batches):
        batch = ips[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        t0 = time.time()
        try:
            results = bulk_lookup(batch)
            elapsed = time.time() - t0
            total_elapsed += elapsed

            ok       = sum(1 for r in results if "error" not in r)
            notfound = sum(1 for r in results if r.get("error") == "not found")
            error    = sum(1 for r in results if "error" in r and r.get("error") != "not found")

            total_ok       += ok
            total_notfound += notfound
            total_error    += error

            print(f"  batch {i+1:5d}/{batches} | ok={ok:3d} not_found={notfound:3d} err={error:3d} | {elapsed*1000:.1f}ms")

        except Exception as e:
            print(f"  batch {i+1:5d}/{batches} | FAILED: {e}")
            total_error += BATCH_SIZE

    rps = TOTAL / total_elapsed if total_elapsed > 0 else 0

    print()
    print("=" * 50)
    print(f"Total IPs   : {TOTAL:,}")
    print(f"Found       : {total_ok:,}")
    print(f"Not found   : {total_notfound:,}")
    print(f"Errors      : {total_error:,}")
    print(f"Elapsed     : {total_elapsed:.2f}s")
    print(f"Throughput  : {rps:.1f} req/s")
    print("=" * 50)

if __name__ == "__main__":
    main()
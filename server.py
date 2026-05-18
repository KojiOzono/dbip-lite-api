#!/usr/bin/env python3
"""
DB-IP Lite MMDB API Server

Endpoints:
  GET  /lookup?ip=1.2.3.4
  POST /lookup  {"ips": ["1.2.3.4", ...]}   (max 10000 IPs per request)
  GET  /health
"""
import ipaddress
import os
from typing import List, Optional

import maxminddb
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
WORK_DIR      = os.environ.get("WORK_DIR", os.path.dirname(os.path.abspath(__file__)))
CITY_MMDB     = os.environ.get("CITY_MMDB", os.path.join(WORK_DIR, "dbip-city-lite.mmdb"))
ASN_MMDB      = os.environ.get("ASN_MMDB",  os.path.join(WORK_DIR, "dbip-asn-lite.mmdb"))

app = FastAPI(title="DB-IP Lite", version="2.0.0")

# ─────────────────────────────────────────
# Open MMDB readers at startup (memory-mapped, no disk I/O per query)
# ─────────────────────────────────────────
city_reader = maxminddb.open_database(CITY_MMDB)
asn_reader  = maxminddb.open_database(ASN_MMDB)

# ─────────────────────────────────────────
# Lookup
# ─────────────────────────────────────────
def lookup_one(ip: str) -> dict:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return {"ip": ip, "error": "invalid IP address"}

    city = city_reader.get(ip) or {}
    asn  = asn_reader.get(ip)  or {}

    if not city and not asn:
        return {"ip": ip, "error": "not found"}

    return {
        "ip":        ip,
        "country":   city.get("country", {}).get("iso_code"),
        "city":      (city.get("city") or {}).get("names", {}).get("en"),
        "latitude":  (city.get("location") or {}).get("latitude"),
        "longitude": (city.get("location") or {}).get("longitude"),
        "asn":       str(asn["autonomous_system_number"]) if asn.get("autonomous_system_number") else None,
        "as_org":    asn.get("autonomous_system_organization"),
    }

# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────
@app.get("/lookup")
def lookup_get(ip: str = Query(..., description="IPv4 or IPv6 address")):
    return lookup_one(ip)


class BulkRequest(BaseModel):
    ips: List[str]

@app.post("/lookup")
def lookup_post(req: BulkRequest):
    if len(req.ips) > 10000:
        raise HTTPException(status_code=400, detail="Maximum 10000 IPs per request")
    return {"results": [lookup_one(ip) for ip in req.ips]}


@app.get("/health")
def health():
    return {"status": "ok", "city_mmdb": CITY_MMDB, "asn_mmdb": ASN_MMDB}

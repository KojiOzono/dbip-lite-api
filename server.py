#!/usr/bin/env python3
"""
DB-IP Lite SQLite API Server

Endpoints:
  GET  /lookup?ip=1.2.3.4
  POST /lookup  {"ips": ["1.2.3.4", ...]}   (max 1000 IPs per request)
  GET  /health
"""
import ipaddress
import os
import sqlite3
import threading
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
WORK_DIR = os.environ.get("WORK_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.environ.get("DB_PATH",  os.path.join(WORK_DIR, "dbip.sqlite"))

app = FastAPI(title="DB-IP Lite", version="1.0.0")

# ─────────────────────────────────────────
# Thread-local DB connection
# ─────────────────────────────────────────
_local = threading.local()

def get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating it if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA cache_size   = -32000")
        conn.execute("PRAGMA temp_store   = MEMORY")
        conn.execute("PRAGMA wal_autocheckpoint = 0")  # ← 追加
        _local.conn = conn
    return _local.conn

# ─────────────────────────────────────────
# IP normalization (must match import_dbip.py)
# ─────────────────────────────────────────
def normalize_ip(ip: str) -> Optional[str]:
    """
    Normalize IP address to match the format stored in SQLite.
    IPv4: zero-pad each octet  →  001.002.003.004
    IPv6: exploded form        →  2001:0db8:0000:...
    """
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv4Address):
            return ".".join(f"{int(o):03d}" for o in str(addr).split("."))
        else:
            return addr.exploded
    except ValueError:
        return None

# ─────────────────────────────────────────
# Lookup query (city + asn)
# ─────────────────────────────────────────
LOOKUP_SQL = """
SELECT
    c.country,
    c.city,
    c.latitude,
    c.longitude,
    a.asn,
    a.as_org
FROM dbip_city c
LEFT JOIN dbip_asn a
    ON a.ip_start <= :ip
    AND a.ip_start = (
        SELECT ip_start FROM dbip_asn
        WHERE ip_start <= :ip
        ORDER BY ip_start DESC
        LIMIT 1
    )
WHERE c.ip_start <= :ip
ORDER BY c.ip_start DESC
LIMIT 1
"""

def lookup_one(ip: str) -> dict:
    ip_norm = normalize_ip(ip)
    if ip_norm is None:
        return {"ip": ip, "error": "invalid IP address"}
    conn = get_conn()
    row = conn.execute(LOOKUP_SQL, {"ip": ip_norm}).fetchone()
    if row is None:
        return {"ip": ip, "error": "not found"}
    return {
        "ip":        ip,
        "country":   row["country"],
        "city":      row["city"],
        "latitude":  row["latitude"],
        "longitude": row["longitude"],
        "asn":       row["asn"],
        "as_org":    row["as_org"],
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
    if len(req.ips) > 1000:
        raise HTTPException(status_code=400, detail="Maximum 1000 IPs per request")
    return {"results": [lookup_one(ip) for ip in req.ips]}


@app.get("/health")
def health():
    return {"status": "ok", "db": DB_PATH}

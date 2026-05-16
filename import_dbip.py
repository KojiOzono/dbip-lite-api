#!/usr/bin/env python3
"""
DB-IP City Lite + ASN Lite → SQLite importer

Tables:
  - dbip_city  (IP range → city, lat/lon)
  - dbip_asn   (IP range → AS number, org name)

Index strategy:
  ip_start / ip_end stored as normalized TEXT with B-tree index for range queries.
  IPv4: zero-padded 4-octet string  (e.g. 001.002.003.004)
  IPv6: exploded form               (e.g. 2001:0db8:0000:...)

Performance:
  - journal_mode = OFF during import (switched back to WAL on completion)
  - Custom normalize_ip (no ipaddress module dependency)
  - city and asn imported in parallel using threads

Environment variables (set by dbip.sh via config.env):
  WORK_DIR, DB_PATH
"""

import csv
import gzip
import logging
import os
import sqlite3
import sys
import threading
import time

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
WORK_DIR    = os.environ.get("WORK_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH     = os.environ.get("DB_PATH",  os.path.join(WORK_DIR, "dbip.sqlite"))
CITY_CSV_GZ = os.path.join(WORK_DIR, "dbip-city-lite.csv.gz")
ASN_CSV_GZ  = os.path.join(WORK_DIR, "dbip-asn-lite.csv.gz")
BATCH_SIZE  = 50_000

# ─────────────────────────────────────────
# Logging
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────
# IP normalization (custom, no external deps)
# ─────────────────────────────────────────
def normalize_ip(ip: str):
    """
    IPv4: zero-pad each octet to 3 digits  →  001.002.003.004
    IPv6: expand to full exploded form     →  2001:0db8:0000:...
    Returns None on parse failure.
    """
    if ":" in ip:
        return _normalize_ipv6(ip)
    return _normalize_ipv4(ip)


def _normalize_ipv4(ip: str):
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    try:
        return ".".join(f"{int(p):03d}" for p in parts)
    except ValueError:
        return None


def _normalize_ipv6(ip: str):
    # Expand :: shorthand and zero-pad each group to 4 hex digits
    try:
        if "::" in ip:
            left, _, right = ip.partition("::")
            left_groups  = left.split(":")  if left  else []
            right_groups = right.split(":") if right else []
            missing = 8 - len(left_groups) - len(right_groups)
            groups = left_groups + ["0"] * missing + right_groups
        else:
            groups = ip.split(":")
        if len(groups) != 8:
            return None
        return ":".join(f"{int(g, 16):04x}" for g in groups)
    except ValueError:
        return None


# ─────────────────────────────────────────
# DDL
# ─────────────────────────────────────────
DDL = """
CREATE TABLE IF NOT EXISTS dbip_city (
    ip_start    TEXT NOT NULL,
    ip_end      TEXT NOT NULL,
    country     TEXT,
    city        TEXT,
    latitude    REAL,
    longitude   REAL
);

CREATE TABLE IF NOT EXISTS dbip_asn (
    ip_start    TEXT NOT NULL,
    ip_end      TEXT NOT NULL,
    asn         TEXT,
    as_org      TEXT
);
"""

DDL_INDEX = """
CREATE INDEX IF NOT EXISTS idx_city_start_desc ON dbip_city (ip_start DESC);
CREATE INDEX IF NOT EXISTS idx_asn_start_desc  ON dbip_asn  (ip_start DESC);
"""


# ─────────────────────────────────────────
# Import (shared logic)
# ─────────────────────────────────────────
def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA cache_size   = -64000")
    conn.execute("PRAGMA temp_store   = MEMORY")
    return conn


def import_table(table: str, csv_gz_path: str, row_parser, errors: list):
    try:
        conn = make_conn()
        log.info(f"[{table}] import start: {csv_gz_path}")
        t0 = time.time()
        total = skipped = 0

        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table}")

        rows = []
        with gzip.open(csv_gz_path, "rt", encoding="utf-8") as f:
            for raw in csv.reader(f):
                parsed = row_parser(raw)
                if parsed is None:
                    skipped += 1
                    continue
                rows.append(parsed)
                total += 1
                if len(rows) >= BATCH_SIZE:
                    cur.executemany(
                        f"INSERT INTO {table} VALUES ({','.join(['?']*len(rows[0]))})",
                        rows,
                    )
                    conn.commit()
                    rows = []
                    if total % 500_000 == 0:
                        log.info(f"  [{table}] {total:,} rows...")

        if rows:
            cur.executemany(
                f"INSERT INTO {table} VALUES ({','.join(['?']*len(rows[0]))})",
                rows,
            )
        conn.commit()
        conn.close()

        elapsed = time.time() - t0
        log.info(f"[{table}] done: {total:,} rows / skipped {skipped:,} ({elapsed:.1f}s)")

    except Exception as e:
        log.exception(f"[{table}] error during import: {e}")
        errors.append(e)


# ─────────────────────────────────────────
# City Lite row parser
# CSV columns: ip_start, ip_end, continent, country, stateprov, city, latitude, longitude
# ─────────────────────────────────────────
def parse_city_row(row):
    if len(row) < 8:
        return None
    ip_start = normalize_ip(row[0])
    ip_end   = normalize_ip(row[1])
    if ip_start is None or ip_end is None:
        return None  # skip IPv6
    try:
        lat = float(row[6]) if row[6] else None
        lon = float(row[7]) if row[7] else None
    except ValueError:
        return None
    return (ip_start, ip_end, row[3] or None, row[5] or None, lat, lon)


# ─────────────────────────────────────────
# ASN Lite row parser
# CSV columns: ip_start, ip_end, asn, as_org
# ─────────────────────────────────────────
def parse_asn_row(row):
    if len(row) < 4:
        return None
    ip_start = normalize_ip(row[0])
    ip_end   = normalize_ip(row[1])
    if ip_start is None or ip_end is None:
        return None  # skip IPv6
    return (ip_start, ip_end, row[2] or None, row[3] or None)


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
def main():
    log.info(f"SQLite DB: {DB_PATH}")

    # Create tables with main connection
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DDL)
    conn.close()

    # Import city and asn in parallel
    errors = []
    t_city = threading.Thread(
        target=import_table,
        args=("dbip_city", CITY_CSV_GZ, parse_city_row, errors),
    )
    t_asn = threading.Thread(
        target=import_table,
        args=("dbip_asn", ASN_CSV_GZ, parse_asn_row, errors),
    )

    t_city.start()
    t_asn.start()
    t_city.join()
    t_asn.join()

    if errors:
        log.error("Import failed.")
        sys.exit(1)

    # Build indexes and switch back to WAL mode
    log.info("Building indexes...")
    t0 = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DDL_INDEX)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.close()
    log.info(f"Indexes built ({time.time()-t0:.1f}s)")

    log.info("=== Import complete ===")


if __name__ == "__main__":
    main()

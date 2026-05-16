# dbip-lite-api

A self-hosted IP geolocation API using [DB-IP Lite](https://db-ip.com/db/lite.php) and SQLite.  
Pure Python, no external database required.

## Features

- Single shell script setup — download, import, and start in one command
- Batch lookup up to 1000 IPs per request
- IPv4 + IPv6 support
- Auto monthly update via cron
- Runs on minimal hardware (tested on 1GB RAM VPS)

## Requirements

- Python 3.8+
- `wget`

## File Structure

```
dbip-lite-api/
├── config.env          # Configuration (edit before setup)
├── dbip.sh             # Management script
├── import_dbip.py      # CSV → SQLite importer
├── server.py           # FastAPI server
├── benchmark.py        # Load test (10,000 random IPs)
└── sample_lookup.py    # Quick viewer (100 random IPs)
```

## Quick Start

### 1. Clone

```bash
git clone https://github.com/KojiOzono/dbip-lite-api.git
cd dbip-lite-api
```

### 2. Edit config

```bash
cp config.env.example config.env
vi config.env
```

```env
WORK_DIR=/root/dbip-lite-api
DB_PATH=/root/dbip-lite-api/dbip.sqlite
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
SERVER_WORKERS=1
```

### 3. Setup (one command)

```bash
bash dbip.sh setup
```

This will:
1. Create Python venv and install dependencies (`fastapi`, `uvicorn`)
2. Download DB-IP City Lite + ASN Lite CSV files (~8M + ~470K rows)
3. Import into SQLite (~90 seconds)
4. Start the API server on port 8080

### 4. Test

Activate the venv first:

```bash
source $WORK_DIR/venv/bin/activate
```

Quick viewer (100 random IPs):

```bash
python sample_lookup.py
```

Load test (10,000 random IPs):

```bash
python benchmark.py
```

## Server Management

```bash
bash dbip.sh start    # Start server
bash dbip.sh stop     # Stop server
bash dbip.sh update   # Stop → download latest CSV → reimport → start
bash dbip.sh download # Download CSV only
bash dbip.sh import   # Import CSV into SQLite only
```

## Monthly Update (cron)

```bash
crontab -e
```

```cron
0 3 2 * * /root/dbip-lite-api/dbip.sh update >> /root/dbip-lite-api/logs/cron.log 2>&1
```

DB-IP Lite is updated monthly. The `update` command handles stop → download → reimport → restart automatically.

## API

### GET /lookup

```bash
curl "http://localhost:8080/lookup?ip=8.8.8.8"
```

```json
{
  "ip": "8.8.8.8",
  "country": "US",
  "city": "Mountain View",
  "latitude": 37.4056,
  "longitude": -122.0775,
  "asn": "15169",
  "as_org": "Google LLC"
}
```

### POST /lookup (batch, max 1000 IPs)

```bash
curl -X POST "http://localhost:8080/lookup" \
  -H "Content-Type: application/json" \
  -d '{"ips": ["8.8.8.8", "1.1.1.1"]}'
```

```json
{
  "results": [
    {
      "ip": "8.8.8.8",
      "country": "US",
      "city": "Mountain View",
      "latitude": 37.4056,
      "longitude": -122.0775,
      "asn": "15169",
      "as_org": "Google LLC"
    },
    {
      "ip": "1.1.1.1",
      "country": "AU",
      "city": "South Brisbane",
      "latitude": -27.4767,
      "longitude": 153.017,
      "asn": "13335",
      "as_org": "Cloudflare, Inc."
    }
  ]
}
```

### GET /health

```bash
curl "http://localhost:8080/health"
```

```json
{"status": "ok", "db": "/root/dbip-lite-api/dbip.sqlite"}
```

## Performance

Tested on a 1GB RAM VPS with NVMe storage (single worker):

```
Total IPs   : 10,000
Found       : 10,000
Not found   : 0
Errors      : 0
Elapsed     : 1.37s
Throughput  : 3,500 – 8,000 req/s
```

Run `benchmark.py` to measure on your environment.

## Data Source

This tool downloads data from [DB-IP](https://db-ip.com).  
IP Geolocation data provided by [DB-IP.com](https://db-ip.com) is licensed under  
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).

> **Note:** You are free to use DB-IP Lite data in any application (including commercial),  
> provided you give attribution to DB-IP.com. If you use results in a web application,  
> you must include a link back to DB-IP.com on pages that display the data.  
> Please review the [DB-IP license terms](https://db-ip.com/db/lite.php) for full details.

## Running as a systemd Service (optional)

Create `/etc/systemd/system/dbip.service`:

```ini
[Unit]
After=network.target

[Service]
ExecStart=/root/dbip-lite-api/venv/bin/uvicorn server:app
WorkingDirectory=/root/dbip-lite-api
Restart=always

[Install]
WantedBy=multi-user.target
```

> Edit `ExecStart` and `WorkingDirectory` to match your `WORK_DIR` in `config.env`.

```bash
systemctl daemon-reload
systemctl enable dbip
systemctl start dbip
```

## License

MIT

#!/bin/bash
# =============================================================
# DB-IP Lite Management Script (SQLite edition)
# Usage: ./dbip.sh <command>
# =============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.env"

# ─────────────────────────────────────────
# Load configuration
# ─────────────────────────────────────────
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: config file not found: $CONFIG_FILE" >&2
    exit 1
fi
set -a; source "$CONFIG_FILE"; set +a

LOG_DIR="${WORK_DIR}/logs"
VENV_DIR="${WORK_DIR}/venv"
PID_FILE="${WORK_DIR}/server.pid"
SERVER_WORKERS="${SERVER_WORKERS:-1}"

# ─────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
    cat <<'EOF'

Usage: dbip.sh <command>

Commands:
  setup     Initial setup (create venv → download → import → start server)
  update    Monthly update (stop → download → import → start)  ← for cron
  download  Download CSV files only
  import    Import into SQLite only (requires downloaded CSV files)
  start     Start the server only
  stop      Stop the server

Examples:
  ./dbip.sh setup
  ./dbip.sh update
  ./dbip.sh start
  ./dbip.sh stop

Cron example (every 2nd day of month at 03:00):
  0 3 2 * * /root/dbip-lite-api/dbip.sh update >> /root/dbip-lite-api/logs/cron.log 2>&1

EOF
}

# ─────────────────────────────────────────
# Python venv setup
# ─────────────────────────────────────────
cmd_setup_venv() {
    if [[ -d "$VENV_DIR" ]]; then
        log "venv already exists. Skipping."
    else
        log "Creating Python venv..."
        python3 -m venv "$VENV_DIR"
        log "Installing dependencies..."
        "$VENV_DIR/bin/pip" install --quiet fastapi "uvicorn[standard]"
        log "venv ready."
    fi
}

activate_venv() {
    [[ -d "$VENV_DIR" ]] || die "venv not found. Run ./dbip.sh setup first."
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
}

# ─────────────────────────────────────────
# Download
# ─────────────────────────────────────────
cmd_download() {
    local year_month
    year_month=$(date +%Y-%m)
    local city_url="https://download.db-ip.com/free/dbip-city-lite-${year_month}.csv.gz"
    local asn_url="https://download.db-ip.com/free/dbip-asn-lite-${year_month}.csv.gz"

    log "Downloading DB-IP Lite (${year_month})"
    mkdir -p "$WORK_DIR"
    cd "$WORK_DIR"

    # Backup existing files
    [[ -f dbip-city-lite.csv.gz ]] && mv dbip-city-lite.csv.gz dbip-city-lite.prev.csv.gz
    [[ -f dbip-asn-lite.csv.gz  ]] && mv dbip-asn-lite.csv.gz  dbip-asn-lite.prev.csv.gz

    # City Lite
    if wget -q --show-progress -O dbip-city-lite.csv.gz "$city_url"; then
        log "City Lite downloaded."
    else
        log "WARN: City Lite download failed. Restoring previous file."
        [[ -f dbip-city-lite.prev.csv.gz ]] && mv dbip-city-lite.prev.csv.gz dbip-city-lite.csv.gz
        die "Failed to download City Lite: $city_url"
    fi

    # ASN Lite
    if wget -q --show-progress -O dbip-asn-lite.csv.gz "$asn_url"; then
        log "ASN Lite downloaded."
    else
        log "WARN: ASN Lite download failed. Restoring previous file."
        [[ -f dbip-asn-lite.prev.csv.gz ]] && mv dbip-asn-lite.prev.csv.gz dbip-asn-lite.csv.gz
        die "Failed to download ASN Lite: $asn_url"
    fi

    rm -f dbip-city-lite.prev.csv.gz dbip-asn-lite.prev.csv.gz
    log "Download complete."
}

# ─────────────────────────────────────────
# Import
# ─────────────────────────────────────────
cmd_import() {
    activate_venv
    log "Importing into SQLite..."
    cd "$WORK_DIR"
    python3 "$SCRIPT_DIR/import_dbip.py"
    log "Import complete."
}

# ─────────────────────────────────────────
# Server start / stop
# ─────────────────────────────────────────
cmd_start() {
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        log "Server is already running (PID: $(cat "$PID_FILE"))."
        return
    fi
    activate_venv
    mkdir -p "$LOG_DIR"
    log "Starting server... http://${SERVER_HOST}:${SERVER_PORT} (workers=${SERVER_WORKERS})"
    nohup "$VENV_DIR/bin/uvicorn" server:app \
        --host "$SERVER_HOST" \
        --port "$SERVER_PORT" \
        --workers "$SERVER_WORKERS" \
        >> "$LOG_DIR/server.log" 2>&1 &
    echo $! > "$PID_FILE"
    log "Server started (PID: $!)."
}

cmd_stop() {
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        kill "$(cat "$PID_FILE")"
        rm -f "$PID_FILE"
        log "Server stopped."
    else
        log "Server is not running."
        rm -f "$PID_FILE"
    fi
}

# ─────────────────────────────────────────
# Log setup
# ─────────────────────────────────────────
setup_log() {
    mkdir -p "$LOG_DIR"
    local log_file="$LOG_DIR/dbip_$(date +%Y%m%d_%H%M%S).log"
    exec > >(tee -a "$log_file") 2>&1
    log "Log file: $log_file"
}

# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
COMMAND="${1:-}"

case "$COMMAND" in
    setup)
        setup_log
        log "=== setup start ==="
        cmd_setup_venv
        cmd_download
        cmd_import
        cmd_start
        log "=== setup complete ==="
        ;;
    update)
        setup_log
        log "=== update start ==="
        cmd_stop
        cmd_download
        cmd_import
        cmd_start
        log "=== update complete ==="
        ;;
    download)
        setup_log
        log "=== download start ==="
        cmd_download
        log "=== download complete ==="
        ;;
    import)
        setup_log
        log "=== import start ==="
        cmd_import
        log "=== import complete ==="
        ;;
    start)
        setup_log
        log "=== start ==="
        cmd_start
        ;;
    stop)
        log "=== stop ==="
        cmd_stop
        ;;
    "")
        usage
        exit 0
        ;;
    *)
        echo "ERROR: Unknown command: $COMMAND" >&2
        usage
        exit 1
        ;;
esac

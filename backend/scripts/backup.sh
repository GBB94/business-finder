#!/usr/bin/env bash
# IdeaScope database backup script
# Usage: ./scripts/backup.sh [backup_dir]
#
# Recommended cron entry (daily at 2 AM):
#   0 2 * * * DB_PATH=/absolute/path/to/ideascope.db /path/to/backend/scripts/backup.sh /backups
#
# Keeps the last 30 daily backups. Older backups are pruned automatically.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default DB_PATH resolves relative to the backend directory, not cwd
if [ -z "${DB_PATH:-}" ]; then
    DB_PATH="${BACKEND_DIR}/ideascope.db"
fi

BACKUP_DIR="${1:-/backups}"
RETENTION_DAYS=30
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/ideascope-${TIMESTAMP}.db"

# Fail early if the source database doesn't exist
if [ ! -f "${DB_PATH}" ]; then
    echo "ERROR: Database not found at ${DB_PATH}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "Backing up: ${DB_PATH}"

# Use SQLite .backup command for a safe, consistent backup
sqlite3 "${DB_PATH}" ".backup '${BACKUP_FILE}'"

echo "Backup created: ${BACKUP_FILE}"

# Prune old backups beyond retention period
find "${BACKUP_DIR}" -name "ideascope-*.db" -type f -mtime "+${RETENTION_DAYS}" -delete

echo "Pruned backups older than ${RETENTION_DAYS} days."

# Verify backup integrity
if sqlite3 "${BACKUP_FILE}" "PRAGMA integrity_check;" | grep -q "ok"; then
    echo "Backup integrity verified."
else
    echo "WARNING: Backup integrity check failed for ${BACKUP_FILE}" >&2
    exit 1
fi

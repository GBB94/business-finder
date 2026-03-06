#!/usr/bin/env bash
# IdeaScope database backup script (PostgreSQL)
# Usage: ./scripts/backup.sh [backup_dir]
#
# Recommended cron entry (daily at 2 AM):
#   0 2 * * * /path/to/backend/scripts/backup.sh /backups
#
# Keeps the last 30 daily backups. Older backups are pruned automatically.

set -euo pipefail

BACKUP_DIR="${1:-/backups}"
RETENTION_DAYS=30
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/ideascope-${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

echo "Backing up PostgreSQL database..."

PGPASSWORD="${PGPASSWORD:-ideascope_dev}" pg_dump \
  -h "${PGHOST:-localhost}" \
  -U "${PGUSER:-ideascope}" \
  -d "${PGDB:-ideascope}" \
  -Fc \
  -f "${BACKUP_FILE}"

echo "Backup created: ${BACKUP_FILE}"

# Prune old backups beyond retention period
find "${BACKUP_DIR}" -name "ideascope-*.dump" -type f -mtime "+${RETENTION_DAYS}" -delete

echo "Pruned backups older than ${RETENTION_DAYS} days."
echo "Backup complete."

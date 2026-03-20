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

# Prune old database backups beyond retention period
find "${BACKUP_DIR}" -name "ideascope-*.dump" -type f -mtime "+${RETENTION_DAYS}" -delete

echo "Pruned database backups older than ${RETENTION_DAYS} days."

# Encrypted env file backup (requires SECRETS_MASTER_KEY)
# Invoke the file directly to avoid app/services/__init__.py which pulls in
# DB/model code that is not needed for the backup CLI.
echo "Backing up env files (encrypted)..."
BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if ! PYTHONPATH="${BACKEND_DIR}" python3 "${BACKEND_DIR}/app/services/backup_service.py" backup --out "${BACKUP_DIR}"; then
  echo "ERROR: Env file backup FAILED." >&2
  exit 1
fi

echo "Backup complete."

"""Encrypted backup and restore for per-project env files.

Uses AES-256-GCM with a key derived from SECRETS_MASTER_KEY via
PBKDF2-HMAC-SHA256. Backups are tar.gz archives encrypted into
a single binary blob (.enc). Each backup embeds a unique salt
and IV so identical plaintext produces different ciphertext.

Usage from CLI (invoke the file directly to avoid __init__.py side effects):
    PYTHONPATH=. python app/services/backup_service.py backup [--out /backups]
    PYTHONPATH=. python app/services/backup_service.py restore <backup_file>
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _settings():
    """Lazy import to avoid triggering app.services.__init__ at module load."""
    from app.config import settings
    return settings

_SALT_LEN = 16
_IV_LEN = 12   # GCM standard
_TAG_LEN = 16  # GCM tag
_KEY_LEN = 32  # AES-256
_KDF_ITERATIONS = 200_000


def _derive_key(master_key: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from the master key using PBKDF2."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        master_key.encode("utf-8"),
        salt,
        _KDF_ITERATIONS,
        dklen=_KEY_LEN,
    )


def _encrypt(plaintext: bytes, master_key: str) -> bytes:
    """Encrypt plaintext with AES-256-GCM. Returns salt + iv + ciphertext + tag."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(_SALT_LEN)
    iv = os.urandom(_IV_LEN)
    key = _derive_key(master_key, salt)

    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(iv, plaintext, None)  # ct includes the tag

    return salt + iv + ct


def _decrypt(blob: bytes, master_key: str) -> bytes:
    """Decrypt a blob produced by _encrypt."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(blob) < _SALT_LEN + _IV_LEN + _TAG_LEN:
        raise ValueError("Encrypted blob is too short")

    salt = blob[:_SALT_LEN]
    iv = blob[_SALT_LEN : _SALT_LEN + _IV_LEN]
    ct = blob[_SALT_LEN + _IV_LEN :]

    key = _derive_key(master_key, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ct, None)


def create_encrypted_backup(
    output_dir: str | None = None,
    envfiles_dir: str | None = None,
) -> str | None:
    """Create an encrypted backup of all env files.

    Returns the backup file path on success, None if no env files exist
    or SECRETS_MASTER_KEY is not configured.
    """
    if not _settings().SECRETS_MASTER_KEY:
        logger.error("SECRETS_MASTER_KEY not configured. Cannot create encrypted backup.")
        return None

    src = Path(envfiles_dir or "/data/envfiles")
    if not src.exists():
        logger.warning("Env files directory does not exist: %s", src)
        return None

    env_files = list(src.glob(".env.*"))
    if not env_files:
        logger.info("No env files found in %s, skipping backup", src)
        return None

    # Create tar.gz in memory
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in env_files:
            tar.add(str(f), arcname=f.name)

    plaintext = buf.getvalue()
    encrypted = _encrypt(plaintext, _settings().SECRETS_MASTER_KEY)

    # Write to output directory
    out_dir = Path(output_dir or "/backups")
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = out_dir / f"envfiles-{timestamp}.enc"
    backup_path.write_bytes(encrypted)
    os.chmod(backup_path, 0o600)

    # Prune old backups (keep last 30)
    existing = sorted(out_dir.glob("envfiles-*.enc"), key=lambda p: p.name)
    for old in existing[:-30]:
        old.unlink()
        logger.info("Pruned old backup: %s", old.name)

    logger.info(
        "Created encrypted env backup: %s (%d files, %d bytes encrypted)",
        backup_path, len(env_files), len(encrypted),
    )
    return str(backup_path)


def restore_encrypted_backup(
    backup_path: str,
    envfiles_dir: str | None = None,
) -> int:
    """Restore env files from an encrypted backup.

    Returns the number of files restored.
    """
    if not _settings().SECRETS_MASTER_KEY:
        raise ValueError("SECRETS_MASTER_KEY not configured. Cannot decrypt backup.")

    blob = Path(backup_path).read_bytes()
    plaintext = _decrypt(blob, _settings().SECRETS_MASTER_KEY)

    dest = Path(envfiles_dir or "/data/envfiles")
    dest.mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO(plaintext)
    count = 0
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # Resolve the full extraction path and verify it stays inside dest
            target = (dest / member.name).resolve()
            if not str(target).startswith(str(dest.resolve()) + os.sep) and target != dest.resolve():
                logger.warning("Skipping tar member with path traversal: %s", member.name)
                continue
            tar.extract(member, path=str(dest))
            os.chmod(target, 0o600)
            count += 1

    logger.info("Restored %d env files from %s to %s", count, backup_path, dest)
    return count


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python -m app.services.backup_service backup [--out DIR]")
        print("       python -m app.services.backup_service restore <FILE>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "backup":
        out = None
        if "--out" in sys.argv:
            idx = sys.argv.index("--out")
            out = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        result = create_encrypted_backup(output_dir=out)
        if result:
            print(f"Backup created: {result}")
        else:
            print("No backup created (check logs)")
            sys.exit(1)
    elif cmd == "restore":
        if len(sys.argv) < 3:
            print("Usage: python -m app.services.backup_service restore <FILE>")
            sys.exit(1)
        count = restore_encrypted_backup(sys.argv[2])
        print(f"Restored {count} files")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

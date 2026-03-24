"""Redis advisory locks for per-project task serialization.

Only one task per project runs at a time. The lock is keyed by idea_id
alone (not idea_id + task_type) to prevent conflicting operations within
the same project.
"""
from __future__ import annotations

import uuid

import redis as redis_lib


def _lock_key(idea_id: str) -> str:
    return f"lock:project:{idea_id}"


def acquire_project_lock(
    redis_conn: redis_lib.Redis,
    idea_id: str,
    task_type: str,
    ttl: int = 300,
) -> str | None:
    """Acquire a per-project lock. Returns a token on success, None if already held.

    task_type is accepted for logging/diagnostics but is NOT part of the
    lock key. Only one task per project can hold the lock.
    """
    key = _lock_key(idea_id)
    token = str(uuid.uuid4())
    acquired = redis_conn.set(key, token, nx=True, ex=ttl)
    return token if acquired else None


def renew_project_lock(
    redis_conn: redis_lib.Redis,
    idea_id: str,
    task_type: str,
    token: str,
    ttl: int = 300,
) -> bool:
    """Extend a lock's TTL if it is still held by the given token."""
    key = _lock_key(idea_id)
    lua = (
        "if redis.call('get',KEYS[1])==ARGV[1] then "
        "  return redis.call('expire',KEYS[1],ARGV[2]) "
        "else return 0 end"
    )
    result = redis_conn.eval(lua, 1, key, token, str(ttl))
    return bool(result)


def release_project_lock(
    redis_conn: redis_lib.Redis,
    idea_id: str,
    task_type: str,
    token: str,
) -> bool:
    """Release a lock using a compare-and-swap Lua script."""
    key = _lock_key(idea_id)
    lua = "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
    result = redis_conn.eval(lua, 1, key, token)
    return bool(result)

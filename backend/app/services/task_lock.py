"""Redis advisory locks for per-project task deduplication."""
from __future__ import annotations

import uuid

import redis as redis_lib


def acquire_project_lock(
    redis_conn: redis_lib.Redis,
    idea_id: str,
    task_type: str,
    ttl: int = 300,
) -> str | None:
    """Acquire a lock for (idea_id, task_type). Returns a token on success, None if already held."""
    key = f"lock:agent:{idea_id}:{task_type}"
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
    key = f"lock:agent:{idea_id}:{task_type}"
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
    key = f"lock:agent:{idea_id}:{task_type}"
    lua = "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"
    result = redis_conn.eval(lua, 1, key, token)
    return bool(result)

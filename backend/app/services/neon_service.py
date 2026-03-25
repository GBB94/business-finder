"""Neon API client for project and branch management.

Creates one Neon project per LaunchPad project. Preview deployments use a
Neon branch (isolated, disposable). Production uses the main branch.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://console.neon.tech/api/v2"


def _headers() -> dict[str, str]:
    if not settings.NEON_API_KEY:
        raise RuntimeError("NEON_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.NEON_API_KEY}",
        "Content-Type": "application/json",
    }


def create_project(project_name: str) -> dict:
    """Create a Neon project. Returns project_id, main connection URI, and main branch_id."""
    resp = httpx.post(
        f"{BASE_URL}/projects",
        headers=_headers(),
        json={"project": {"name": project_name}},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    project = data["project"]
    # The first database and role are auto-created by Neon
    connection_uris = data.get("connection_uris", [])
    main_uri = connection_uris[0]["connection_uri"] if connection_uris else None

    # Find the main branch ID
    main_branch_id = project.get("default_branch_id")

    logger.info(
        "Created Neon project '%s' (id=%s, branch=%s)",
        project_name, project["id"], main_branch_id,
    )
    return {
        "project_id": project["id"],
        "main_branch_id": main_branch_id,
        "main_connection_uri": main_uri,
    }


def create_branch(project_id: str, branch_name: str = "preview") -> dict:
    """Create a branch off main for preview isolation. Returns branch_id and connection URI."""
    resp = httpx.post(
        f"{BASE_URL}/projects/{project_id}/branches",
        headers=_headers(),
        json={
            "branch": {"name": branch_name},
            "endpoints": [{"type": "read_write"}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    branch = data["branch"]
    endpoints = data.get("endpoints", [])
    # Build connection URI from endpoint host
    connection_uri = None
    if endpoints:
        host = endpoints[0].get("host")
        if host:
            # Neon connection format: user info comes from the main project
            # The branch endpoint host is what differentiates branches
            connection_uri = f"postgresql://neondb_owner@{host}/neondb?sslmode=require"

    # If Neon returned connection_uris directly, prefer that
    for uri_obj in data.get("connection_uris", []):
        connection_uri = uri_obj.get("connection_uri", connection_uri)

    logger.info(
        "Created Neon branch '%s' (id=%s) on project=%s",
        branch_name, branch["id"], project_id,
    )
    return {
        "branch_id": branch["id"],
        "branch_name": branch_name,
        "connection_uri": connection_uri,
    }


def delete_branch(project_id: str, branch_id: str) -> bool:
    """Delete a Neon branch. Returns True on success."""
    resp = httpx.delete(
        f"{BASE_URL}/projects/{project_id}/branches/{branch_id}",
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 404:
        logger.warning("Branch %s not found on project %s", branch_id, project_id)
        return False
    resp.raise_for_status()
    logger.info("Deleted Neon branch %s on project=%s", branch_id, project_id)
    return True

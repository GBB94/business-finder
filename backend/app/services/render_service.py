"""Render API client for service and environment management.

Creates web services, manages environment variables per deploy context,
and triggers deploys. Preview services auto-deploy from branches;
production promotion updates the env group to use production credentials.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.render.com/v1"


def _headers() -> dict[str, str]:
    if not settings.RENDER_API_KEY:
        raise RuntimeError("RENDER_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.RENDER_API_KEY}",
        "Content-Type": "application/json",
    }


def create_web_service(
    name: str,
    repo_url: str,
    *,
    branch: str = "main",
    env_vars: Optional[dict[str, str]] = None,
    build_command: str = "npm install && npm run build",
    start_command: str = "npm start",
    plan: str = "free",
) -> dict:
    """Create a Render web service connected to a GitHub repo.

    Returns service_id, service_url, and deploy_url.
    """
    owner_id = settings.RENDER_OWNER_ID

    body: dict = {
        "name": name,
        "type": "web_service",
        "repo": repo_url,
        "branch": branch,
        "autoDeploy": "yes",
        "buildCommand": build_command,
        "startCommand": start_command,
        "plan": plan,
        "runtime": "node",
    }
    if owner_id:
        body["ownerId"] = owner_id

    # Convert env_vars dict to Render's format
    if env_vars:
        body["envVars"] = [
            {"key": k, "value": v} for k, v in env_vars.items()
        ]

    resp = httpx.post(
        f"{BASE_URL}/services",
        headers=_headers(),
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    service = data.get("service", data)
    service_id = service["id"]
    service_url = service.get("serviceDetails", {}).get("url") or f"https://{name}.onrender.com"

    logger.info("Created Render service '%s' (id=%s)", name, service_id)
    return {
        "service_id": service_id,
        "service_url": service_url,
        "name": name,
    }


def update_env_vars(service_id: str, env_vars: dict[str, str]) -> dict:
    """Replace all environment variables on a Render service.

    This is a PUT operation: all existing env vars are replaced.
    Used during promotion to swap preview credentials for production ones.
    """
    render_vars = [{"key": k, "value": v} for k, v in env_vars.items()]

    resp = httpx.put(
        f"{BASE_URL}/services/{service_id}/env-vars",
        headers=_headers(),
        json=render_vars,
        timeout=30,
    )
    resp.raise_for_status()

    logger.info(
        "Updated %d env vars on Render service %s",
        len(env_vars), service_id,
    )
    return {"service_id": service_id, "keys_updated": list(env_vars.keys())}


def trigger_deploy(service_id: str) -> dict:
    """Trigger a manual deploy on a Render service. Returns deploy_id."""
    resp = httpx.post(
        f"{BASE_URL}/services/{service_id}/deploys",
        headers=_headers(),
        json={},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    deploy_id = data.get("id", data.get("deploy", {}).get("id"))
    logger.info("Triggered deploy %s on service %s", deploy_id, service_id)
    return {"deploy_id": deploy_id, "service_id": service_id}


def get_service(service_id: str) -> dict | None:
    """Fetch service metadata. Returns None if not found."""
    resp = httpx.get(
        f"{BASE_URL}/services/{service_id}",
        headers=_headers(),
        timeout=15,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()

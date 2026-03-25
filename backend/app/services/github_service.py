"""GitHub API client for repo creation and branch management.

Creates repos from the golden path template. Manages branch merging
for production promotions.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"


def _headers() -> dict[str, str]:
    if not settings.GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def create_repo_from_template(
    repo_name: str,
    *,
    description: str = "",
    private: bool = True,
) -> dict:
    """Create a new repo from the golden path template.

    Returns repo full_name, html_url, and clone_url.
    """
    template = settings.GITHUB_TEMPLATE_REPO
    if not template:
        raise RuntimeError("GITHUB_TEMPLATE_REPO is not configured")

    owner = settings.GITHUB_ORG
    if not owner:
        raise RuntimeError("GITHUB_ORG is not configured")

    resp = httpx.post(
        f"{BASE_URL}/repos/{template}/generate",
        headers=_headers(),
        json={
            "owner": owner,
            "name": repo_name,
            "description": description,
            "private": private,
            "include_all_branches": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    repo = resp.json()

    logger.info("Created repo '%s' from template '%s'", repo["full_name"], template)
    return {
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "clone_url": repo["clone_url"],
        "default_branch": repo.get("default_branch", "main"),
    }


def merge_branch(
    repo_full_name: str,
    head: str,
    base: str = "main",
    commit_message: str | None = None,
) -> dict:
    """Merge a branch into base (typically main). Returns merge commit SHA."""
    resp = httpx.post(
        f"{BASE_URL}/repos/{repo_full_name}/merges",
        headers=_headers(),
        json={
            "base": base,
            "head": head,
            "commit_message": commit_message or f"Merge {head} into {base}",
        },
        timeout=30,
    )

    if resp.status_code == 204:
        # Already up to date
        logger.info("Branch '%s' already merged into '%s' on %s", head, base, repo_full_name)
        return {"status": "already_merged", "sha": None}

    if resp.status_code == 409:
        raise RuntimeError(
            f"Merge conflict: cannot merge '{head}' into '{base}' on {repo_full_name}. "
            f"Resolve conflicts manually."
        )

    resp.raise_for_status()
    data = resp.json()

    logger.info(
        "Merged '%s' into '%s' on %s (sha=%s)",
        head, base, repo_full_name, data.get("sha", "")[:8],
    )
    return {
        "status": "merged",
        "sha": data.get("sha"),
        "html_url": data.get("html_url"),
    }


def get_repo(repo_full_name: str) -> dict | None:
    """Fetch repo metadata. Returns None if not found."""
    resp = httpx.get(
        f"{BASE_URL}/repos/{repo_full_name}",
        headers=_headers(),
        timeout=15,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()

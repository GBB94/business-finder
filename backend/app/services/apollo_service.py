"""Apollo.io API client for B2B prospect search.

Used by the marketing agent to find prospects matching an idea's target
audience. Apollo provides contact data (email, title, company) and basic
firmographic filters (industry, location, headcount).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.apollo.io/v1"


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": settings.APOLLO_API_KEY or "",
    }


async def search_people(
    *,
    titles: list[str] | None = None,
    industries: list[str] | None = None,
    locations: list[str] | None = None,
    person_seniorities: list[str] | None = None,
    employee_count_min: int | None = None,
    employee_count_max: int | None = None,
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """Search Apollo for people matching the given filters.

    Returns {"people": [...], "pagination": {...}}.
    Each person includes: first_name, last_name, email, title, organization_name,
    city, state, country.
    """
    body: dict = {
        "page": page,
        "per_page": min(per_page, 100),  # Apollo max is 100
    }

    if titles:
        body["person_titles"] = titles
    if industries:
        body["organization_industry_tag_ids"] = industries
    if locations:
        body["person_locations"] = locations
    if person_seniorities:
        body["person_seniorities"] = person_seniorities
    if employee_count_min is not None or employee_count_max is not None:
        ranges = []
        if employee_count_min is not None and employee_count_max is not None:
            ranges.append(f"{employee_count_min},{employee_count_max}")
        elif employee_count_min is not None:
            ranges.append(f"{employee_count_min},")
        else:
            ranges.append(f",{employee_count_max}")
        body["organization_num_employees_ranges"] = ranges

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/mixed_people/search",
            headers=_headers(),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


async def enrich_person(email: str) -> dict:
    """Enrich a single email address with Apollo data.

    Returns person record with title, company, seniority, etc.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/people/match",
            headers=_headers(),
            json={"email": email, "reveal_personal_emails": False},
        )
        resp.raise_for_status()
        return resp.json()


async def get_organization(domain: str) -> dict:
    """Look up a company by domain.

    Returns firmographic data: name, industry, employee count, etc.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BASE_URL}/organizations/enrich",
            headers=_headers(),
            json={"domain": domain},
        )
        resp.raise_for_status()
        return resp.json()

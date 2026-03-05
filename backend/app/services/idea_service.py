from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.idea import Idea, IdeaStatus

ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "discovery": ["scoring", "killed", "parked"],
    "scoring": ["validating", "killed", "parked"],
    "validating": ["building", "killed", "parked"],
    "building": ["retention", "killed", "parked"],
    "retention": ["growing", "killed", "parked"],
    "growing": ["killed", "parked"],
    "killed": ["discovery"],
    "parked": ["discovery"],
}

DEFAULT_KILL_TRIGGERS = {
    "no_paying_customers_90d": {
        "label": "No paying customers after 90 days of validation",
        "fired": False,
    },
    "runway_below_floor": {
        "label": "Runway drops below floor months",
        "fired": False,
    },
    "founder_lost_conviction": {
        "label": "Founder lost conviction in the problem",
        "fired": False,
    },
}


def transition_status(db: Session, idea: Idea, new_status: str) -> Idea:
    current = idea.status if isinstance(idea.status, str) else idea.status.value
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        raise ValueError(
            f"Cannot transition from '{current}' to '{new_status}'. "
            f"Allowed: {allowed}"
        )

    idea.status = new_status
    if new_status == "killed":
        idea.kill_date = datetime.now(timezone.utc)
    elif new_status == "discovery" and current in ("killed", "parked"):
        idea.kill_date = None

    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea


def seed_kill_triggers(idea: Idea) -> None:
    if idea.kill_triggers is None:
        idea.kill_triggers = DEFAULT_KILL_TRIGGERS.copy()


def compute_days_in_stage(idea: Idea) -> int:
    now = datetime.now(timezone.utc)
    updated = idea.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return (now - updated).days


def archive_idea(db: Session, idea: Idea) -> Idea:
    idea.archived_at = datetime.now(timezone.utc)
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea


def unarchive_idea(db: Session, idea: Idea) -> Idea:
    idea.archived_at = None
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea

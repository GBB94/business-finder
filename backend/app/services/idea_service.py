from __future__ import annotations

import copy
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.idea import Idea, IdeaStatus
from app.models.founder_profile import FounderProfile

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


_VALIDATION_STAGES = {"validating", "building", "retention", "growing"}


def evaluate_kill_triggers(db: Session, idea: Idea) -> dict:
    """Evaluate auto-evaluable kill triggers and return updated triggers dict.

    Only updates triggers that can be auto-evaluated. Manual triggers
    (founder_lost_conviction) are never auto-set. Already-fired triggers
    are never cleared.
    """
    triggers = copy.deepcopy(idea.kill_triggers) if idea.kill_triggers else {}

    # --- no_paying_customers_90d ---
    trigger = triggers.get("no_paying_customers_90d")
    if trigger and not trigger.get("fired"):
        status = idea.status if isinstance(idea.status, str) else idea.status.value
        if status in _VALIDATION_STAGES:
            created = idea.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            days_since_creation = (datetime.now(timezone.utc) - created).days
            if days_since_creation >= 90:
                pre_sale_count = sum(
                    1 for ev in idea.evidence
                    if (ev.evidence_type if isinstance(ev.evidence_type, str)
                        else ev.evidence_type.value) == "pre_sale"
                )
                if pre_sale_count == 0:
                    trigger["fired"] = True

    # --- runway_below_floor ---
    trigger = triggers.get("runway_below_floor")
    if trigger and not trigger.get("fired"):
        profile = db.query(FounderProfile).filter_by(user_id=idea.user_id).first()
        if profile and profile.monthly_burn_rate > 0:
            runway_remaining = profile.current_savings / profile.monthly_burn_rate
            if runway_remaining < profile.runway_floor_months:
                trigger["fired"] = True

    # founder_lost_conviction — manual only, never auto-evaluated

    return triggers

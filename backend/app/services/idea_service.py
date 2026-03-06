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
        "category": "hard",
        "state": "grey",
        "fired": False,
    },
    "runway_below_floor": {
        "label": "Runway drops below floor months",
        "category": "hard",
        "state": "grey",
        "fired": False,
    },
    "founder_lost_conviction": {
        "label": "Founder lost conviction in the problem",
        "category": "soft",
        "state": "grey",
        "fired": False,
    },
    "activation_below_floor": {
        "label": "Activation rate below floor",
        "category": "hard",
        "state": "grey",
        "fired": False,
        "min_sample_size": 30,
        "sample_window_days": 30,
        "metric_key": "activation_rate",
        "first_breach_at": None,
    },
    "churn_above_ceiling": {
        "label": "Monthly churn above ceiling",
        "category": "hard",
        "state": "grey",
        "fired": False,
        "min_sample_size": 20,
        "sample_window_days": 60,
        "metric_key": "monthly_churn",
        "first_breach_at": None,
    },
    "cac_payback_over_12": {
        "label": "CAC payback exceeds 12 months",
        "category": "hard",
        "state": "grey",
        "fired": False,
        "min_sample_size": 10,
        "sample_window_days": 30,
        "metric_key": None,
        "first_breach_at": None,
    },
    "poor_activation": {
        "label": "Activation consistently below threshold",
        "category": "soft",
        "state": "grey",
        "fired": False,
        "min_sample_size": 30,
        "sample_window_days": 30,
        "metric_key": "activation_rate",
        "first_breach_at": None,
    },
    "bad_margins": {
        "label": "Gross margins below sustainable level",
        "category": "soft",
        "state": "grey",
        "fired": False,
        "min_sample_size": 3,
        "sample_window_days": 60,
        "metric_key": "gross_margin",
        "first_breach_at": None,
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
    idea.archive_note = None
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea


_VALIDATION_STAGES = {"validating", "building", "retention", "growing"}


def _ensure_trigger_shape(trigger: dict) -> dict:
    """Ensure old-format triggers have the new fields with defaults."""
    trigger.setdefault("category", "hard")
    trigger.setdefault("state", "grey")
    trigger.setdefault("fired", False)
    return trigger


def evaluate_kill_triggers(db: Session, idea: Idea) -> dict:
    """Evaluate auto-evaluable kill triggers and return updated triggers dict.

    Only updates triggers that can be auto-evaluated. Manual triggers
    (founder_lost_conviction) are never auto-set. Already-fired triggers
    are never cleared.
    """
    triggers = copy.deepcopy(idea.kill_triggers) if idea.kill_triggers else {}

    # Ensure all triggers have the new shape (graceful migration)
    for key in triggers:
        _ensure_trigger_shape(triggers[key])

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
                    trigger["state"] = "red"

    # --- runway_below_floor ---
    trigger = triggers.get("runway_below_floor")
    if trigger and not trigger.get("fired"):
        profile = db.query(FounderProfile).filter_by(user_id=idea.user_id).first()
        if profile and profile.monthly_burn_rate > 0:
            runway_remaining = profile.current_savings / profile.monthly_burn_rate
            if runway_remaining < profile.runway_floor_months:
                trigger["fired"] = True
                trigger["state"] = "red"

    # founder_lost_conviction — manual only, never auto-evaluated

    # --- metric-driven triggers ---
    from app.services.metrics_service import evaluate_metric_triggers
    metric_states = evaluate_metric_triggers(db, idea)
    for ms in metric_states:
        key = ms["key"]
        if key in triggers:
            # Don't clear manually fired triggers
            if triggers[key].get("fired") and ms["state"] != "red":
                continue
            triggers[key]["state"] = ms["state"]
            triggers[key]["fired"] = ms["fired"]
            triggers[key]["first_breach_at"] = ms.get("first_breach_at")

    return triggers

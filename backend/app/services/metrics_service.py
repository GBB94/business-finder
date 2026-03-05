from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.idea import Idea
from app.models.metric_entry import MetricEntry

# ---------------------------------------------------------------------------
# Metric definitions — the single source of truth for known metric keys
# ---------------------------------------------------------------------------

METRIC_DEFINITIONS: dict[str, dict] = {
    # Gate 2 — Retention
    "day_30_retention": {"label": "Day-30 Retention", "unit": "%", "category": "retention"},
    "monthly_churn": {"label": "Monthly Churn", "unit": "%", "category": "retention"},
    "activation_rate": {"label": "Activation Rate", "unit": "%", "category": "retention"},
    "nrr": {"label": "Net Revenue Retention", "unit": "%", "category": "retention"},
    # Gate 3 — Economics
    "mrr": {"label": "MRR", "unit": "$", "category": "economics"},
    "gross_margin": {"label": "Gross Margin", "unit": "%", "category": "economics"},
    "cac": {"label": "CAC", "unit": "$", "category": "economics"},
    "ltv": {"label": "LTV", "unit": "$", "category": "economics"},
    "payment_processing_cost": {"label": "Payment Processing Cost", "unit": "%", "category": "economics"},
    "ai_inference_cost_pct": {"label": "AI Inference Cost", "unit": "%", "category": "economics"},
}

VALID_METRIC_KEYS = set(METRIC_DEFINITIONS.keys())

# ---------------------------------------------------------------------------
# Benchmarks keyed by product_use_frequency
# ---------------------------------------------------------------------------

BENCHMARKS: dict[str, dict[str, dict]] = {
    "daily": {
        "activation_rate": {"value": 50, "direction": "floor"},
        "day_30_retention": {"value": 40, "direction": "floor"},
        "monthly_churn": {"value": 5, "direction": "ceiling"},
    },
    "weekly": {
        "activation_rate": {"value": 30, "direction": "floor"},
        "day_30_retention": {"value": 25, "direction": "floor"},
        "monthly_churn": {"value": 8, "direction": "ceiling"},
    },
    "monthly": {
        "activation_rate": {"value": 30, "direction": "floor"},
        "day_30_retention": {"value": 20, "direction": "floor"},
        "monthly_churn": {"value": 10, "direction": "ceiling"},
    },
}

# ---------------------------------------------------------------------------
# Metric-driven kill trigger definitions
# ---------------------------------------------------------------------------

METRIC_KILL_TRIGGERS: dict[str, dict] = {
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
        "metric_key": None,  # computed metric
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_latest_entry(db: Session, idea_id: str, metric_key: str) -> Optional[MetricEntry]:
    return (
        db.query(MetricEntry)
        .filter_by(idea_id=idea_id, metric_key=metric_key)
        .order_by(MetricEntry.period_end.desc())
        .first()
    )


def _get_entries_for_key(db: Session, idea_id: str, metric_key: str, limit: int = 6) -> list[MetricEntry]:
    return (
        db.query(MetricEntry)
        .filter_by(idea_id=idea_id, metric_key=metric_key)
        .order_by(MetricEntry.period_end.desc())
        .limit(limit)
        .all()
    )


def _is_breaching(value: float, benchmark: dict) -> bool:
    if benchmark["direction"] == "floor":
        return value < benchmark["value"]
    else:  # ceiling
        return value > benchmark["value"]


def _compute_derived_metrics(db: Session, idea_id: str) -> list[dict]:
    """Compute LTV/CAC ratio, CAC payback months, effective margin."""
    computed = []

    mrr_entry = _get_latest_entry(db, idea_id, "mrr")
    cac_entry = _get_latest_entry(db, idea_id, "cac")
    ltv_entry = _get_latest_entry(db, idea_id, "ltv")
    churn_entry = _get_latest_entry(db, idea_id, "monthly_churn")
    margin_entry = _get_latest_entry(db, idea_id, "gross_margin")

    # LTV/CAC ratio
    ltv_val = ltv_entry.value if ltv_entry else None
    cac_val = cac_entry.value if cac_entry else None
    ltv_cac = None
    if ltv_val is not None and cac_val is not None and cac_val > 0:
        ltv_cac = round(ltv_val / cac_val, 2)
    computed.append({
        "metric_key": "ltv_cac_ratio",
        "label": "LTV / CAC Ratio",
        "unit": "x",
        "value": ltv_cac,
        "note": "Target: > 3x" if ltv_cac is not None else None,
    })

    # CAC payback months
    mrr_val = mrr_entry.value if mrr_entry else None
    margin_val = margin_entry.value if margin_entry else None
    payback = None
    if cac_val is not None and mrr_val is not None and mrr_val > 0:
        effective_mrr = mrr_val
        if margin_val is not None:
            effective_mrr = mrr_val * (margin_val / 100)
        if effective_mrr > 0:
            payback = round(cac_val / effective_mrr, 1)
    computed.append({
        "metric_key": "cac_payback_months",
        "label": "CAC Payback",
        "unit": "months",
        "value": payback,
        "note": "Target: < 12 months" if payback is not None else None,
    })

    # Effective margin (gross margin minus AI inference cost minus payment processing)
    ai_entry = _get_latest_entry(db, idea_id, "ai_inference_cost_pct")
    pp_entry = _get_latest_entry(db, idea_id, "payment_processing_cost")
    eff_margin = None
    if margin_val is not None:
        eff_margin = margin_val
        if ai_entry:
            eff_margin -= ai_entry.value
        if pp_entry:
            eff_margin -= pp_entry.value
        eff_margin = round(eff_margin, 1)
    computed.append({
        "metric_key": "effective_margin",
        "label": "Effective Margin",
        "unit": "%",
        "value": eff_margin,
        "note": "Gross margin minus processing & AI costs" if eff_margin is not None else None,
    })

    return computed


# ---------------------------------------------------------------------------
# Dashboard builder
# ---------------------------------------------------------------------------


def build_metrics_dashboard(db: Session, idea: Idea) -> dict:
    freq = idea.product_use_frequency
    if isinstance(freq, str):
        freq_key = freq
    elif freq is not None:
        freq_key = freq.value
    else:
        freq_key = None

    bench_set = BENCHMARKS.get(freq_key, {}) if freq_key else {}

    retention_metrics = []
    economics_metrics = []

    for key, defn in METRIC_DEFINITIONS.items():
        latest = _get_latest_entry(db, idea.id, key)
        history = _get_entries_for_key(db, idea.id, key)

        bench = bench_set.get(key)
        passes = None
        bench_value = None
        bench_direction = None
        if bench and latest:
            bench_value = bench["value"]
            bench_direction = bench["direction"]
            passes = not _is_breaching(latest.value, bench)

        metric = {
            "metric_key": key,
            "label": defn["label"],
            "unit": defn["unit"],
            "category": defn["category"],
            "latest_value": latest.value if latest else None,
            "sample_size": latest.sample_size if latest else None,
            "benchmark_value": bench_value,
            "benchmark_direction": bench_direction,
            "passes_benchmark": passes,
            "history": history,
        }

        if defn["category"] == "retention":
            retention_metrics.append(metric)
        else:
            economics_metrics.append(metric)

    computed = _compute_derived_metrics(db, idea.id)
    trigger_states = evaluate_metric_triggers(db, idea)

    return {
        "retention_metrics": retention_metrics,
        "economics_metrics": economics_metrics,
        "computed_metrics": computed,
        "trigger_states": trigger_states,
    }


# ---------------------------------------------------------------------------
# Kill trigger evaluation
# ---------------------------------------------------------------------------


def evaluate_metric_triggers(db: Session, idea: Idea) -> list[dict]:
    """Evaluate metric-driven kill triggers and return their states."""
    triggers = copy.deepcopy(idea.kill_triggers) if idea.kill_triggers else {}
    now = datetime.now(timezone.utc)

    freq = idea.product_use_frequency
    if isinstance(freq, str):
        freq_key = freq
    elif freq is not None:
        freq_key = freq.value
    else:
        freq_key = None

    bench_set = BENCHMARKS.get(freq_key, {}) if freq_key else {}
    results = []

    for trig_key, trig in triggers.items():
        # Skip triggers without metric tracking fields
        if "metric_key" not in trig and "category" not in trig:
            continue

        metric_key = trig.get("metric_key")
        category = trig.get("category", "hard")
        min_sample = trig.get("min_sample_size", 0)
        window_days = trig.get("sample_window_days", 30)
        state = trig.get("state", "grey")
        first_breach = trig.get("first_breach_at")

        # Special handling for computed metric triggers
        if trig_key == "cac_payback_over_12":
            computed = _compute_derived_metrics(db, idea.id)
            payback = next((c for c in computed if c["metric_key"] == "cac_payback_months"), None)
            payback_val = payback["value"] if payback else None

            if payback_val is None:
                state = "grey"
            elif payback_val > 12:
                if first_breach is None:
                    first_breach = now.isoformat()
                    state = "yellow"
                else:
                    breach_dt = datetime.fromisoformat(first_breach)
                    if breach_dt.tzinfo is None:
                        breach_dt = breach_dt.replace(tzinfo=timezone.utc)
                    elapsed = (now - breach_dt).days
                    state = "red" if elapsed >= window_days else "yellow"
            else:
                first_breach = None
                state = "grey"

            results.append({
                "key": trig_key,
                "label": trig["label"],
                "category": category,
                "state": state,
                "fired": state == "red",
                "metric_key": None,
            })
            continue

        if not metric_key:
            continue

        latest = _get_latest_entry(db, idea.id, metric_key)
        bench = bench_set.get(metric_key)

        if not latest or not bench:
            state = "grey"
            first_breach = None
        elif latest.sample_size is not None and latest.sample_size < min_sample:
            state = "grey"
            first_breach = None
        elif _is_breaching(latest.value, bench):
            if first_breach is None:
                first_breach = now.isoformat()
                state = "yellow"
            else:
                breach_dt = datetime.fromisoformat(first_breach)
                if breach_dt.tzinfo is None:
                    breach_dt = breach_dt.replace(tzinfo=timezone.utc)
                elapsed = (now - breach_dt).days
                state = "red" if elapsed >= window_days else "yellow"
        else:
            first_breach = None
            state = "grey"

        results.append({
            "key": trig_key,
            "label": trig["label"],
            "category": category,
            "state": state,
            "fired": state == "red",
            "metric_key": metric_key,
        })

    return results


def update_trigger_states_on_idea(db: Session, idea: Idea) -> dict:
    """Re-evaluate metric triggers and update the idea's kill_triggers JSON."""
    triggers = copy.deepcopy(idea.kill_triggers) if idea.kill_triggers else {}
    states = evaluate_metric_triggers(db, idea)

    for ts in states:
        key = ts["key"]
        if key in triggers:
            triggers[key]["state"] = ts["state"]
            triggers[key]["fired"] = ts["fired"]

    return triggers


# ---------------------------------------------------------------------------
# Snapshot builder (for monthly reviews)
# ---------------------------------------------------------------------------


def build_metrics_snapshot(db: Session, idea: Idea) -> dict:
    """Build a snapshot of current metric values for a monthly review."""
    snapshot: dict = {}
    for key in METRIC_DEFINITIONS:
        entry = _get_latest_entry(db, idea.id, key)
        if entry:
            snapshot[key] = {
                "value": entry.value,
                "sample_size": entry.sample_size,
                "period_start": entry.period_start.isoformat(),
                "period_end": entry.period_end.isoformat(),
            }

    # Add computed metrics
    computed = _compute_derived_metrics(db, idea.id)
    for c in computed:
        if c["value"] is not None:
            snapshot[c["metric_key"]] = {"value": c["value"]}

    return snapshot if snapshot else None

"""Country-aware email compliance classification.

Classifies outbound campaigns by the prospect's country to determine
which regulations apply and what per-email requirements must be met.

Hard blocks: countries where cold outbound is illegal without prior consent.
Soft requirements: unsubscribe links, physical address, opt-out mechanisms.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ComplianceResult:
    """Result of classifying a campaign's compliance requirements."""
    classification: str  # gdpr, uwg, casl, can_spam, pecr, unknown
    allowed: bool  # False = hard block, do not send
    requirements: list[str] = field(default_factory=list)  # per-email requirements
    warnings: list[str] = field(default_factory=list)  # advisory, non-blocking


# Countries where unsolicited cold email is effectively illegal without
# explicit prior consent. UWG (Germany, Austria) is the strictest.
# Canada (CASL) requires explicit consent for most B2B cold email too.
_HARD_BLOCK_COUNTRIES: set[str] = {
    "DE",  # Germany (UWG)
    "AT",  # Austria (UWG equivalent)
    "CA",  # Canada (CASL requires explicit consent, implied consent is narrow)
}

# GDPR countries: cold email is possible under "legitimate interest" but
# requires strict compliance (unsubscribe, physical address, clear sender ID,
# honest subject lines, and you must stop immediately on opt-out).
_GDPR_COUNTRIES: set[str] = {
    "BE", "BG", "CZ", "DK", "EE", "FI", "FR", "GR", "HR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK", "ES", "CY",
    # EEA
    "IS", "LI", "NO",
    # Post-Brexit UK uses its own PECR but similar requirements
}

# UK: PECR (Privacy and Electronic Communications Regulations)
_PECR_COUNTRIES: set[str] = {"GB"}

# Canada: CASL (Canadian Anti-Spam Legislation)
# Cold email is allowed to businesses under "implied consent" for
# a limited period, but requires strict unsubscribe and sender ID.
_CASL_COUNTRIES: set[str] = {"CA"}

# US: CAN-SPAM (least restrictive for B2B cold email)
_CAN_SPAM_COUNTRIES: set[str] = {"US"}


_GDPR_REQUIREMENTS: list[str] = [
    "unsubscribe_link",
    "physical_address",
    "clear_sender_identity",
    "honest_subject_line",
    "legitimate_interest_basis",
    "immediate_opt_out_compliance",
]

_PECR_REQUIREMENTS: list[str] = [
    "unsubscribe_link",
    "physical_address",
    "clear_sender_identity",
    "honest_subject_line",
    "b2b_only",  # PECR allows B2B without consent but not B2C
]

_CASL_REQUIREMENTS: list[str] = [
    "unsubscribe_link",
    "physical_address",
    "clear_sender_identity",
    "implied_consent_time_limit",  # 6 months for inquiries, 2 years for existing business
    "functional_unsubscribe_within_10_days",
]

_CAN_SPAM_REQUIREMENTS: list[str] = [
    "unsubscribe_link",
    "physical_address",
    "honest_subject_line",
    "clear_sender_identity",
    "honor_opt_out_within_10_days",
]

_UWG_BLOCK_REASON = (
    "Cold outbound email to this country requires explicit prior consent "
    "under UWG (Gesetz gegen den unlauteren Wettbewerb). Campaign blocked."
)


def classify_country(country_code: str | None) -> ComplianceResult:
    """Classify a single country code and return compliance requirements.

    Args:
        country_code: ISO 3166-1 alpha-2 code, or None if unknown.
    """
    if not country_code:
        return ComplianceResult(
            classification="unknown",
            allowed=True,
            requirements=_CAN_SPAM_REQUIREMENTS,  # fall back to strictest common denominator
            warnings=["Country unknown. Defaulting to CAN-SPAM requirements."],
        )

    cc = country_code.upper().strip()

    if cc in _HARD_BLOCK_COUNTRIES:
        return ComplianceResult(
            classification="uwg",
            allowed=False,
            requirements=[],
            warnings=[_UWG_BLOCK_REASON],
        )

    if cc in _PECR_COUNTRIES:
        return ComplianceResult(
            classification="pecr",
            allowed=True,
            requirements=_PECR_REQUIREMENTS,
        )

    if cc in _GDPR_COUNTRIES:
        return ComplianceResult(
            classification="gdpr",
            allowed=True,
            requirements=_GDPR_REQUIREMENTS,
        )

    if cc in _CASL_COUNTRIES:
        return ComplianceResult(
            classification="casl",
            allowed=True,
            requirements=_CASL_REQUIREMENTS,
        )

    if cc in _CAN_SPAM_COUNTRIES:
        return ComplianceResult(
            classification="can_spam",
            allowed=True,
            requirements=_CAN_SPAM_REQUIREMENTS,
        )

    # Rest of world: apply CAN-SPAM as baseline
    return ComplianceResult(
        classification="unknown",
        allowed=True,
        requirements=_CAN_SPAM_REQUIREMENTS,
        warnings=[f"No specific regulation mapped for {cc}. Applying CAN-SPAM baseline."],
    )


def classify_campaign_prospects(countries: list[str | None]) -> ComplianceResult:
    """Classify a campaign based on all prospect countries.

    Uses the strictest applicable regulation. If ANY prospect is in a
    hard-block country, those prospects must be excluded (not the whole
    campaign, just those individuals).

    Returns the dominant classification and merged requirements.
    """
    if not countries:
        return classify_country(None)

    blocked_countries: list[str] = []
    all_requirements: set[str] = set()
    all_warnings: list[str] = []
    classifications: dict[str, int] = {}

    for cc in countries:
        result = classify_country(cc)
        classifications[result.classification] = classifications.get(result.classification, 0) + 1
        all_requirements.update(result.requirements)
        all_warnings.extend(result.warnings)
        if not result.allowed and cc:
            blocked_countries.append(cc)

    if blocked_countries:
        all_warnings.insert(
            0,
            f"Prospects in {', '.join(set(blocked_countries))} must be excluded (UWG hard block).",
        )

    # Dominant classification = most common
    dominant = max(classifications, key=classifications.get)  # type: ignore[arg-type]

    return ComplianceResult(
        classification=dominant,
        allowed=True,  # campaign-level: allowed, but individual prospects may be blocked
        requirements=sorted(all_requirements),
        warnings=all_warnings,
    )

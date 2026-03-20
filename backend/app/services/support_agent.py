"""Support agent: inbox triage, response drafting, escalation, feature extraction.

Phase 3 of LaunchPad. Handles inbound customer emails by:
1. Triaging (classify intent, urgency, confidence)
2. Drafting responses using thread history for context
3. Escalating to founder when confidence is below threshold or SLA breached
4. Extracting feature requests into the IdeaScope evidence pipeline

All responses are draft-only in Phase 3. Human sends until trust builds.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.models.evidence import Evidence, EvidenceType, GateLabel, Sentiment, SourceType
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent
from app.models.support_thread import SupportThread

logger = logging.getLogger(__name__)

# Confidence threshold: below this, escalate to founder instead of drafting
CONFIDENCE_THRESHOLD = 0.7

# Escalation SLA: flag threads with no response after this many hours
ESCALATION_SLA_HOURS = 4

TRIAGE_SYSTEM_PROMPT = """\
You are a support triage agent for a SaaS product. You receive inbound \
customer emails and must classify them.

Analyze the email and respond with valid JSON:
{
  "intent": "bug_report" | "feature_request" | "billing" | "how_to" | "praise" | "complaint" | "other",
  "urgency": "low" | "medium" | "high" | "critical",
  "confidence": 0.0-1.0,
  "summary": "one-line summary of the issue",
  "suggested_category": "technical" | "billing" | "product" | "general",
  "is_feature_request": true/false,
  "feature_description": "description if is_feature_request is true, else null"
}

Consider urgency levels:
- critical: service is down, data loss, security issue
- high: blocking issue, payment failed, cannot use core feature
- medium: non-blocking bug, confusion about functionality
- low: feature request, general question, praise

Set confidence to how confident you are that you understand the issue \
and could draft a helpful response. Lower confidence for ambiguous, \
multi-part, or domain-specific questions.
"""

DRAFT_SYSTEM_PROMPT = """\
You are a support agent drafting a response to a customer email. \
You have access to the conversation thread history.

Guidelines:
- Be helpful, concise, and professional
- If you are unsure about something, say so honestly
- Do not make promises about timelines or features
- For bug reports, acknowledge the issue and explain next steps
- For feature requests, thank them and note it has been recorded
- For billing issues, be empathetic and direct
- Sign off as "The [product_name] Team"

Respond with valid JSON:
{
  "draft_response": "the full email response text",
  "confidence": 0.0-1.0,
  "internal_notes": "any notes for the founder about this thread",
  "needs_escalation": true/false,
  "escalation_reason": "reason if needs_escalation is true, else null"
}

Set confidence based on how sure you are the response is accurate and \
helpful. Lower for ambiguous issues, technical questions outside your \
context, or billing disputes that may need manual review.
"""


async def triage_email(
    *,
    subject: str,
    body: str,
    sender_email: str,
    product_name: str,
    model: str | None = None,
) -> dict:
    """Classify an inbound email. Returns triage result with intent, urgency, confidence."""
    model = model or settings.CLAUDE_MODEL_HAIKU

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    user_content = (
        f"Product: {product_name}\n"
        f"From: {sender_email}\n"
        f"Subject: {subject}\n\n"
        f"Email body:\n{body}"
    )

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=TRIAGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text
    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"intent": "other", "urgency": "medium", "confidence": 0.3, "summary": raw[:200]}

    return {
        "triage": result,
        "tokens_used": tokens_used,
        "model_version": model,
        "raw_response": raw,
    }


async def draft_response(
    *,
    thread_messages: list[dict],
    product_name: str,
    product_context: str,
    model: str | None = None,
) -> dict:
    """Draft a response given conversation thread history."""
    model = model or settings.CLAUDE_MODEL_HAIKU

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Build conversation context
    thread_text = ""
    for msg in thread_messages:
        direction = "Customer" if msg.get("direction") == "inbound" else "Support"
        thread_text += f"\n[{direction}] ({msg.get('timestamp', 'unknown')}):\n{msg.get('body', '')}\n"

    user_content = (
        f"Product: {product_name}\n"
        f"Product context: {product_context}\n\n"
        f"Conversation thread:{thread_text}\n\n"
        f"Draft a response to the most recent customer message."
    )

    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=DRAFT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text
    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "draft_response": raw,
            "confidence": 0.3,
            "internal_notes": "Failed to parse structured response",
            "needs_escalation": True,
            "escalation_reason": "Unstructured AI output",
        }

    return {
        "draft": result,
        "tokens_used": tokens_used,
        "model_version": model,
        "raw_response": raw,
    }


def get_or_create_thread(
    db: Session,
    launch_id: str,
    customer_email: str,
    subject: str | None = None,
) -> SupportThread:
    """Find an existing open thread for this customer or create a new one."""
    thread = (
        db.query(SupportThread)
        .filter(
            SupportThread.launch_id == launch_id,
            SupportThread.customer_email == customer_email,
            SupportThread.status.in_(["open", "waiting_on_customer"]),
        )
        .order_by(SupportThread.created_at.desc())
        .first()
    )
    if thread:
        # Reopen threads where the customer is replying to a waiting conversation
        if thread.status == "waiting_on_customer":
            thread.status = "open"
            thread.updated_at = datetime.now(timezone.utc)
            db.flush()
        return thread

    thread = SupportThread(
        launch_id=launch_id,
        customer_email=customer_email,
        subject=subject,
        status="open",
        messages=[],
    )
    db.add(thread)
    db.flush()
    return thread


def add_message_to_thread(
    db: Session,
    thread: SupportThread,
    direction: str,
    body: str,
    message_id: str | None = None,
) -> SupportThread:
    """Append a message to the thread."""
    messages = list(thread.messages or [])
    messages.append({
        "direction": direction,
        "body": body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_id": message_id,
    })
    thread.messages = messages
    thread.message_count = len(messages)
    thread.updated_at = datetime.now(timezone.utc)
    db.flush()
    return thread


def check_escalation_sla(db: Session, launch_id: str) -> list[SupportThread]:
    """Find threads that have breached the 4-hour escalation SLA.

    Returns threads that are open, have at least one inbound message,
    and the last inbound message is older than ESCALATION_SLA_HOURS.
    Uses the timestamp of the latest inbound message, not thread creation.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ESCALATION_SLA_HOURS)

    threads = (
        db.query(SupportThread)
        .filter(
            SupportThread.launch_id == launch_id,
            SupportThread.status == "open",
            SupportThread.escalated_at.is_(None),
        )
        .all()
    )

    sla_breached = []
    for thread in threads:
        messages = thread.messages or []
        if not messages:
            continue
        # Check if last message is inbound (customer waiting)
        last_msg = messages[-1]
        if last_msg.get("direction") != "inbound":
            continue
        # Use the timestamp of the last inbound message for SLA check
        msg_ts = last_msg.get("timestamp")
        if not msg_ts:
            continue
        try:
            msg_time = datetime.fromisoformat(msg_ts)
        except (ValueError, TypeError):
            continue
        if msg_time <= cutoff:
            sla_breached.append(thread)

    return sla_breached


def escalate_thread(
    db: Session,
    thread: SupportThread,
    reason: str,
) -> SupportThread:
    """Mark a thread as escalated."""
    thread.status = "escalated"
    thread.escalated_at = datetime.now(timezone.utc)
    thread.escalation_reason = reason
    thread.updated_at = datetime.now(timezone.utc)
    db.flush()
    return thread


def extract_feature_request(
    db: Session,
    thread: SupportThread,
    launch: LaunchInstance,
    feature_description: str,
) -> Evidence:
    """Promote a feature request from a support thread into IdeaScope evidence."""
    evidence = Evidence(
        idea_id=launch.idea_id,
        user_id=launch.user_id,
        gate=GateLabel.gate_2,
        evidence_type=EvidenceType.customer_conversation,
        title=f"Feature request: {feature_description[:100]}",
        content={
            "source": "support_thread",
            "thread_id": thread.id,
            "customer_email": thread.customer_email,
            "feature_description": feature_description,
            "thread_subject": thread.subject,
            "message_count": thread.message_count,
        },
        source_type=SourceType.conversation,
        sentiment=Sentiment.positive,
        tags=["feature_request", "support_extracted"],
    )
    db.add(evidence)
    db.flush()

    # Link back to thread
    thread.feature_request_extracted = True
    thread.evidence_id = evidence.id
    thread.updated_at = datetime.now(timezone.utc)
    db.flush()

    # Create operational event for visibility
    event = OperationalEvent(
        launch_id=thread.launch_id,
        event_type="feature_request_extracted",
        payload={
            "thread_id": thread.id,
            "evidence_id": evidence.id,
            "feature_description": feature_description[:500],
        },
    )
    db.add(event)
    db.flush()

    return evidence

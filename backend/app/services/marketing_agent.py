"""Marketing agent for LaunchPad: cold email, social, and content generation.

All marketing tasks are manual-trigger only in Phase 2. The agent generates
drafts and plans; sending/publishing requires approval gates.
"""
from __future__ import annotations

import logging
from typing import Optional

import anthropic

from app.config import settings
from app.models.agent_task import AgentTask

logger = logging.getLogger(__name__)


async def draft_cold_emails(
    idea_name: str,
    idea_audience: str,
    idea_problem: str,
    idea_solution: str,
    prospect_count: int = 5,
    model: str | None = None,
) -> dict:
    """Generate personalized cold email drafts for an idea.

    Returns a dict with drafts, subject lines, and token usage.
    """
    model = model or settings.CLAUDE_MODEL_HAIKU

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are a cold email specialist. Generate {prospect_count} cold email drafts "
                    f"for the following product:\n\n"
                    f"Product: {idea_name}\n"
                    f"Target Audience: {idea_audience}\n"
                    f"Problem it solves: {idea_problem}\n"
                    f"Solution: {idea_solution}\n\n"
                    f"For each email, provide:\n"
                    f"1. A compelling subject line (under 50 chars)\n"
                    f"2. The email body (3-5 sentences, personalization placeholders like {{first_name}}, {{company}})\n"
                    f"3. A clear CTA\n\n"
                    f"Return as a JSON object with a 'drafts' array, each item having "
                    f"'subject', 'body', and 'cta' fields. Keep the tone professional but conversational. "
                    f"No hype words. Focus on the problem, not the product."
                ),
            }
        ],
    )

    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return {
        "raw_response": response.content[0].text,
        "tokens_used": tokens_used,
        "model_version": model,
        "draft_count": prospect_count,
    }


async def draft_social_post(
    idea_name: str,
    idea_audience: str,
    idea_problem: str,
    idea_solution: str,
    platform: str = "twitter",
    milestone: str | None = None,
    model: str | None = None,
) -> dict:
    """Generate a social media post draft.

    Returns a dict with the draft post and token usage.
    """
    model = model or settings.CLAUDE_MODEL_HAIKU

    platform_rules = {
        "twitter": "Max 280 characters. No hashtag spam (1-2 max). Thread format OK.",
        "linkedin": "Professional tone. 1-3 paragraphs. Can be longer.",
    }

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write a {platform} post for:\n\n"
                    f"Product: {idea_name}\n"
                    f"Audience: {idea_audience}\n"
                    f"Problem: {idea_problem}\n"
                    f"Solution: {idea_solution}\n"
                    f"{f'Milestone/context: {milestone}' if milestone else ''}\n\n"
                    f"Platform rules: {platform_rules.get(platform, 'Keep it concise.')}\n\n"
                    f"Return as JSON with 'post' (the text) and 'notes' (any suggestions). "
                    f"Tone: authentic, not corporate. No emoji overload."
                ),
            }
        ],
    )

    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return {
        "raw_response": response.content[0].text,
        "tokens_used": tokens_used,
        "model_version": model,
        "platform": platform,
    }


async def write_content(
    idea_name: str,
    idea_audience: str,
    idea_problem: str,
    idea_solution: str,
    content_type: str = "blog_post",
    topic: str | None = None,
    model: str | None = None,
) -> dict:
    """Generate marketing content (blog post, landing page copy, etc.).

    Returns a dict with the content and token usage.
    """
    model = model or settings.CLAUDE_MODEL

    content_prompts = {
        "blog_post": "Write a blog post (800-1200 words) that addresses a pain point the target audience has.",
        "landing_page": "Write landing page copy: hero headline, subheadline, 3 benefit sections, CTA.",
        "faq": "Write 8-10 FAQ entries covering common questions about this product.",
        "email_sequence": "Write a 3-email welcome sequence for new signups.",
    }

    prompt = content_prompts.get(content_type, f"Write {content_type} content.")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Product: {idea_name}\n"
                    f"Audience: {idea_audience}\n"
                    f"Problem: {idea_problem}\n"
                    f"Solution: {idea_solution}\n"
                    f"{f'Topic: {topic}' if topic else ''}\n\n"
                    f"{prompt}\n\n"
                    f"Return as JSON with 'title', 'content', and 'meta_description' fields."
                ),
            }
        ],
    )

    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return {
        "raw_response": response.content[0].text,
        "tokens_used": tokens_used,
        "model_version": model,
        "content_type": content_type,
    }

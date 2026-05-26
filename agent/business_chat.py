"""
Conversational front-end for the Business Agent.

The agent interviews the user (headcount, roles, per-role needs, budget, office
basics) and, once it has enough, emits a structured spec wrapped in
<<SPEC>>...<<END>> sentinels that the app extracts and feeds to the build engine.
"""

import json
import re

from .config import chutes, CHUTES_MODEL
from .prompts import BUSINESS_CHAT_SYSTEM_PROMPT


_SPEC_RE = re.compile(r"<<SPEC>>\s*(\{.*?\})\s*<<END>>", re.DOTALL)


def chat_turn(messages: list[dict], company_context: dict | None = None) -> str:
    """One conversation turn. `messages` is the running [{role, content}] history."""
    ctx_str = (
        f"Company: {company_context.get('name', '?')} | "
        f"Industry: {company_context.get('industry', '?')} | "
        f"Size: {company_context.get('size', '?')} employees | "
        f"Location: {company_context.get('location', 'Kuala Lumpur')}"
    ) if company_context else "Not yet provided."
    system = BUSINESS_CHAT_SYSTEM_PROMPT.replace("{company_context}", ctx_str)
    user_turns = sum(1 for m in messages if m["role"] == "user")
    if user_turns >= 3:
        system += "\n\nCRITICAL: The user has provided enough information. You MUST emit <<SPEC>> NOW using your best inferences for any missing values. No more questions."
    response = chutes.chat.completions.create(
        model=CHUTES_MODEL,
        messages=[{"role": "system", "content": system}, *messages],
        temperature=0.4,
        max_tokens=500,
    )
    return response.choices[0].message.content


def extract_spec(text: str) -> dict | None:
    """Pull the structured spec from an assistant message, or None if not present."""
    match = _SPEC_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def clean_for_display(text: str) -> str:
    """Strip the <<SPEC>>...<<END>> block so the user only sees the natural summary."""
    return _SPEC_RE.sub("", text).strip()

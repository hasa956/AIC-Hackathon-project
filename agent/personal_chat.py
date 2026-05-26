"""
Optional detail gathering and refinement chat for personal PC builds.
"""

import json
import re

from .config import chutes, CHUTES_MODEL
from .prompts import PERSONAL_REFINEMENT_PROMPT, PERSONAL_DETAILS_PROMPT

_REFINE_RE   = re.compile(r"<<REFINE>>\s*(\{.*?\})\s*<<END>>", re.DOTALL)
_DETAILS_RE  = re.compile(r"<<DETAILS>>\s*(\{.*?\})\s*<<END>>", re.DOTALL)


def personal_chat_turn(messages: list[dict], build_summary: str = "") -> str:
    system = PERSONAL_REFINEMENT_PROMPT.replace("{build_context}", build_summary or "Not provided.")
    response = chutes.chat.completions.create(
        model=CHUTES_MODEL,
        messages=[{"role": "system", "content": system}, *messages],
        temperature=0.4,
        max_tokens=600,
    )
    return response.choices[0].message.content


def extract_refinement(text: str) -> dict | None:
    match = _REFINE_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def clean_refinement_display(text: str) -> str:
    return _REFINE_RE.sub("", text).strip()


def details_chat_turn(messages: list[dict], purpose_summary: str = "") -> str:
    """Chat to gather build details after initial purpose selection."""
    system = PERSONAL_DETAILS_PROMPT.replace("{purpose_context}", purpose_summary or "Not specified.")
    user_turns = sum(1 for m in messages if m["role"] == "user")
    if user_turns >= 4:
        system += "\n\nCRITICAL: The user has answered all 4 questions. You MUST emit <<DETAILS>> NOW. No more questions under any circumstances."
    response = chutes.chat.completions.create(
        model=CHUTES_MODEL,
        messages=[{"role": "system", "content": system}, *messages],
        temperature=0.4,
        max_tokens=600,
    )
    return response.choices[0].message.content


def extract_details(text: str) -> dict | None:
    """Extract build details spec from chat response."""
    match = _DETAILS_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def clean_details_display(text: str) -> str:
    """Strip <<DETAILS>> block for display."""
    return _DETAILS_RE.sub("", text).strip()

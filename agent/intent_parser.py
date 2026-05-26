"""
Layer 1 — Intent Parser.

Takes user form input (Personal or Business mode) and produces a canonical
intent JSON consumed by Layer 2 (catalogue search) and Layer 3 (reasoning).

Single LLM call to Chutes / Gemma 4 31B (fast model).

Entry point: parse_intent(user_input: dict) -> dict
"""

import json
import re

from .config import chutes, CHUTES_FAST_MODEL
from .prompts import INTENT_PARSER_SYSTEM_PROMPT


class IntentValidationError(Exception):
    """Raised when the parsed intent is missing critical fields.

    Caller should catch this and ask the user to clarify, NOT continue with bad data.
    """
    pass


# ── Internal helpers ─────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Pull JSON out of LLM output. Handles raw JSON, ```json fences, and embedded JSON."""
    text = text.strip()

    # Strip code fences like ```json ... ```
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        # Otherwise grab the first {...} block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    return json.loads(text)


def _build_user_message(user_input: dict) -> str:
    """Construct the user-facing prompt from the form data dict."""
    parts = []
    mode = user_input.get("mode", "personal")
    parts.append(f"Mode: {mode}")

    if mode == "personal":
        if user_input.get("purposes"):
            parts.append(f"Purposes (multi-select): {', '.join(user_input['purposes'])}")
        if user_input.get("budget_min_rm") is not None and user_input.get("budget_rm") is not None:
            parts.append(
                f"Budget range: RM{user_input['budget_min_rm']} – RM{user_input['budget_rm']} "
                f"(aim within this range; never exceed the upper bound)"
            )
        elif user_input.get("budget_rm") is not None:
            parts.append(f"Budget: RM{user_input['budget_rm']}")
        if user_input.get("owned_parts"):
            parts.append(f"Already owns: {', '.join(user_input['owned_parts'])}")
        if user_input.get("aesthetic_style"):
            parts.append(f"Aesthetic style: {user_input['aesthetic_style']}")
        if user_input.get("noise_preference"):
            parts.append(f"Noise preference: {user_input['noise_preference']}")
        if user_input.get("location"):
            parts.append(f"Location: {user_input['location']}")

    elif mode == "business":
        profile = user_input.get("company_profile", {})
        parts.append(f"Company: {profile.get('name', 'unspecified')}")
        parts.append(f"Industry: {profile.get('industry', 'unspecified')}")
        parts.append(f"Size: {profile.get('size', 'unspecified')}")
        role = user_input.get("role")
        if role:
            parts.append(f"Role to spec: {role['role']} ({role.get('count', 1)} units)")
        if user_input.get("budget_rm_per_unit") is not None:
            parts.append(f"Budget per unit: RM{user_input['budget_rm_per_unit']}")

    if user_input.get("free_text"):
        parts.append(f"User's own words: \"{user_input['free_text']}\"")

    return "\n".join(parts)


def _validate(intent: dict) -> None:
    """Sanity-check the parsed intent. Raises IntentValidationError if bad."""
    errors = []

    if not intent.get("use_cases"):
        errors.append("No use cases identified. Please describe what you'll use the PC for.")

    if not intent.get("required_categories"):
        errors.append("No build categories required — did you exclude everything?")

    budget = intent.get("budget_rm")
    if budget is not None and budget < 1000:
        errors.append(f"Budget RM{budget} is too low for a desktop PC. Minimum reasonable: RM1500.")

    if errors:
        raise IntentValidationError(" | ".join(errors))


# ── Public API ───────────────────────────────────────────────────────

def parse_intent(user_input: dict, max_retries: int = 1) -> dict:
    """
    Parse user input into canonical intent JSON.

    Args:
        user_input: dict with form fields. Examples:

            Personal mode:
                {
                    "mode": "personal",
                    "purposes": ["gaming"],
                    "budget_rm": 5000,
                    "owned_parts": ["monitor", "keyboard"],
                    "aesthetic_style": "stealth",
                    "noise_preference": "balanced",
                    "free_text": "I play AAA games at 1440p"
                }

            Business mode (call once per role to get one intent per role profile):
                {
                    "mode": "business",
                    "company_profile": {"name": "...", "industry": "...", "size": "..."},
                    "role": {"role": "developer", "count": 5},
                    "budget_rm_per_unit": 6000
                }

        max_retries: how many times to retry on JSON parse failure.

    Returns:
        Canonical intent dict, ready for Layer 2. Always contains:
            mode, use_cases, budget_rm, budget_tier, excluded_categories,
            required_categories, style_profile, noise_preference,
            priority_weights, location, notes, raw_brief

    Raises:
        IntentValidationError: if intent is missing critical fields.
            Caller should ask user to clarify and retry.
        json.JSONDecodeError: if LLM cannot produce valid JSON after retries.
    """
    user_message = _build_user_message(user_input)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = chutes.chat.completions.create(
                model=CHUTES_FAST_MODEL,
                messages=[
                    {"role": "system", "content": INTENT_PARSER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=1500,
            )
            raw = response.choices[0].message.content
            intent = _extract_json(raw)

            # Keep the raw brief for downstream logging / debug
            intent["raw_brief"] = user_input.get("free_text") or user_message

            _validate(intent)
            return intent

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            if attempt < max_retries:
                continue
            raise

    raise RuntimeError(f"Intent parsing failed after retries: {last_error}")
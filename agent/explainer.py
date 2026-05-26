"""
"Explain this component" feature.

Lazy on-click: when the user expands a component in the BOM, this fires one
Chutes API call (DeepSeek-V3.2) to explain the choice in plain English.
"""

from .config import chutes, CHUTES_MODEL


EXPLAINER_SYSTEM_PROMPT = """You are a friendly PC hardware expert talking to a non-technical user.

Explain in 3-4 conversational sentences WHY this specific component was chosen for this build. Cover:
1. What this component is and what it does in the system
2. Why it suits this user's specific use case and budget
3. A brief comparison with the alternatives that were considered

No bullet points, no headings, no markdown. Talk like you are advising a friend over coffee. Keep it warm and plain-English."""


def _build_user_message(item: dict, build: dict, alternatives: list[dict] | None) -> str:
    intent = build.get("intent", {})
    use_cases = ", ".join(intent.get("use_cases", []))
    budget = intent.get("budget_rm", "unspecified")
    tier = intent.get("budget_tier", "")
    style = intent.get("style_profile", {}).get("vibe", "")
    noise = intent.get("noise_preference", "")

    lines = [
        f"User intent: {use_cases} ({tier} tier, budget RM{budget})",
        f"Aesthetic: {style}, Noise: {noise}",
        "",
        f"CHOSEN: {item['name']} ({item['category']}) at RM{item.get('unit_price_rm')}",
        f"Picker's rationale: {item.get('rationale', 'n/a')}",
    ]

    if alternatives:
        lines.append("\nAlternatives that were considered but not chosen:")
        for alt in alternatives:
            vendors = alt.get("vendors", [])
            best = min(vendors, key=lambda v: v.get("price_rm", 9_999_999), default={})
            lines.append(f"- {alt['name']}: RM{best.get('price_rm', '?')}")
    return "\n".join(lines)


def explain_component(
    item: dict,
    build: dict,
    alternatives: list[dict] | None = None,
    stream: bool = False,
):
    """
    Generate a plain-English explanation for one item in the build.

    Args:
        item: chosen item from build['items']  (must include name, category,
              unit_price_rm, rationale)
        build: full build dict (uses build['intent'] for context)
        alternatives: optional list of candidate dicts that were not picked
        stream: if True, returns a generator yielding text chunks

    Returns:
        Explanation string, or generator if stream=True
    """
    user_message = _build_user_message(item, build, alternatives)
    messages = [
        {"role": "system", "content": EXPLAINER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    if stream:
        return _stream(messages)

    response = chutes.chat.completions.create(
        model=CHUTES_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=400,
    )
    return response.choices[0].message.content.strip()


def _stream(messages):
    """Generator yielding chunks of the explanation as they arrive."""
    stream = chutes.chat.completions.create(
        model=CHUTES_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=400,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

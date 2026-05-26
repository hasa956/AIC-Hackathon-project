"""
Layer 3 - Reasoning Layer.

Takes intent + Layer 2 candidates, calls DeepSeek-V3.2 on Chutes to pick
the best combination, validates compatibility in pure Python, retries up to
twice on conflicts, then enriches the build with vendor pricing & shipping.

Entry point: generate_build(intent, candidates) -> dict
"""

import json
import re
from copy import deepcopy

from .config import chutes, CHUTES_MODEL
from .prompts import REASONER_SYSTEM_PROMPT
from .compatibility import validate_build
from .tools import calculate_total_cost


class BuildGenerationError(Exception):
    """Raised when no compatible build can be produced after all retries."""
    pass


# ── Helpers ──────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    return json.loads(text)


def _cheapest_vendor(product: dict) -> dict:
    """Return the cheapest vendor entry for a product."""
    vendors = product.get("vendors", [])
    if not vendors:
        return {}
    return min(vendors, key=lambda v: v.get("price_rm", float("inf")))


def _format_candidates_for_prompt(candidates: dict) -> str:
    """
    Build a compact human-readable candidate list for the LLM prompt.
    One section per category, one bullet per candidate with key specs and best price.
    """
    sections = []
    for category, products in candidates.items():
        if not products:
            sections.append(f"\n{category.upper()} candidates: NONE AVAILABLE")
            continue
        lines = [f"\n{category.upper()} candidates (pick 1):"]
        for p in products:
            specs = p.get("specs", {})
            spec_str = ", ".join(f"{k}={v}" for k, v in specs.items()
                                 if v not in (None, [], "") and not isinstance(v, dict))
            cheapest = _cheapest_vendor(p)
            price_str = f"RM{cheapest.get('price_rm', '?')} from {cheapest.get('name', '?')}"
            lines.append(f"- {p['id']} \"{p['name']}\" | {spec_str} | {price_str}")
        sections.append("\n".join(lines))
    return "\n".join(sections)


def _format_intent_for_prompt(intent: dict) -> str:
    """Compact intent summary for the user message."""
    return (
        f"Mode: {intent.get('mode')}\n"
        f"Use cases: {', '.join(intent.get('use_cases', []))}\n"
        f"Budget: RM{intent.get('budget_rm')} ({intent.get('budget_tier')})\n"
        f"Excluded (already owned): {', '.join(intent.get('excluded_categories', [])) or 'none'}\n"
        f"Style: {intent.get('style_profile', {}).get('vibe')}, "
        f"RGB: {intent.get('style_profile', {}).get('rgb_preference')}\n"
        f"Noise: {intent.get('noise_preference')}\n"
        f"Priority weights: {intent.get('priority_weights')}\n"
        f"Location: {intent.get('location')}"
    )


def _resolve_picks(picks: list, candidates: dict) -> dict:
    """
    Given the LLM's list of {category, product_id, vendor_name, unit_price_rm},
    look up the full product dicts from the candidate pool.
    Returns dict[category, full_product_dict] with vendor info attached.
    """
    by_id = {p["id"]: p for products in candidates.values() for p in products}
    build = {}
    for pick in picks:
        cat = pick["category"]
        pid = pick["product_id"]
        product = by_id.get(pid)
        if not product:
            continue
        product = deepcopy(product)
        product["_picked_vendor"] = pick.get("vendor_name")
        product["_picked_price_rm"] = pick.get("unit_price_rm")
        product["_rationale"] = pick.get("rationale", "")
        build[cat] = product
    return build


def _call_llm_for_build(
    intent: dict,
    candidates: dict,
    prior_errors: list[str] | None = None,
) -> dict:
    """One LLM call. Returns the parsed JSON proposal."""
    user_message_parts = [
        "USER INTENT:",
        _format_intent_for_prompt(intent),
        "\n",
        "AVAILABLE CANDIDATES:",
        _format_candidates_for_prompt(candidates),
    ]
    if prior_errors:
        user_message_parts.extend([
            "\n",
            "PREVIOUS ATTEMPT FAILED with these compatibility errors. Pick a DIFFERENT combination that fixes ALL of them:",
            *[f"- {e}" for e in prior_errors],
        ])

    response = chutes.chat.completions.create(
        model=CHUTES_MODEL,
        messages=[
            {"role": "system", "content": REASONER_SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_message_parts)},
        ],
        temperature=0.2,
        max_tokens=3500,
    )
    raw = response.choices[0].message.content
    return _extract_json(raw)


# ── Public API ───────────────────────────────────────────────────────

def generate_build(
    intent: dict,
    candidates: dict,
    max_retries: int = 2,
) -> dict:
    """
    Generate a compatible PC build from candidates.

    Args:
        intent:     Layer 1 output (canonical intent dict).
        candidates: Layer 2 output (dict[category, list[product]]).
        max_retries: how many times to retry on compatibility failure.

    Returns:
        Full build dict:
        {
            "items": [...],                # picked products with vendor + price
            "compatibility_issues": [],    # empty if valid
            "build_rationale": str,
            "warnings": [...],
            "costs": {
                "subtotal_rm", "shipping_total_rm", "sst_rm",
                "grand_total_rm", "by_vendor"
            },
            "intent": {...}                # echoed for downstream display
        }

    Raises:
        BuildGenerationError: if no compatible build can be produced after retries.
    """
    prior_errors: list[str] = []

    for attempt in range(max_retries + 1):
        proposal = _call_llm_for_build(intent, candidates, prior_errors or None)
        build = _resolve_picks(proposal.get("items", []), candidates)
        errors = validate_build(build)

        if not errors:
            # Build is compatible — enrich with logistics
            items_for_cost = [
                {
                    "category": cat,
                    "product_id": prod["id"],
                    "name": prod["name"],
                    "vendor_name": prod.get("_picked_vendor"),
                    "unit_price_rm": prod.get("_picked_price_rm"),
                }
                for cat, prod in build.items()
            ]
            costs = calculate_total_cost(items_for_cost, intent.get("location", "Kuala Lumpur"))

            warnings_list = list(proposal.get("warnings", []))
            budget_rm = intent.get("budget_rm")
            budget_exceeded = False
            if budget_rm and costs["grand_total_rm"] > budget_rm:
                overage = round(costs["grand_total_rm"] - budget_rm, 2)
                warnings_list.append(
                    f"OVER BUDGET: Total (incl. SST & shipping) RM{costs['grand_total_rm']:,.2f} "
                    f"exceeds budget RM{budget_rm:,.2f} by RM{overage:,.2f}."
                )
                budget_exceeded = True

            return {
                "items": [
                    {
                        "category": cat,
                        "product_id": prod["id"],
                        "name": prod["name"],
                        "vendor_name": prod.get("_picked_vendor"),
                        "unit_price_rm": prod.get("_picked_price_rm"),
                        "rationale": prod.get("_rationale", ""),
                        "official_page": prod.get("official_page"),
                        "specs": prod.get("specs", {}),
                    }
                    for cat, prod in build.items()
                ],
                "compatibility_issues": [],
                "build_rationale": proposal.get("build_rationale", ""),
                "warnings": warnings_list,
                "budget_exceeded": budget_exceeded,
                "costs": costs,
                "intent": intent,
                "attempts": attempt + 1,
            }

        # Compatibility failed — log errors and retry
        prior_errors = errors

    raise BuildGenerationError(
        f"Failed to produce a compatible build after {max_retries + 1} attempts. "
        f"Last errors: {prior_errors}"
    )
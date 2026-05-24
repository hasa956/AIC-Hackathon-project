"""
Diagnostic helpers for Layer 2 graceful failure handling.

When a category returns zero candidates from search, this module produces a
user-friendly explanation (which filter dropped them, what the user can do).
"""

from .catalogue import load_catalogue


VISUAL_CATEGORIES = {"case", "case_fans", "cooler", "ram"}


def diagnose_missing_candidates(search_results: dict, intent: dict) -> list[dict]:
    """
    For each category in search_results with zero candidates, return a
    user-facing reason explaining why and a suggested fix.

    Args:
        search_results: dict[category, list[products]] from search_all_categories
        intent:         intent dict from Layer 1

    Returns:
        List of {"category", "reason", "suggestion"} entries. Empty if all categories
        have at least one candidate.
    """
    catalogue = load_catalogue()
    missing = []

    for category, cands in search_results.items():
        if cands:
            continue

        products = catalogue.get(category, [])
        if not products:
            reason = "catalogue has no products in this category"
            suggestion = f"add {category}.json to data/ folder, or drop it from required_categories"
        else:
            in_stock = [p for p in products if p.get("in_stock", True)]
            if not in_stock:
                reason = f"all {len(products)} products are out of stock"
                suggestion = "check back later, or relax the in_stock filter"
            else:
                style = intent.get("style_profile", {})
                rgb_pref = style.get("rgb_preference")
                vibe = style.get("vibe")
                if rgb_pref is False and category in VISUAL_CATEGORIES:
                    reason = (
                        f"all {len(in_stock)} in-stock {category}s have RGB lighting "
                        f"but the user's aesthetic is '{vibe}' (no RGB)"
                    )
                    suggestion = (
                        f"either expand the {category} catalogue with non-RGB options, "
                        f"or relax the user's aesthetic preference"
                    )
                else:
                    reason = "products filtered out by style or preference rules"
                    suggestion = "relax style preferences and re-run"

        missing.append({
            "category": category,
            "reason": reason,
            "suggestion": suggestion,
        })
    return missing

"""
Parts comparison feature.

Pure data lookup — no API call needed. Returns a side-by-side comparison
of two products in the same category, with per-spec winner detection.
"""

from .catalogue import load_catalogue


# For each numeric spec key, is higher better?
# True = higher better, False = lower better
_HIGHER_IS_BETTER = {
    # Universal
    "warranty_yr": True, "price_rm": False,
    # CPU
    "cores": True, "threads": True, "base_ghz": True, "boost_ghz": True,
    "cache_mb": True,
    "tdp_watts": False,  # lower = cooler + less power
    # GPU
    "vram_gb": True, "boost_clock_mhz": True, "memory_bandwidth_gbps": True,
    "length_mm": False,  # lower = fits in more cases
    # RAM
    "capacity_gb": True, "speed_mhz": True,
    "cas_latency": False,  # lower = faster
    # Storage
    "read_speed_mb": True, "write_speed_mb": True, "tbw": True,
    # PSU
    "wattage": True, "efficiency_rating_pct": True,
    # Cooler
    "max_tdp_watts": True,
    "height_mm": False, "noise_db": False,
    # Case
    "max_gpu_length_mm": True, "max_cooler_height_mm": True,
    "m2_slots": True, "ram_slots": True, "sata_ports": True,
}


class CompareError(Exception):
    pass


def _find_by_id(catalogue: dict, pid: str) -> dict | None:
    for products in catalogue.values():
        for p in products:
            if p["id"] == pid:
                return p
    return None


def _cheapest_vendor(product: dict) -> dict | None:
    vendors = product.get("vendors", [])
    if not vendors:
        return None
    return min(vendors, key=lambda v: v.get("price_rm", float("inf")))


def _winner_for(key: str, val_a, val_b) -> str | None:
    """Return 'a', 'b', 'tie', or None (not comparable)."""
    if val_a is None and val_b is None:
        return None
    if val_a is None:
        return "b"
    if val_b is None:
        return "a"
    if not isinstance(val_a, (int, float)) or not isinstance(val_b, (int, float)):
        return None  # categorical / list values aren't compared
    if val_a == val_b:
        return "tie"
    higher_better = _HIGHER_IS_BETTER.get(key, True)
    if higher_better:
        return "a" if val_a > val_b else "b"
    return "a" if val_a < val_b else "b"


def compare_products(product_id_a: str, product_id_b: str) -> dict:
    """
    Side-by-side comparison of two products in the same category.

    Returns a dict suitable for rendering a comparison table:
        {
            "category": str,
            "a": {id, name, price_rm, vendor},
            "b": {id, name, price_rm, vendor},
            "specs": [{key, a, b, winner}, ...],
            "price_winner": "a" | "b" | "tie",
            "overall_winner": "a" | "b" | "tie",
            "win_counts": {"a": int, "b": int, "tie": int}
        }

    Raises:
        CompareError: if a product is missing or categories don't match.
    """
    catalogue = load_catalogue()
    a = _find_by_id(catalogue, product_id_a)
    b = _find_by_id(catalogue, product_id_b)

    if not a:
        raise CompareError(f"Product '{product_id_a}' not found")
    if not b:
        raise CompareError(f"Product '{product_id_b}' not found")
    if a["category"] != b["category"]:
        raise CompareError(
            f"Cannot compare across categories: {a['category']} vs {b['category']}"
        )

    cv_a = _cheapest_vendor(a) or {}
    cv_b = _cheapest_vendor(b) or {}
    price_a = cv_a.get("price_rm")
    price_b = cv_b.get("price_rm")

    specs_a = a.get("specs", {})
    specs_b = b.get("specs", {})
    all_keys = sorted(set(specs_a.keys()) | set(specs_b.keys()))

    spec_rows = []
    win_counts = {"a": 0, "b": 0, "tie": 0}
    for k in all_keys:
        va, vb = specs_a.get(k), specs_b.get(k)
        w = _winner_for(k, va, vb)
        if w in win_counts:
            win_counts[w] += 1
        spec_rows.append({"key": k, "a": va, "b": vb, "winner": w})

    price_winner = _winner_for("price_rm", price_a, price_b)
    if price_winner in win_counts:
        win_counts[price_winner] += 1

    if win_counts["a"] > win_counts["b"]:
        overall = "a"
    elif win_counts["b"] > win_counts["a"]:
        overall = "b"
    else:
        overall = "tie"

    return {
        "category": a["category"],
        "a": {
            "id": a["id"], "name": a["name"],
            "price_rm": price_a, "vendor": cv_a.get("name"),
            "link": cv_a.get("link"),
        },
        "b": {
            "id": b["id"], "name": b["name"],
            "price_rm": price_b, "vendor": cv_b.get("name"),
            "link": cv_b.get("link"),
        },
        "specs": spec_rows,
        "price_winner": price_winner,
        "overall_winner": overall,
        "win_counts": win_counts,
    }

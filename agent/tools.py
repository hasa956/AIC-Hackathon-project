"""
Mock external tools — designed with proper input/output schemas so real APIs
can drop in later (EasyParcel, Lalamove, J&T, etc.).

This module demonstrates tool-use architecture without burning API credits.
"""

# Malaysia SST rate (Sales & Service Tax)
SST_RATE = 0.06

# Mock per-vendor shipping baselines (RM and days from KL)
_VENDOR_SHIPPING = {
    "Lazada MY": {"base_rm": 0.0,  "days": 5, "carrier": "Ninja Van"},
    "Shopee MY": {"base_rm": 8.0,  "days": 4, "carrier": "J&T Express"},
    "PC Image":  {"base_rm": 0.0,  "days": 7, "carrier": "Self pickup or courier"},
}

# Rough distance multipliers from KL by city
_LOCATION_MULTIPLIERS = {
    "kuala lumpur": 1.0,
    "petaling jaya": 1.0,
    "shah alam":    1.05,
    "johor bahru":  1.4,
    "penang":       1.4,
    "kota kinabalu": 2.2,
    "kuching":      2.2,
}


def get_shipping_estimate(
    vendor: str,
    location: str = "Kuala Lumpur",
    weight_kg: float = 5.0,
) -> dict:
    """
    Mock logistics estimator. Returns shipping cost and delivery time per vendor.

    Real API drops in here later — EasyParcel, Lalamove, J&T, Ninja Van all
    expose similar (vendor, destination, weight) -> (cost, ETA) schemas.

    Args:
        vendor: vendor name as listed in catalogue (e.g. "Shopee MY")
        location: delivery city (defaults to Kuala Lumpur)
        weight_kg: package weight (PC parcels typically 5-15kg)

    Returns:
        {
            "vendor": str,
            "location": str,
            "shipping_rm": float,
            "delivery_days": int,
            "carrier": str
        }
    """
    profile = _VENDOR_SHIPPING.get(vendor, {"base_rm": 15.0, "days": 7, "carrier": "Standard courier"})
    multiplier = _LOCATION_MULTIPLIERS.get(location.strip().lower(), 1.3)

    # Cap weight contribution so a 10kg PC isn't priced like a fridge
    weight_factor = 1.0 + max(0, (weight_kg - 5.0)) * 0.05

    cost = profile["base_rm"] * multiplier * weight_factor
    # Round to nearest RM
    cost = round(cost, 2)

    days = profile["days"] + (1 if multiplier > 1.3 else 0)

    return {
        "vendor": vendor,
        "location": location,
        "shipping_rm": cost,
        "delivery_days": days,
        "carrier": profile["carrier"],
    }


def calculate_sst(subtotal_rm: float, rate: float = SST_RATE) -> float:
    """
    Malaysia SST calculation. Default 6% rate.

    Args:
        subtotal_rm: subtotal before tax
        rate: SST rate (default 0.06)

    Returns:
        Tax amount in RM, rounded to 2 dp.
    """
    return round(subtotal_rm * rate, 2)


def calculate_total_cost(
    items: list[dict],
    location: str = "Kuala Lumpur",
) -> dict:
    """
    Sum up a complete build's cost including shipping and SST.

    Args:
        items: list of {category, product_id, name, vendor_name, unit_price_rm}
        location: delivery city

    Returns:
        {
            "subtotal_rm": float,
            "shipping_total_rm": float,
            "sst_rm": float,
            "grand_total_rm": float,
            "by_vendor": {vendor: {items_total, shipping, delivery_days}}
        }
    """
    by_vendor: dict[str, dict] = {}

    for item in items:
        vendor = item.get("vendor_name", "Unknown")
        price = float(item.get("unit_price_rm", 0))
        entry = by_vendor.setdefault(vendor, {
            "items_total_rm": 0.0,
            "shipping_rm": 0.0,
            "delivery_days": 0,
            "carrier": "",
        })
        entry["items_total_rm"] += price

    # One shipping estimate per vendor, not per item
    for vendor, entry in by_vendor.items():
        ship = get_shipping_estimate(vendor, location)
        entry["shipping_rm"] = ship["shipping_rm"]
        entry["delivery_days"] = ship["delivery_days"]
        entry["carrier"] = ship["carrier"]

    subtotal = sum(e["items_total_rm"] for e in by_vendor.values())
    shipping_total = sum(e["shipping_rm"] for e in by_vendor.values())
    sst = calculate_sst(subtotal + shipping_total)
    grand_total = subtotal + shipping_total + sst

    return {
        "subtotal_rm": round(subtotal, 2),
        "shipping_total_rm": round(shipping_total, 2),
        "sst_rm": sst,
        "grand_total_rm": round(grand_total, 2),
        "by_vendor": {v: {k: (round(val, 2) if isinstance(val, float) else val)
                          for k, val in entry.items()}
                      for v, entry in by_vendor.items()},
    }
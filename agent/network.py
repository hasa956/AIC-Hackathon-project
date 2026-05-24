"""
Network scoping advisory — Business mode only.

Pure formulas pulled from compatibility_rules.json -> network_topology_advisory.
No LLM call. Framed as advisory only — not a deployable plan.

Generates:
  - Switch sizing recommendation
  - Router recommendation
  - NAS recommendation (only if designers/content creators present)
  - WiFi access point count
  - Cat6 cabling estimate
  - Rough RM budget range
"""

import math


_SWITCH_TIERS = [
    (8,    "TP-Link TL-SG108",    "8-port unmanaged",                   200),
    (16,   "TP-Link TL-SG116",    "16-port unmanaged",                  350),
    (24,   "TP-Link TL-SG1024D",  "24-port unmanaged",                  500),
    (None, "TP-Link TL-SG3428",   "24-port managed (large or mixed)",  1200),
]

_ROUTER_TIERS = [
    (50,   "TP-Link ER605",       "Single WAN business router",         400),
    (200,  "TP-Link ER7206",      "Multi-WAN failover router",          900),
    (None, "Enterprise router",   "Consult IT vendor for sizing",      3500),
]

_NAS_TIERS = [
    (15,   "WD My Cloud EX2 Ultra",   "2-bay NAS",                     1200),
    (50,   "Synology DS923+",         "4-bay NAS with RAID 5",         4500),
    (None, "Synology DS1621+",        "6-bay NAS with RAID 6",         8500),
]

_WIFI_AP_PRICE_RM = 900     # WiFi 6 PoE ceiling-mount
_CABLE_BOX_M = 305
_CABLE_BOX_PRICE_RM = 450
_PATCH_CABLE_PRICE_RM = 15  # 2m patch cables


def _pick_tier(value, tiers):
    for threshold, name, desc, price in tiers:
        if threshold is None or value <= threshold:
            return {"name": name, "description": desc, "price_rm": price}
    return None


def _select_switch(devices_per_floor: int, mixed_roles: bool) -> dict:
    tier = _pick_tier(devices_per_floor, _SWITCH_TIERS)
    if mixed_roles and devices_per_floor <= 24:
        # Bump to managed switch for QoS across mixed roles
        tier = {
            "name": "TP-Link TL-SG3428",
            "description": "24-port managed with QoS (mixed roles need priority bandwidth)",
            "price_rm": 1200,
        }
    return tier


def _select_router(total_users: int, vpn_needed: bool) -> dict:
    tier = _pick_tier(total_users, _ROUTER_TIERS)
    if vpn_needed:
        tier["description"] += " (VPN-capable for remote workers)"
    return tier


def _select_nas(total_users: int, has_video_editing: bool) -> dict:
    tier = _pick_tier(total_users, _NAS_TIERS)
    # Video editing forces minimum 4-bay regardless of user count
    if has_video_editing and tier and tier["name"] == "WD My Cloud EX2 Ultra":
        tier = {
            "name": "Synology DS923+",
            "description": "4-bay NAS with RAID 5 (required for video editing workflows)",
            "price_rm": 4500,
        }
    return tier


def generate_network_advisory(
    company_profile: dict,
    role_breakdown: list[dict],
    floor_area_sqm: float | None = None,
    total_floors: int = 1,
    has_remote_workers: bool = False,
) -> dict:
    """
    Generate the network scoping advisory for a business.

    Args:
        company_profile:    company info dict (used for context only)
        role_breakdown:     [{"role": str, "count": int}, ...]
        floor_area_sqm:     total floor area; defaults to 1 AP per floor if unknown
        total_floors:       number of office floors
        has_remote_workers: triggers VPN-capable router

    Returns:
        Advisory dict with switch, router, NAS, WiFi, cabling, budget range,
        plus a disclaimer string.
    """
    total_wired = sum(r["count"] for r in role_breakdown)
    if total_wired == 0:
        return {"error": "no headcount provided"}

    roles_present = {r["role"] for r in role_breakdown}
    has_designers = bool(roles_present & {"designer", "content_creator"})
    has_mixed_roles = len(roles_present) > 1

    # Switch — one per floor
    devices_per_floor = math.ceil(total_wired / total_floors)
    switch_tier = _select_switch(devices_per_floor, has_mixed_roles)
    switch = {
        **switch_tier,
        "quantity": total_floors,
        "subtotal_rm": switch_tier["price_rm"] * total_floors,
    }

    # Router
    router = _select_router(total_wired, has_remote_workers)

    # NAS only if designers/content creators
    nas = _select_nas(total_wired, has_designers) if has_designers else None

    # WiFi APs — by area if known, else 1 per floor
    if floor_area_sqm:
        aps_per_floor = math.ceil(floor_area_sqm / 280)
    else:
        aps_per_floor = 1
    total_aps = aps_per_floor * total_floors
    wifi = {
        "access_points_qty": total_aps,
        "recommendation": "WiFi 6 PoE ceiling-mount (e.g. TP-Link EAP670)",
        "unit_price_rm": _WIFI_AP_PRICE_RM,
        "subtotal_rm": total_aps * _WIFI_AP_PRICE_RM,
    }

    # Cabling
    metres = math.ceil(total_wired * 15 * 1.2)
    boxes = math.ceil(metres / _CABLE_BOX_M)
    patch_qty = math.ceil(total_wired / 10) * 10
    cabling = {
        "estimated_metres": metres,
        "bulk_boxes_qty": boxes,
        "box_size_m": _CABLE_BOX_M,
        "patch_cables_qty": patch_qty,
        "subtotal_rm": boxes * _CABLE_BOX_PRICE_RM + patch_qty * _PATCH_CABLE_PRICE_RM,
    }

    # Budget range — sum + spread
    subtotal = (
        switch["subtotal_rm"]
        + router["price_rm"]
        + (nas["price_rm"] if nas else 0)
        + wifi["subtotal_rm"]
        + cabling["subtotal_rm"]
    )
    budget_low = int(round(subtotal * 0.85, -2))
    budget_high = int(round(subtotal * 1.30, -2))

    return {
        "switch": switch,
        "router": router,
        "nas": nas,
        "wifi": wifi,
        "cabling": cabling,
        "estimated_total_rm": subtotal,
        "estimated_budget_range_rm": [budget_low, budget_high],
        "disclaimer": (
            "Advisory only — not included in the PC quote. Source via your IT "
            "vendor or telco. Actual costs depend on site survey, cable routing, "
            "and installation labour."
        ),
        "summary": {
            "total_wired_devices": total_wired,
            "total_floors": total_floors,
            "has_designers": has_designers,
            "mixed_roles": has_mixed_roles,
            "remote_workers": has_remote_workers,
        },
    }

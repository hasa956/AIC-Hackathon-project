"""
Business Agent orchestrator.

For each unique role in the headcount breakdown, generate one PC build profile
(tiered spec matrix). Aggregate into a single business quote. Layer on the
network scoping advisory. Persist company profile + summary to sessions.json.

Entry point: generate_business_quote(company_profile, role_breakdown)
"""

import json
import os
from datetime import datetime

from .intent_parser import parse_intent
from .catalogue import search_all_categories
from .reasoner import generate_build
from .network import generate_network_advisory
from .diagnostics import diagnose_missing_candidates


SESSIONS_FILE = "sessions.json"


# Role -> sensible Layer 1 input defaults
# Sourced from compatibility_rules.json role_pc_profiles, mapped to Layer 1 enums.
_ROLE_TEMPLATES = {
    "developer": {
        "use_cases": ["development", "office"],
        "default_budget_rm": 6000,
        "aesthetic_style": "workstation",
        "noise_preference": "balanced",
        "free_text": "Workstation for full-stack development. Heavy compiling, Docker, multiple IDEs.",
    },
    "designer": {
        "use_cases": ["video_editing", "3d_design"],
        "default_budget_rm": 7500,
        "aesthetic_style": "workstation",
        "noise_preference": "balanced",
        "free_text": "Workstation for design and content creation. High VRAM GPU, fast NVMe for project files.",
    },
    "finance": {
        "use_cases": ["office"],
        "default_budget_rm": 2500,
        "aesthetic_style": "minimal",
        "noise_preference": "silent",
        "free_text": "Office desktop for spreadsheets and reporting tools. Quiet, reliable, no GPU work.",
    },
    "executive": {
        "use_cases": ["office"],
        "default_budget_rm": 4500,
        "aesthetic_style": "workstation",
        "noise_preference": "silent",
        "free_text": "Premium quiet desktop for executive office use. Clean aesthetics, near-silent operation.",
    },
    "content_creator": {
        "use_cases": ["video_editing", "streaming", "3d_design"],
        "default_budget_rm": 9000,
        "aesthetic_style": "workstation",
        "noise_preference": "balanced",
        "free_text": "Powerful all-rounder for streaming, video editing, and 3D rendering simultaneously.",
    },
    "admin": {
        "use_cases": ["office"],
        "default_budget_rm": 2000,
        "aesthetic_style": "minimal",
        "noise_preference": "balanced",
        "free_text": "Entry-level office desktop for admin work. Most budget-friendly build.",
    },
}


# ── Session persistence (local sessions.json) ────────────────────────

def _load_sessions_file() -> dict:
    if not os.path.exists(SESSIONS_FILE):
        return {"sessions": []}
    with open(SESSIONS_FILE, "r", encoding="utf-8") as fp:
        try:
            return json.load(fp)
        except json.JSONDecodeError:
            return {"sessions": []}


def _save_sessions_file(data: dict) -> None:
    with open(SESSIONS_FILE, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)


def save_session(session_data: dict) -> str:
    """Append a new session and return its ID."""
    db = _load_sessions_file()
    session_id = "sess_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    record = {
        "id": session_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        **session_data,
    }
    db["sessions"].append(record)
    _save_sessions_file(db)
    return session_id


def load_session(session_id: str) -> dict | None:
    db = _load_sessions_file()
    for s in db["sessions"]:
        if s.get("id") == session_id:
            return s
    return None


def list_sessions(mode: str | None = None) -> list[dict]:
    """Return condensed metadata for saved sessions. mode='personal'|'business'|None for all."""
    db = _load_sessions_file()
    sessions = db["sessions"]
    if mode:
        sessions = [s for s in sessions if s.get("mode", "business") == mode]
    return [
        {
            "id": s["id"],
            "created_at": s.get("created_at"),
            "mode": s.get("mode", "business"),
            "company_name": s.get("company_profile", {}).get("name"),
            "total_pcs": s.get("summary", {}).get("total_pcs"),
            "total_rm": s.get("summary", {}).get("total_grand_total_rm"),
            "use_cases": s.get("summary", {}).get("use_cases", []),
            "grand_total_rm": s.get("summary", {}).get("grand_total_rm"),
            "budget_rm": s.get("summary", {}).get("budget_rm"),
        }
        for s in sessions
    ]


# ── Business orchestrator ────────────────────────────────────────────

def _intent_input_for_role(
    role: str,
    company_profile: dict,
    count: int,
    budget_override: float | None = None,
) -> dict:
    """Build a Layer 1 input dict from a role + company profile."""
    template = _ROLE_TEMPLATES.get(role) or _ROLE_TEMPLATES["admin"]
    return {
        "mode": "business",
        "company_profile": company_profile,
        "role": {"role": role, "count": count},
        "purposes": template["use_cases"],
        "budget_rm_per_unit": budget_override or template["default_budget_rm"],
        "aesthetic_style": template["aesthetic_style"],
        "noise_preference": template["noise_preference"],
        "owned_parts": [],
        "free_text": template["free_text"],
        "location": company_profile.get("location", "Kuala Lumpur"),
    }


def intent_input_from_role_spec(role_spec: dict, company_profile: dict) -> dict:
    """Build a Layer 1 input from a chat-derived role spec (free-form needs)."""
    return {
        "mode": "business",
        "company_profile": company_profile,
        "role": {"role": role_spec.get("role", "staff"),
                 "count": int(role_spec.get("count", 1) or 1)},
        "purposes": [],
        "budget_rm_per_unit": role_spec.get("budget_rm"),
        "owned_parts": [],
        "free_text": role_spec.get("needs", ""),
        "location": company_profile.get("location", "Kuala Lumpur"),
    }


def generate_quote_from_spec(spec: dict, persist: bool = True) -> dict:
    """
    Run the full per-role build pipeline from a chat-derived spec.

    Returns the shape the Streamlit business view expects:
        {company_profile, role_results, network, total_cost, total_pcs, session_id}
    """
    company_profile = dict(spec.get("company_profile", {}))
    company_profile.setdefault("location", "Kuala Lumpur")
    roles  = spec.get("roles", [])
    office = spec.get("office", {}) or {}

    role_results: dict[str, dict] = {}
    total_cost = 0.0
    total_pcs  = 0

    for rs in roles:
        role  = rs.get("role", "staff")
        count = int(rs.get("count", 1) or 1)
        intent_input = intent_input_from_role_spec(rs, company_profile)
        try:
            intent     = parse_intent(intent_input)
            candidates = search_all_categories(intent, top_k=3)
            build      = generate_build(intent, candidates)
            per_unit   = build["costs"]["grand_total_rm"]
            role_total = round(per_unit * count, 2)
            total_cost += role_total
            total_pcs  += count
            role_results[role] = {
                "count":      count,
                "per_unit":   per_unit,
                "role_total": role_total,
                "build":      build,
                "candidates": candidates,
            }
        except Exception as e:
            role_results[role] = {"count": count, "error": f"{type(e).__name__}: {e}"}

    role_breakdown = [
        {"role": rs.get("role", "staff"), "count": int(rs.get("count", 1) or 1)}
        for rs in roles
    ]
    floor_area = office.get("floor_area_sqm")
    network = generate_network_advisory(
        company_profile    = company_profile,
        role_breakdown     = role_breakdown,
        floor_area_sqm     = float(floor_area) if floor_area else None,
        total_floors       = int(office.get("total_floors", 1) or 1),
        has_remote_workers = bool(office.get("has_remote_workers", False)),
    )

    session_id = ""
    if persist:
        session_id = save_session({
            "company_profile": company_profile,
            "role_breakdown":  role_breakdown,
            "summary": {
                "total_pcs":                  total_pcs,
                "total_grand_total_rm":       round(total_cost, 2),
                "roles_covered":              [r["role"] for r in role_breakdown],
                "network_estimated_total_rm": network.get("estimated_total_rm", 0),
            },
        })

    return {
        "company_profile": company_profile,
        "role_results":    role_results,
        "network":         network,
        "total_cost":      round(total_cost, 2),
        "total_pcs":       total_pcs,
        "session_id":      session_id,
    }


def generate_business_quote(
    company_profile: dict,
    role_breakdown: list[dict],
    budget_overrides: dict | None = None,
    floor_area_sqm: float | None = None,
    total_floors: int = 1,
    has_remote_workers: bool = False,
    persist: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Full business quote: per-role builds + network advisory + persistence.

    Args:
        company_profile:    {"name", "industry", "size", "location"}
        role_breakdown:     [{"role": str, "count": int}, ...]
        budget_overrides:   optional {role: budget_rm}
        floor_area_sqm:     drives WiFi AP sizing
        total_floors:       number of office floors
        has_remote_workers: triggers VPN-capable router
        persist:            save to sessions.json if True
        verbose:            print progress

    Returns:
        {
            "id": "sess_...",
            "company_profile": {...},
            "role_breakdown": [...],
            "role_builds": {role: {count, build, ...}},
            "network_advisory": {...},
            "summary": {...},
        }
    """
    # Collapse duplicate role rows
    role_counts: dict[str, int] = {}
    for entry in role_breakdown:
        r = entry["role"]
        role_counts[r] = role_counts.get(r, 0) + entry["count"]

    role_builds: dict[str, dict] = {}
    total_cost = 0.0
    total_pcs = 0

    for role, count in role_counts.items():
        if verbose:
            print(f"\n→ Generating build for role '{role}' (x{count})...")
        budget = (budget_overrides or {}).get(role)
        intent_input = _intent_input_for_role(role, company_profile, count, budget)

        try:
            intent = parse_intent(intent_input)
            candidates = search_all_categories(intent, top_k=3)
            missing = diagnose_missing_candidates(candidates, intent)
            build = generate_build(intent, candidates)

            per_unit = build["costs"]["grand_total_rm"]
            role_total = per_unit * count
            total_cost += role_total
            total_pcs += count

            role_builds[role] = {
                "count": count,
                "per_unit_grand_total_rm": per_unit,
                "role_total_rm": round(role_total, 2),
                "build": build,
                "missing_categories": missing,
            }

            if verbose:
                print(f"  ✓ Done. Per-unit RM{per_unit:.2f}, role total RM{role_total:.2f}")

        except Exception as e:
            if verbose:
                print(f"  ✗ Failed: {type(e).__name__}: {e}")
            role_builds[role] = {
                "count": count,
                "error": f"{type(e).__name__}: {e}",
            }

    # Network advisory (pure code, no LLM)
    if verbose:
        print("\n→ Generating network scoping advisory...")
    network_advisory = generate_network_advisory(
        company_profile=company_profile,
        role_breakdown=[{"role": r, "count": c} for r, c in role_counts.items()],
        floor_area_sqm=floor_area_sqm,
        total_floors=total_floors,
        has_remote_workers=has_remote_workers,
    )

    summary = {
        "total_pcs": total_pcs,
        "total_grand_total_rm": round(total_cost, 2),
        "roles_covered": list(role_counts.keys()),
        "network_estimated_total_rm": network_advisory.get("estimated_total_rm", 0),
    }

    result = {
        "company_profile": company_profile,
        "role_breakdown": [{"role": r, "count": c} for r, c in role_counts.items()],
        "role_builds": role_builds,
        "network_advisory": network_advisory,
        "summary": summary,
    }

    if persist:
        # Persist profile + summary only — full builds are too large and
        # contain LLM output that's not worth re-storing.
        result["id"] = save_session({
            "company_profile": company_profile,
            "role_breakdown": result["role_breakdown"],
            "summary": summary,
        })

    return result

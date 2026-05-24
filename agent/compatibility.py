"""
Compatibility validation — pure-code implementation of the 12 rules from
compatibility_rules.json. Pure Python is more reliable than asking the LLM
to enforce these.

Entry point: validate_build(build) -> list[str]
Returns a list of error messages. Empty list = valid build.
"""

from typing import Optional


def _get(d: Optional[dict], *path, default=None):
    """Safely traverse a nested dict by key path."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


# ── Individual rule checks. Each returns either an error string or None. ──

def _r_cpu_motherboard_socket(b):
    cpu, mb = b.get("cpu"), b.get("motherboard")
    if not (cpu and mb):
        return None
    c_sock = _get(cpu, "specs", "socket")
    m_sock = _get(mb, "specs", "socket")
    if c_sock and m_sock and c_sock != m_sock:
        return f"CPU socket {c_sock} does not match motherboard socket {m_sock}"
    return None


def _r_ram_type(b):
    cpu, mb, ram = b.get("cpu"), b.get("motherboard"), b.get("ram")
    if not (cpu and mb and ram):
        return None
    ram_type = _get(ram, "specs", "type")
    mb_type = _get(mb, "specs", "ram_type")
    cpu_support = _get(cpu, "specs", "ram_support", default=[])
    if ram_type and mb_type and ram_type != mb_type:
        return f"RAM type {ram_type} does not match motherboard RAM type {mb_type}"
    if ram_type and cpu_support and ram_type not in cpu_support:
        return f"RAM type {ram_type} not supported by CPU (supports: {cpu_support})"
    return None


def _r_mb_case_form_factor(b):
    mb, case = b.get("motherboard"), b.get("case")
    if not (mb and case):
        return None
    mb_form = _get(mb, "specs", "form_factor")
    case_support = _get(case, "specs", "form_factor_support", default=[])
    if mb_form and case_support and mb_form not in case_support:
        return f"Motherboard form factor {mb_form} not supported by case (supports: {case_support})"
    return None


def _r_gpu_case_length(b):
    gpu, case = b.get("gpu"), b.get("case")
    if not (gpu and case):
        return None
    gpu_len = _get(gpu, "specs", "length_mm")
    case_max = _get(case, "specs", "max_gpu_length_mm")
    if gpu_len and case_max and gpu_len > case_max:
        return f"GPU length {gpu_len}mm exceeds case clearance {case_max}mm"
    return None


def _r_cooler_case_height(b):
    cooler, case = b.get("cooler"), b.get("case")
    if not (cooler and case):
        return None
    if _get(cooler, "specs", "type") != "Air":
        return None
    cooler_h = _get(cooler, "specs", "height_mm")
    case_max = _get(case, "specs", "max_cooler_height_mm")
    if cooler_h and case_max and cooler_h > case_max:
        return f"Cooler height {cooler_h}mm exceeds case clearance {case_max}mm"
    return None


def _r_cooler_socket(b):
    cpu, cooler = b.get("cpu"), b.get("cooler")
    if not (cpu and cooler):
        return None
    cpu_sock = _get(cpu, "specs", "socket")
    supported = _get(cooler, "specs", "socket_support", default=[])
    if cpu_sock and supported and cpu_sock not in supported:
        return f"Cooler does not support CPU socket {cpu_sock} (supports: {supported})"
    return None


def _r_cooler_tdp(b):
    cpu, cooler = b.get("cpu"), b.get("cooler")
    if not (cpu and cooler):
        return None
    cpu_tdp = _get(cpu, "specs", "tdp_watts")
    cooler_max = _get(cooler, "specs", "max_tdp_watts")
    if cpu_tdp and cooler_max and cooler_max < cpu_tdp:
        return f"Cooler max TDP {cooler_max}W below CPU TDP {cpu_tdp}W"
    return None


def _r_psu_wattage(b):
    cpu, gpu, psu = b.get("cpu"), b.get("gpu"), b.get("psu")
    if not (cpu and psu):
        return None
    cpu_tdp = _get(cpu, "specs", "tdp_watts", default=0)
    gpu_tdp = _get(gpu, "specs", "tdp_watts", default=0) if gpu else 0
    psu_w = _get(psu, "specs", "wattage", default=0)
    required = int((cpu_tdp + gpu_tdp + 100) * 1.2)
    if psu_w and psu_w < required:
        return f"PSU {psu_w}W insufficient — system needs at least {required}W (20% headroom over CPU+GPU+100W baseline)"
    return None


def _r_ram_slots(b):
    mb, ram = b.get("motherboard"), b.get("ram")
    if not (mb and ram):
        return None
    sticks = _get(ram, "specs", "sticks")
    slots = _get(mb, "specs", "ram_slots")
    if sticks and slots and sticks > slots:
        return f"RAM kit has {sticks} sticks but motherboard only has {slots} slots"
    return None


def _r_aio_radiator(b):
    cooler, case = b.get("cooler"), b.get("case")
    if not (cooler and case):
        return None
    if _get(cooler, "specs", "type") != "AIO":
        return None
    rad = _get(cooler, "specs", "radiator_mm")
    supported = _get(case, "specs", "radiator_support_mm", default=[])
    if rad and supported and rad not in supported:
        return f"Case does not support {rad}mm AIO radiator (supports: {supported})"
    return None


_ALL_RULES = [
    _r_cpu_motherboard_socket,
    _r_ram_type,
    _r_mb_case_form_factor,
    _r_gpu_case_length,
    _r_cooler_case_height,
    _r_cooler_socket,
    _r_cooler_tdp,
    _r_psu_wattage,
    _r_ram_slots,
    _r_aio_radiator,
]


# ── Public API ───────────────────────────────────────────────────────

def validate_build(build: dict) -> list[str]:
    """
    Run all compatibility rules against a build.

    Args:
        build: dict with keys like cpu, motherboard, ram, gpu, etc.
               Each value is the full product dict (with specs).

    Returns:
        List of error strings. Empty list means the build is valid.
    """
    errors = []
    for rule in _ALL_RULES:
        err = rule(build)
        if err:
            errors.append(err)
    return errors
"""
Streamlit dashboard — AI-powered PC Recommendation Agent
AI Marathon 2026 — Problem Statement 1: Autonomous Sales Engineer
"""

import os
import streamlit as st

from agent.catalogue import (
    load_catalogue, build_or_load_embeddings, CATEGORIES, search_all_categories,
)
from agent.intent_parser import parse_intent, IntentValidationError
from agent.reasoner import generate_build, BuildGenerationError
from agent.explainer import explain_component
from agent.compare import compare_products, CompareError
from agent.business import (
    list_sessions, save_session, _ROLE_TEMPLATES, _intent_input_for_role,
)
from agent.network import generate_network_advisory

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PC Agent — AI Marathon 2026",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
PURPOSE_OPTIONS = [
    "gaming", "office", "video_editing", "3d_design",
    "streaming", "development", "light_gaming",
]
VIBE_OPTIONS   = ["stealth", "minimal", "workstation", "clean_white", "rgb_gamer"]
NOISE_OPTIONS  = ["silent", "balanced", "performance"]
ROLE_OPTIONS   = ["developer", "designer", "finance", "executive", "content_creator", "admin"]
INDUSTRY_OPTIONS = [
    "software", "finance", "healthcare", "education",
    "manufacturing", "retail", "media", "consulting",
]
SIZE_OPTIONS = ["1-10", "11-50", "51-200", "201-500", "500+"]

CATEGORY_DISPLAY = {c: c.replace("_", " ").title() for c in CATEGORIES}


# ── Cached resources ──────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading catalogue & building embeddings…")
def init_resources():
    cat = load_catalogue()
    build_or_load_embeddings(cat)
    return cat


# ── Shared helpers ────────────────────────────────────────────────────────────
def _stream_to_state(key: str, generator) -> str:
    """Stream chunks into a placeholder, cache result in session_state. Returns full text."""
    if key in st.session_state:
        return st.session_state[key]
    chunks = []
    ph = st.empty()
    for chunk in generator:
        chunks.append(chunk)
        ph.write("".join(chunks))
    text = "".join(chunks)
    st.session_state[key] = text
    return text


def render_vendor_table(product_id: str, category: str) -> None:
    """Show all vendor rows for a product, sorted by price."""
    catalogue = init_resources()
    product = next(
        (p for p in catalogue.get(category, []) if p["id"] == product_id), None
    )
    if not product:
        st.caption("Vendor data unavailable.")
        return

    vendors = sorted(product.get("vendors", []), key=lambda v: v.get("price_rm", 9_999_999))
    for v in vendors:
        warranty = f" · {v['warranty_yr']}yr warranty" if v.get("warranty_yr") else ""
        link = v.get("link", "")
        label = f"[{v['name']}]({link})" if link else f"**{v['name']}**"
        st.markdown(f"- {label}: RM {v['price_rm']:,}{warranty}")


def render_bom_item(item: dict, build: dict, candidates: dict, prefix: str = "") -> None:
    """One BOM row: category / name / vendor / price + explain + vendor expanders."""
    cat  = item["category"]
    name = item["name"]
    pid  = item.get("product_id", name)

    alts = [c for c in candidates.get(cat, []) if c["id"] != pid]

    c1, c2, c3, c4 = st.columns([2, 4, 2, 2])
    c1.markdown(f"**{CATEGORY_DISPLAY.get(cat, cat)}**")
    c2.write(name)
    c3.write(item.get("vendor_name", "—"))
    c4.write(f"RM {item.get('unit_price_rm', 0):,.0f}")

    ex1, ex2 = st.columns(2)
    explain_key = f"{prefix}explain_{pid}"

    with ex1:
        with st.expander("Explain this component"):
            if explain_key in st.session_state:
                st.write(st.session_state[explain_key])
            else:
                if st.button("Generate explanation", key=f"{prefix}btn_exp_{pid}"):
                    with st.spinner("Asking Morpheus/Llama…"):
                        _stream_to_state(
                            explain_key,
                            explain_component(item, build, alts, stream=True),
                        )

    with ex2:
        with st.expander("Compare vendors"):
            render_vendor_table(pid, cat)

    st.markdown("---")


def render_build_costs(costs: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Subtotal",    f"RM {costs.get('subtotal_rm',       0):,.2f}")
    c2.metric("Shipping",    f"RM {costs.get('shipping_total_rm', 0):,.2f}")
    c3.metric("SST (6%)",    f"RM {costs.get('sst_rm',            0):,.2f}")
    c4.metric("Grand Total", f"RM {costs.get('grand_total_rm',    0):,.2f}")


def render_full_build(build: dict, candidates: dict, prefix: str = "") -> None:
    """Compatibility badge + cost metrics + reasoning + full BOM."""
    issues = build.get("compatibility_issues", [])
    if not issues:
        st.success("✓ All compatibility checks passed")
    else:
        for issue in issues:
            st.error(f"⚠️ {issue}")

    render_build_costs(build.get("costs", {}))

    rationale = build.get("build_rationale", "")
    warnings  = build.get("warnings", [])
    if rationale or warnings:
        with st.expander("Agent's Reasoning"):
            if rationale:
                st.write(rationale)
            for w in warnings:
                st.warning(w)

    st.subheader("Bill of Materials")
    h1, h2, h3, h4 = st.columns([2, 4, 2, 2])
    h1.markdown("**Category**")
    h2.markdown("**Component**")
    h3.markdown("**Vendor**")
    h4.markdown("**Price**")
    st.markdown("---")

    for item in build.get("items", []):
        render_bom_item(item, build, candidates, prefix=prefix)


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("## 🖥️ PC Agent")
        st.caption("AI Marathon 2026 — Problem Statement 1")

        # Live agent status
        api_ok = bool(os.getenv("MORPHEUS_API_KEY"))
        dot    = "🟢" if api_ok else "🔴"
        label  = "Online — Morpheus / Llama 3.3" if api_ok else "No API key configured"
        st.markdown(f"{dot} {label}")

        st.divider()

        mode = st.radio("Mode", ["Personal Agent", "Business Agent"])

        st.divider()

        # ── Compare Parts ────────────────────────────────────────────────────
        st.subheader("⚖️ Compare Parts")
        catalogue = init_resources()

        cmp_cat = st.selectbox("Category", CATEGORIES,
                               format_func=lambda c: CATEGORY_DISPLAY[c],
                               key="cmp_cat")
        products_in_cat = catalogue.get(cmp_cat, [])

        if len(products_in_cat) >= 2:
            opts  = {p["name"]: p["id"] for p in products_in_cat}
            names = list(opts.keys())

            name_a = st.selectbox("Part A", names, key="cmp_a")
            opts_b = [n for n in names if n != name_a]
            name_b = st.selectbox("Part B", opts_b, key="cmp_b")

            if st.button("Compare ↔", use_container_width=True):
                try:
                    st.session_state["compare_result"] = compare_products(
                        opts[name_a], opts[name_b]
                    )
                    st.rerun()
                except CompareError as e:
                    st.error(str(e))
        else:
            st.caption("Need ≥ 2 products in this category.")

        # ── Session history (business mode) ──────────────────────────────────
        if mode == "Business Agent":
            st.divider()
            st.subheader("Session History")
            sessions = list_sessions()
            if not sessions:
                st.caption("No saved sessions yet.")
            else:
                for s in reversed(sessions[-5:]):
                    ts      = (s.get("created_at") or "")[:16].replace("T", " ")
                    company = s.get("company_name") or "Unknown"
                    pcs     = s.get("total_pcs") or 0
                    total   = s.get("total_rm")  or 0.0
                    with st.expander(f"**{company}**"):
                        st.markdown(f"**{pcs} PCs** | RM {total:,.0f}")
                        st.caption(f"{ts}  ·  `{s['id']}`")

    return mode


# ── Compare panel (main area) ─────────────────────────────────────────────────
def render_compare_panel() -> None:
    result = st.session_state.get("compare_result")
    if not result:
        return

    a  = result["a"]
    b  = result["b"]
    wc = result["win_counts"]
    ow = result["overall_winner"]
    winner_name = a["name"] if ow == "a" else (b["name"] if ow == "b" else "Tie")

    with st.expander(
        f"⚖️ Comparison: **{a['name']}** vs **{b['name']}**",
        expanded=True
    ):
        if ow != "tie":
            st.success(
                f"🏆 Overall winner: **{winner_name}**  "
                f"({wc['a']}–{wc['b']} spec wins, {wc['tie']} ties)"
            )
        else:
            st.info(f"🤝 Tie  ({wc['a']}–{wc['b']} spec wins, {wc['tie']} ties)")

        col_spec, col_a, col_b = st.columns([3, 4, 4])
        col_spec.markdown("**Spec**")
        col_a.markdown(
            f"**{a['name']}**  \n"
            f"RM {(a['price_rm'] or 0):,} @ {a['vendor'] or '—'}"
        )
        col_b.markdown(
            f"**{b['name']}**  \n"
            f"RM {(b['price_rm'] or 0):,} @ {b['vendor'] or '—'}"
        )

        for row in result["specs"]:
            sc, sa, sb = st.columns([3, 4, 4])
            sc.write(row["key"].replace("_", " ").title())
            va = str(row["a"]) if row["a"] is not None else "—"
            vb = str(row["b"]) if row["b"] is not None else "—"
            w  = row["winner"]
            sa.write(f"{'✅ ' if w == 'a' else ''}{va}")
            sb.write(f"{'✅ ' if w == 'b' else ''}{vb}")

        if st.button("✕ Close comparison", key="close_cmp"):
            del st.session_state["compare_result"]
            st.rerun()

    st.divider()


# ── Personal Agent mode ───────────────────────────────────────────────────────
def render_personal_mode() -> None:
    st.title("Personal PC Recommendation")
    st.caption(
        "Answer 4 questions below. The 3-layer AI pipeline picks the optimal, "
        "compatible build within your budget."
    )

    with st.form("personal_form"):
        st.markdown("#### Step 1 — Purpose")
        purposes = st.multiselect(
            "What will you use this PC for?  *(select all that apply)*",
            PURPOSE_OPTIONS,
            default=["gaming"],
        )

        st.markdown("#### Step 2 — Aesthetic vibe")
        vibe = st.select_slider("Style", options=VIBE_OPTIONS, value="minimal")

        st.markdown("#### Step 3 — Budget")
        budget = st.slider("Total budget (RM)", 1500, 20_000, 5000, 500)
        st.caption(f"Selected: **RM {budget:,}**")

        st.markdown("#### Step 4 — Preferences")
        col_n, col_o = st.columns(2)
        with col_n:
            noise = st.select_slider(
                "Noise tolerance", options=NOISE_OPTIONS, value="balanced"
            )
        with col_o:
            owned = st.multiselect(
                "Parts you already own  *(skip from build)*",
                CATEGORIES,
                format_func=lambda c: CATEGORY_DISPLAY[c],
                default=[],
            )

        free_text = st.text_area(
            "Anything else?  *(optional)*",
            placeholder=(
                "e.g. 'I want to run local LLMs', 'must be near-silent', "
                "'gaming at 1440p ultra settings'…"
            ),
        )

        submit = st.form_submit_button(
            "Build My PC 🚀", use_container_width=True, type="primary"
        )

    if submit:
        if not purposes:
            st.error("Please select at least one purpose.")
            return

        user_input = {
            "mode":             "personal",
            "purposes":         purposes,
            "budget_rm":        budget,
            "aesthetic_style":  vibe,
            "noise_preference": noise,
            "owned_parts":      owned,
            "free_text":        free_text,
        }

        status = st.status("Running AI pipeline…", expanded=True)
        with status:
            # Layer 1
            st.write("**Layer 1** — Parsing intent with Llama 3.3…")
            try:
                intent = parse_intent(user_input)
            except IntentValidationError as e:
                status.update(label="Intent parsing failed", state="error")
                st.error(str(e))
                return

            use_cases_str = ", ".join(intent.get("use_cases", []))
            tier = intent.get("budget_tier", "")
            st.write(f"✓ Use cases: `{use_cases_str}` · tier: `{tier}`")

            # Layer 2
            st.write("**Layer 2** — Semantic catalogue search (local embeddings)…")
            candidates = search_all_categories(intent, top_k=3)
            n_cands = sum(len(v) for v in candidates.values())
            st.write(f"✓ {n_cands} candidates across {len(candidates)} categories")

            # Layer 3
            st.write("**Layer 3** — Generating compatible build with Llama 3.3…")
            try:
                build = generate_build(intent, candidates)
            except BuildGenerationError as e:
                status.update(label="Build generation failed", state="error")
                st.error(str(e))
                return

            attempts   = build.get("attempts", 1)
            grand_total = build["costs"]["grand_total_rm"]
            status.update(
                label=(
                    f"Build ready — RM {grand_total:,.2f}  "
                    f"({attempts} compatibility attempt{'s' if attempts > 1 else ''})"
                ),
                state="complete",
            )

        st.session_state["personal_build"]      = build
        st.session_state["personal_candidates"] = candidates
        st.rerun()

    # Render stored build
    if "personal_build" in st.session_state:
        st.divider()
        render_full_build(
            st.session_state["personal_build"],
            st.session_state.get("personal_candidates", {}),
            prefix="p_",
        )


# ── Business Agent mode ───────────────────────────────────────────────────────
def render_business_mode() -> None:
    st.title("Business Fleet Recommendation")
    st.caption(
        "Per-role PC fleet spec with per-unit pricing, fleet totals, "
        "and a network scoping advisory."
    )

    with st.form("business_form"):
        st.markdown("#### Company Profile")
        cp1, cp2, cp3, cp4 = st.columns(4)
        company_name = cp1.text_input("Company Name", value="Acme Sdn Bhd")
        industry     = cp2.selectbox("Industry", INDUSTRY_OPTIONS)
        size         = cp3.selectbox("Size", SIZE_OPTIONS, index=1)
        location     = cp4.text_input("Location", value="Kuala Lumpur")

        nc1, nc2, nc3 = st.columns(3)
        floor_area  = nc1.number_input("Floor area (sqm)", 0, 100_000, 200, 50)
        floors      = nc2.number_input("Total floors", 1, 100, 1)
        has_remote  = nc3.checkbox("Has remote workers")

        st.markdown("#### Role Breakdown")
        st.caption("Set count to **0** to exclude a role.")

        role_col_headers = st.columns([2, 1, 2, 5])
        role_col_headers[0].markdown("**Role**")
        role_col_headers[1].markdown("**Count**")
        role_col_headers[2].markdown("**Budget/unit (RM)**")
        role_col_headers[3].markdown("**Profile**")

        role_inputs: dict[str, dict] = {}
        for role in ROLE_OPTIONS:
            template       = _ROLE_TEMPLATES.get(role, {})
            default_budget = template.get("default_budget_rm", 3000)
            desc           = template.get("free_text", "")[:90]

            rc1, rc2, rc3, rc4 = st.columns([2, 1, 2, 5])
            rc1.markdown(f"**{role.title()}**")
            count = rc2.number_input(
                "n", 0, 500, 0,
                key=f"biz_c_{role}", label_visibility="collapsed"
            )
            budget_val = rc3.number_input(
                f"def {default_budget}", 1500, 100_000, default_budget,
                key=f"biz_b_{role}", label_visibility="collapsed"
            )
            rc4.caption(desc)

            if count > 0:
                role_inputs[role] = {"count": int(count), "budget": int(budget_val)}

        submit = st.form_submit_button(
            "Generate Fleet Quote 🏢", use_container_width=True, type="primary"
        )

    if submit:
        if not role_inputs:
            st.error("Set at least one role's count > 0.")
            return

        company_profile = {
            "name":     company_name,
            "industry": industry,
            "size":     size,
            "location": location,
        }

        role_results: dict[str, dict] = {}
        total_cost = 0.0
        total_pcs  = 0
        n_roles    = len(role_inputs)

        bar = st.progress(0, text="Starting fleet generation…")

        for idx, (role, rd) in enumerate(role_inputs.items()):
            count  = rd["count"]
            budget = rd["budget"]
            bar.progress(idx / n_roles, text=f"Building: **{role}** ×{count}…")

            intent_input = _intent_input_for_role(role, company_profile, count, budget)

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

        bar.progress(0.95, text="Generating network advisory…")

        role_breakdown = [{"role": r, "count": d["count"]} for r, d in role_inputs.items()]
        network = generate_network_advisory(
            company_profile  = company_profile,
            role_breakdown   = role_breakdown,
            floor_area_sqm   = float(floor_area) if floor_area > 0 else None,
            total_floors     = int(floors),
            has_remote_workers = bool(has_remote),
        )

        session_id = save_session({
            "company_profile": company_profile,
            "role_breakdown":  role_breakdown,
            "summary": {
                "total_pcs":              total_pcs,
                "total_grand_total_rm":   round(total_cost, 2),
                "roles_covered":          list(role_inputs.keys()),
                "network_estimated_total_rm": network.get("estimated_total_rm", 0),
            },
        })

        bar.empty()
        st.session_state["business_result"] = {
            "company_profile": company_profile,
            "role_results":    role_results,
            "network":         network,
            "total_cost":      total_cost,
            "total_pcs":       total_pcs,
            "session_id":      session_id,
        }
        st.rerun()

    if "business_result" in st.session_state:
        render_business_result(st.session_state["business_result"])


def render_business_result(result: dict) -> None:
    company      = result["company_profile"]
    role_results = result["role_results"]
    network      = result["network"]

    st.divider()
    st.markdown(f"### Fleet Quote — {company['name']}")
    st.caption(f"Session `{result.get('session_id', '')}`  ·  saved to sessions.json")

    # Fleet summary metrics
    net_total = network.get("estimated_total_rm", 0)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total PCs",              result["total_pcs"])
    m2.metric("PC Fleet Total",         f"RM {result['total_cost']:,.0f}")
    m3.metric("Network Advisory (est)", f"RM {net_total:,.0f}")
    m4.metric("Combined Estimate",      f"RM {result['total_cost'] + net_total:,.0f}")

    # ── Per-role builds ───────────────────────────────────────────────────────
    st.subheader("Per-Role Builds")

    for role, data in role_results.items():
        count = data["count"]

        if "error" in data:
            with st.expander(f"❌ {role.title()} ×{count} — Generation failed"):
                st.error(data["error"])
            continue

        per_unit   = data["per_unit"]
        role_total = data["role_total"]
        build      = data["build"]
        candidates = data["candidates"]
        costs      = build.get("costs", {})

        with st.expander(
            f"**{role.title()}** ×{count}  |  "
            f"RM {per_unit:,.2f}/unit  ·  RM {role_total:,.2f} total"
        ):
            issues = build.get("compatibility_issues", [])
            if not issues:
                st.success("✓ All compatibility checks passed")
            else:
                for issue in issues:
                    st.error(f"⚠️ {issue}")

            render_build_costs(costs)
            st.markdown(f"**Fleet line: ×{count} units = RM {role_total:,.2f}**")

            rationale = build.get("build_rationale", "")
            if rationale:
                with st.expander("Agent's Reasoning"):
                    st.write(rationale)

            st.markdown("**Bill of Materials**")
            rh1, rh2, rh3, rh4 = st.columns([2, 4, 2, 2])
            rh1.markdown("**Category**")
            rh2.markdown("**Component**")
            rh3.markdown("**Vendor**")
            rh4.markdown("**Price/unit**")
            st.markdown("---")

            for item in build.get("items", []):
                render_bom_item(item, build, candidates, prefix=f"{role}_")

    # ── Network advisory ──────────────────────────────────────────────────────
    st.subheader("Network Advisory")
    st.warning(network.get("disclaimer", "Advisory only — not included in PC quote."))

    budget_range = network.get("estimated_budget_range_rm", [0, 0])
    st.info(
        f"Estimated network infrastructure budget: "
        f"**RM {budget_range[0]:,} – RM {budget_range[1]:,}**"
    )

    na1, na2 = st.columns(2)

    with na1:
        sw = network.get("switch", {})
        if sw:
            st.markdown("**🔌 Switch**")
            st.markdown(f"{sw['name']} · *{sw['description']}*")
            qty = sw.get("quantity", 1)
            st.markdown(
                f"×{qty} unit{'s' if qty > 1 else ''} "
                f"→ RM {sw.get('subtotal_rm', sw['price_rm']):,}"
            )

        rt = network.get("router", {})
        if rt:
            st.markdown("**🌐 Router**")
            st.markdown(f"{rt['name']} · *{rt['description']}*")
            st.markdown(f"RM {rt['price_rm']:,}")

        nas = network.get("nas")
        if nas:
            st.markdown("**💾 NAS** *(designers / content creators detected)*")
            st.markdown(f"{nas['name']} · *{nas['description']}*")
            st.markdown(f"RM {nas['price_rm']:,}")

    with na2:
        wifi = network.get("wifi", {})
        if wifi:
            st.markdown("**📶 WiFi Access Points**")
            st.markdown(wifi.get("recommendation", ""))
            st.markdown(
                f"×{wifi['access_points_qty']} APs × RM {wifi['unit_price_rm']:,} "
                f"= RM {wifi['subtotal_rm']:,}"
            )

        cabling = network.get("cabling", {})
        if cabling:
            st.markdown("**🔧 Cat6 Cabling**")
            st.markdown(
                f"~{cabling['estimated_metres']} m · "
                f"{cabling['bulk_boxes_qty']} box(es) + "
                f"{cabling['patch_cables_qty']} patch cables"
            )
            st.markdown(f"RM {cabling['subtotal_rm']:,}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    init_resources()             # warm up catalogue + embeddings
    mode = render_sidebar()
    render_compare_panel()       # compare result shown above content if active

    if mode == "Personal Agent":
        render_personal_mode()
    else:
        render_business_mode()


if __name__ == "__main__":
    main()

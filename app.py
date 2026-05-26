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
    list_sessions, load_session, generate_quote_from_spec, save_session,
)
from agent.business_chat import chat_turn, extract_spec, clean_for_display
from agent.personal_chat import (
    personal_chat_turn, extract_refinement, clean_refinement_display,
    details_chat_turn, extract_details, clean_details_display,
)
from agent.reports import generate_financial_excel, generate_rfp_pdf

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PC Agent — AI Marathon 2026",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
PURPOSE_OPTIONS = [
    "Work & Office", "Gaming & Entertainment", "Content Creation",
    "Development & Programming", "General Purpose",
]
VIBE_OPTIONS   = ["stealth", "minimal", "workstation", "clean_white", "rgb_gamer"]

INDUSTRY_OPTIONS = [
    "Technology", "Finance & Banking", "Healthcare", "Education",
    "Retail & E-commerce", "Manufacturing", "Media & Creative",
    "Professional Services", "Government", "Other",
]
SIZE_OPTIONS = ["1–10", "11–50", "51–200", "201–500", "501–1000", "1000+"]
MY_CITIES = [
    "Kuala Lumpur", "Petaling Jaya", "Shah Alam", "Subang Jaya", "Klang",
    "Putrajaya", "Cyberjaya", "Ampang", "Cheras", "Kajang",
    "Johor Bahru", "Skudai", "Iskandar Puteri",
    "Georgetown (Penang)", "Butterworth", "Bayan Lepas",
    "Ipoh", "Kota Kinabalu", "Kuching", "Melaka", "Seremban",
    "Alor Setar", "Kota Bharu", "Kuala Terengganu", "Kuantan",
    "Miri", "Sibu", "Sandakan", "Tawau",
]

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

    intent_data = build.get("intent", {})
    budget_rm = intent_data.get("budget_rm")
    grand_total = build.get("costs", {}).get("grand_total_rm", 0)
    if budget_rm:
        if grand_total > budget_rm:
            overage = grand_total - budget_rm
            st.error(
                f"⚠️ Over budget by RM{overage:,.2f} — "
                f"total RM{grand_total:,.2f} vs budget RM{budget_rm:,.2f} (incl. SST & shipping)"
            )
        else:
            remaining = budget_rm - grand_total
            st.info(
                f"Within budget — RM{remaining:,.2f} remaining "
                f"(total RM{grand_total:,.2f} of RM{budget_rm:,.2f})"
            )

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


# ── Sidebar header ────────────────────────────────────────────────────────────
def render_sidebar_header() -> None:
    with st.sidebar:
        st.markdown("## 🖥️ PC Agent")
        st.caption("AI Marathon 2026 — Problem Statement 1")

        # Live agent status
        api_ok = bool(os.getenv("MORPHEUS_API_KEY"))
        dot    = "🟢" if api_ok else "🔴"
        label  = "Online — Morpheus / Llama 3.3" if api_ok else "No API key configured"
        st.markdown(f"{dot} {label}")

        st.divider()


# ── Compare Parts page ────────────────────────────────────────────────────────
def render_compare_page() -> None:
    st.title("⚖️ Compare Parts")
    st.caption(
        "Side-by-side spec comparison of two products in the same category. "
        "Pure spec data — no AI call."
    )

    catalogue = init_resources()

    c1, c2, c3 = st.columns(3)
    cmp_cat = c1.selectbox("Category", CATEGORIES,
                           format_func=lambda c: CATEGORY_DISPLAY[c],
                           key="cmp_cat")
    products_in_cat = catalogue.get(cmp_cat, [])

    if len(products_in_cat) >= 2:
        opts  = {p["name"]: p["id"] for p in products_in_cat}
        names = list(opts.keys())

        name_a = c2.selectbox("Part A", names, key="cmp_a")
        opts_b = [n for n in names if n != name_a]
        name_b = c3.selectbox("Part B", opts_b, key="cmp_b")

        if st.button("Compare ↔", use_container_width=True, type="primary"):
            try:
                st.session_state["compare_result"] = compare_products(
                    opts[name_a], opts[name_b]
                )
            except CompareError as e:
                st.error(str(e))
    else:
        st.caption("Need ≥ 2 products in this category.")

    st.divider()
    render_compare_result()


def _compare_llm_analysis(compare_result: dict) -> str:
    from agent.config import chutes, CHUTES_MODEL
    from agent.prompts import COMPARE_ANALYSIS_PROMPT
    a  = compare_result["a"]
    b  = compare_result["b"]
    wc = compare_result["win_counts"]
    ow = compare_result["overall_winner"]
    winner_name = a["name"] if ow == "a" else (b["name"] if ow == "b" else "Tie")
    spec_lines  = [
        f"  {row['key'].replace('_', ' ').title()}: "
        f"{a['name']}={row['a']} vs {b['name']}={row['b']} → {row['winner']}"
        for row in compare_result["specs"]
    ]
    user_msg = (
        f"Product A: {a['name']} — RM {(a.get('price_rm') or 0):,} @ {a.get('vendor', '?')}\n"
        f"Product B: {b['name']} — RM {(b.get('price_rm') or 0):,} @ {b.get('vendor', '?')}\n"
        f"Overall winner: {winner_name} ({wc['a']}–{wc['b']} spec wins, {wc['tie']} ties)\n\n"
        f"Specs:\n" + "\n".join(spec_lines)
    )
    resp = chutes.chat.completions.create(
        model=CHUTES_MODEL,
        messages=[
            {"role": "system", "content": COMPARE_ANALYSIS_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=300,
    )
    return resp.choices[0].message.content


def render_compare_result() -> None:
    result = st.session_state.get("compare_result")
    if not result:
        st.info("Pick two parts above and click **Compare**.")
        return

    a  = result["a"]
    b  = result["b"]
    wc = result["win_counts"]
    ow = result["overall_winner"]
    winner_name = a["name"] if ow == "a" else (b["name"] if ow == "b" else "Tie")

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

    with st.expander("🤖 AI Analysis"):
        analysis_key = f"cmp_analysis_{result['a']['name']}_{result['b']['name']}"
        if analysis_key in st.session_state:
            st.write(st.session_state[analysis_key])
        else:
            if st.button("Generate AI comparison", key="btn_cmp_ai"):
                with st.spinner("Analysing with Llama 3.3…"):
                    analysis = _compare_llm_analysis(result)
                st.session_state[analysis_key] = analysis
                st.rerun()

    if st.button("✕ Clear comparison", key="close_cmp"):
        del st.session_state["compare_result"]
        st.rerun()


# ── Personal Agent mode ───────────────────────────────────────────────────────
def render_personal_mode() -> None:
    st.title("Personal PC Recommendation")
    st.caption(
        "Pick your use case and budget — chat with the agent for details, "
        "then the 3-layer AI pipeline builds it."
    )

    _render_personal_session_sidebar()

    if st.session_state.get("personal_session_view"):
        _render_personal_session_detail(st.session_state["personal_session_view"])
        return

    if st.session_state.get("personal_compare_mode"):
        _render_saved_builds_compare()
        return

    initial = st.session_state.get("personal_initial_input")
    details = st.session_state.get("personal_gathered_details")

    # Phase 2: details chat (form submitted, details not yet gathered)
    if initial and not details:
        _render_personal_details_chat()
        return

    # Phase 2→3 transition: details ready, pipeline not yet run
    if initial and details and "personal_build" not in st.session_state:
        merged = _merge_details_into_input(initial, details)
        _run_personal_pipeline(merged)
        return

    # Phase 3: build result
    if "personal_build" in st.session_state:
        _render_personal_build_phase()
        return

    # Phase 1: form
    _render_personal_form_phase()


def _render_personal_form_phase() -> None:
    with st.form("personal_form"):
        st.markdown("#### Purpose & Budget")
        purposes = st.multiselect(
            "What will you use this PC for?  *(select all that apply)*",
            PURPOSE_OPTIONS,
        )
        budget_min, budget_max = st.slider(
            "Budget range (RM)", 2000, 20_000, (3000, 6000), 500
        )
        st.caption(f"Target: **RM {budget_min:,} – RM {budget_max:,}**")
        submit = st.form_submit_button("Continue →", use_container_width=True, type="primary")

    if submit:
        if not purposes:
            st.error("Please select at least one purpose.")
            return
        for k in ("personal_details_chat", "personal_gathered_details", "personal_build",
                   "personal_candidates", "personal_user_input", "personal_refine_chat",
                   "personal_refining", "personal_session_id"):
            st.session_state.pop(k, None)
        st.session_state["personal_initial_input"] = {
            "purposes": purposes,
            "budget_min": budget_min,
            "budget_max": budget_max,
        }
        st.rerun()


def _render_personal_details_chat() -> None:
    initial  = st.session_state["personal_initial_input"]
    purposes = ", ".join(initial["purposes"])
    bmin     = initial["budget_min"]
    bmax     = initial["budget_max"]
    purpose_summary = (
        f"Purposes: {purposes}. "
        f"Budget: RM {bmin:,} – RM {bmax:,}."
    )

    st.markdown("#### Tell Us More About Your Needs")
    st.caption(f"Selected: **{purposes}**  ·  Budget: RM {bmin:,} – RM {bmax:,}")

    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Change purpose/budget"):
            for k in ("personal_initial_input", "personal_details_chat"):
                st.session_state.pop(k, None)
            st.rerun()

    if "personal_details_chat" not in st.session_state:
        st.session_state["personal_details_chat"] = [{
            "role": "assistant",
            "content": (
                f"You've selected **{purposes}** with a budget of "
                f"RM {bmin:,}–RM {bmax:,}. "
                "Let me ask a few quick questions to tailor the build. "
                "What's your primary focus — for example, competitive gaming at high FPS, "
                "video editing in Premiere Pro, or backend development?"
            ),
        }]

    for m in st.session_state["personal_details_chat"]:
        with st.chat_message(m["role"]):
            disp = clean_details_display(m["content"]) if m["role"] == "assistant" else m["content"]
            st.markdown(disp)

    if prompt := st.chat_input("Tell the agent about your needs…", key="details_input"):
        st.session_state["personal_details_chat"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                reply = details_chat_turn(
                    st.session_state["personal_details_chat"], purpose_summary
                )
            st.markdown(clean_details_display(reply))
        st.session_state["personal_details_chat"].append({"role": "assistant", "content": reply})

        gathered = extract_details(reply)
        if gathered:
            st.session_state["personal_gathered_details"] = gathered
            st.rerun()


def _merge_details_into_input(initial: dict, details: dict) -> dict:
    purposes = initial.get("purposes", [])
    owned    = details.get("owned_parts") or []
    free_parts = []
    if details.get("primary_workload"):
        free_parts.append(f"Primary workload: {details['primary_workload']}.")
    if details.get("specific_software"):
        free_parts.append(f"Software: {details['specific_software']}.")
    return {
        "mode":             "personal",
        "purposes":         purposes,
        "budget_rm":        initial.get("budget_max"),
        "budget_min_rm":    initial.get("budget_min"),
        "aesthetic_style":  "minimal",
        "noise_preference": "balanced",
        "owned_parts":      owned,
        "free_text":        " ".join(free_parts),
    }


def _render_personal_build_phase() -> None:
    build      = st.session_state["personal_build"]
    candidates = st.session_state.get("personal_candidates", {})
    user_input = st.session_state.get("personal_user_input", {})

    grand_total = build["costs"]["grand_total_rm"]
    budget_rm   = user_input.get("budget_rm", 0)
    if budget_rm and grand_total > budget_rm:
        _render_personal_retry(user_input)

    if st.session_state.get("personal_refining"):
        _render_personal_refine_chat()
    else:
        render_full_build(build, candidates, prefix="p_")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("🔧 Refine this build", use_container_width=True):
                st.session_state["personal_refining"] = True
                st.rerun()
        with c2:
            if st.button("📊 Compare saved builds", use_container_width=True):
                st.session_state["personal_compare_mode"] = True
                st.rerun()
        with c3:
            if st.button("🔄 Start fresh", use_container_width=True):
                for k in ("personal_build", "personal_candidates", "personal_user_input",
                          "personal_refine_chat", "personal_refining", "personal_initial_input",
                          "personal_details_chat", "personal_gathered_details", "personal_session_id"):
                    st.session_state.pop(k, None)
                st.rerun()


def _run_personal_pipeline(user_input: dict) -> None:
    status = st.status("Running AI pipeline…", expanded=True)
    with status:
        st.write("**Layer 1** — Parsing intent with Llama 3.3…")
        try:
            intent = parse_intent(user_input)
        except IntentValidationError as e:
            status.update(label="Intent parsing failed", state="error")
            st.error(str(e))
            return
        st.write(f"✓ `{', '.join(intent.get('use_cases', []))}` · tier: `{intent.get('budget_tier', '')}`")

        st.write("**Layer 2** — Semantic catalogue search…")
        candidates = search_all_categories(intent, top_k=3)
        st.write(f"✓ {sum(len(v) for v in candidates.values())} candidates")

        st.write("**Layer 3** — Generating compatible build…")
        try:
            build = generate_build(intent, candidates)
        except BuildGenerationError as e:
            status.update(label="Build generation failed", state="error")
            st.error(str(e))
            return

        grand_total = build["costs"]["grand_total_rm"]
        status.update(
            label=f"Build ready — RM {grand_total:,.2f} ({build.get('attempts', 1)} attempt(s))",
            state="complete",
        )

    session_id = save_session({
        "mode": "personal",
        "user_input": user_input,
        "summary": {
            "use_cases":     intent.get("use_cases", []),
            "budget_rm":     user_input.get("budget_rm"),
            "budget_min_rm": user_input.get("budget_min_rm"),
            "grand_total_rm": grand_total,
        },
        "build":      build,
        "candidates": candidates,
    })
    st.session_state["personal_build"]      = build
    st.session_state["personal_candidates"] = candidates
    st.session_state["personal_user_input"] = user_input
    st.session_state["personal_session_id"] = session_id
    st.rerun()


def _render_personal_retry(user_input: dict) -> None:
    build       = st.session_state["personal_build"]
    grand_total = build["costs"]["grand_total_rm"]
    budget_rm   = user_input.get("budget_rm", 0)
    overage     = grand_total - budget_rm
    st.error(
        f"⚠️ Over budget by **RM {overage:,.2f}** — "
        f"total RM {grand_total:,.2f} vs budget RM {budget_rm:,.2f} (incl. SST & shipping)"
    )
    with st.expander("🔄 Adjust & Retry to fit budget"):
        new_min, new_max = st.slider(
            "Budget range (RM)", 2000, 20_000,
            (int(user_input.get("budget_min_rm", budget_rm * 0.8)),
             int(max(grand_total, budget_rm) + 1000)), 500,
            key="retry_budget",
        )
        new_purposes = st.multiselect(
            "Use cases (remove to reduce cost)", PURPOSE_OPTIONS,
            default=user_input.get("purposes", []), key="retry_purposes",
        )
        if st.button("Rebuild with adjusted parameters", type="primary", key="retry_rebuild"):
            new_input = {**user_input, "budget_rm": new_max, "budget_min_rm": new_min,
                         "purposes": new_purposes}
            for k in ("personal_refine_chat", "personal_refining"):
                st.session_state.pop(k, None)
            _run_personal_pipeline(new_input)


def _render_personal_refine_chat() -> None:
    build      = st.session_state["personal_build"]
    user_input = st.session_state.get("personal_user_input", {})
    costs      = build.get("costs", {})
    intent     = build.get("intent", {})
    summary    = (
        f"Use cases: {', '.join(intent.get('use_cases', user_input.get('purposes', [])))}"
        f" | Budget: RM {user_input.get('budget_min_rm', 0):,.0f}–RM {user_input.get('budget_rm', 0):,.0f}"
        f" | Grand Total: RM {costs.get('grand_total_rm', 0):,.2f}"
        f" | Tier: {intent.get('budget_tier', 'mid_range')}"
    )

    st.markdown("#### Refine Your Build")
    st.caption("Tell the agent your aesthetic preferences, owned parts, or specific needs.")

    if "personal_refine_chat" not in st.session_state:
        st.session_state["personal_refine_chat"] = [{
            "role": "assistant",
            "content": (
                "Your quick build is ready. Let's personalise it — "
                "what aesthetic style do you prefer? "
                "Stealth (dark, no RGB), minimal (clean white/black), "
                "workstation (professional), or RGB gamer (colourful, tempered glass)?"
            ),
        }]

    for m in st.session_state["personal_refine_chat"]:
        with st.chat_message(m["role"]):
            disp = clean_refinement_display(m["content"]) if m["role"] == "assistant" else m["content"]
            st.markdown(disp)

    if prompt := st.chat_input("Tell the agent your preferences…", key="refine_input"):
        st.session_state["personal_refine_chat"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                reply = personal_chat_turn(st.session_state["personal_refine_chat"], summary)
            st.markdown(clean_refinement_display(reply))
        st.session_state["personal_refine_chat"].append({"role": "assistant", "content": reply})

        refinement = extract_refinement(reply)
        if refinement:
            new_input = {
                **user_input,
                "aesthetic_style":  refinement.get("aesthetic_style", "minimal"),
                "noise_preference": refinement.get("noise_preference", "balanced"),
                "free_text":        refinement.get("free_text", ""),
            }
            st.session_state.pop("personal_refining", None)
            _run_personal_pipeline(new_input)

    col_back, _ = st.columns([1, 4])
    with col_back:
        if st.button("← Cancel refinement"):
            st.session_state["personal_refining"] = False
            st.rerun()


def _render_personal_session_sidebar() -> None:
    with st.sidebar:
        st.subheader("Build History")
        sessions = list_sessions(mode="personal")
        if not sessions:
            st.caption("No saved builds yet.")
        else:
            for s in reversed(sessions[-8:]):
                ts    = (s.get("created_at") or "")[:16].replace("T", " ")
                uses  = ", ".join(s.get("use_cases", [])[:2]).title() or "Build"
                total = s.get("grand_total_rm") or 0.0
                with st.expander(uses):
                    st.markdown(f"**RM {total:,.0f}**")
                    st.caption(f"{ts}  ·  `{s['id'][-8:]}`")
                    if st.button("View build", key=f"pview_{s['id']}",
                                 use_container_width=True):
                        st.session_state["personal_session_view"] = s["id"]
                        st.rerun()
        st.divider()


def _render_personal_session_detail(session_id: str) -> None:
    if st.button("← Back to build"):
        st.session_state.pop("personal_session_view", None)
        st.rerun()

    sess = load_session(session_id)
    if not sess:
        st.error("Session not found.")
        return

    summ = sess.get("summary", {})
    ts   = (sess.get("created_at") or "")[:16].replace("T", " ")
    uses = ", ".join(summ.get("use_cases", [])).title() or "General"

    st.markdown(f"### Saved Build — {uses}")
    st.caption(f"`{session_id}`  ·  {ts}")

    m1, m2, m3 = st.columns(3)
    m1.metric("Use Cases",   uses)
    m2.metric("Budget",      f"RM {summ.get('budget_rm', 0):,.0f}")
    m3.metric("Grand Total", f"RM {summ.get('grand_total_rm', 0):,.2f}")

    build      = sess.get("build")
    candidates = sess.get("candidates", {})
    if build:
        st.divider()
        render_full_build(build, candidates, prefix=f"hist_{session_id[-6:]}_")
    else:
        st.caption("Full build data not stored for this session.")


def _render_saved_builds_compare() -> None:
    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Back"):
            st.session_state.pop("personal_compare_mode", None)
            st.rerun()

    st.subheader("📊 Compare Saved Builds")
    sessions = list_sessions(mode="personal")
    if len(sessions) < 2:
        st.info("Need at least 2 saved builds to compare.")
        return

    def _label(s):
        uses  = ", ".join(s.get("use_cases", [])[:2]).title() or "Build"
        total = s.get("grand_total_rm") or 0
        ts    = (s.get("created_at") or "")[:10]
        return f"{uses} · RM {total:,.0f} ({ts})"

    opts  = {_label(s): s["id"] for s in reversed(sessions)}
    names = list(opts.keys())
    c1, c2 = st.columns(2)
    name_a = c1.selectbox("Build A", names, key="cmp_save_a")
    name_b = c2.selectbox("Build B", [n for n in names if n != name_a], key="cmp_save_b")

    if st.button("Compare builds →", type="primary", use_container_width=True):
        sess_a = load_session(opts[name_a])
        sess_b = load_session(opts[name_b])
        if sess_a and sess_b:
            _render_saved_build_diff(sess_a, sess_b)


def _render_saved_build_diff(sess_a: dict, sess_b: dict) -> None:
    build_a = sess_a.get("build", {})
    build_b = sess_b.get("build", {})
    summ_a  = sess_a.get("summary", {})
    summ_b  = sess_b.get("summary", {})
    total_a = summ_a.get("grand_total_rm", 0)
    total_b = summ_b.get("grand_total_rm", 0)
    diff    = total_a - total_b
    uses_a  = ", ".join(summ_a.get("use_cases", [])).title() or "Build A"
    uses_b  = ", ".join(summ_b.get("use_cases", [])).title() or "Build B"

    m1, m2, m3 = st.columns(3)
    m1.metric("Build A", f"RM {total_a:,.2f}", uses_a)
    m2.metric("Build B", f"RM {total_b:,.2f}", uses_b)
    m3.metric("Difference", f"RM {abs(diff):,.2f}",
              "A cheaper" if diff < 0 else ("B cheaper" if diff > 0 else "Same"))

    st.divider()
    items_a  = {i["category"]: i for i in build_a.get("items", [])}
    items_b  = {i["category"]: i for i in build_b.get("items", [])}
    all_cats = sorted(set(list(items_a) + list(items_b)))

    hc, ha, hb = st.columns([2, 4, 4])
    hc.markdown("**Category**")
    ha.markdown(f"**{uses_a}**  *(RM {total_a:,.0f})*")
    hb.markdown(f"**{uses_b}**  *(RM {total_b:,.0f})*")
    st.markdown("---")

    for cat in all_cats:
        ia = items_a.get(cat)
        ib = items_b.get(cat)
        cc, ca, cb = st.columns([2, 4, 4])
        cc.markdown(f"**{cat.replace('_', ' ').title()}**")
        if ia:
            ca.write(f"{ia['name']}\n*RM {ia.get('unit_price_rm', 0):,.0f} · {ia.get('vendor_name', '?')}*")
        else:
            ca.caption("—")
        if ib:
            cb.write(f"{ib['name']}\n*RM {ib.get('unit_price_rm', 0):,.0f} · {ib.get('vendor_name', '?')}*")
        else:
            cb.caption("—")


# ── Business Agent mode (hybrid form → chat → form) ──────────────────────────
def render_business_mode() -> None:
    st.title("Business Fleet Recommendation")
    st.caption(
        "Fill in your company details, chat with the agent about each role, "
        "then confirm office layout — the fleet quote builds automatically."
    )

    _render_session_history_sidebar()

    if st.session_state.get("viewing_session"):
        _render_session_detail(st.session_state["viewing_session"])
        return

    if "business_result" in st.session_state:
        render_business_result(st.session_state["business_result"])
        st.divider()
        if st.button("🔄 Start a new quote"):
            for k in ("business_result", "biz_chat_messages", "biz_spec",
                      "biz_company", "biz_roles", "biz_office", "biz_step"):
                st.session_state.pop(k, None)
            st.rerun()
        return

    _render_business_flow()


def _render_session_history_sidebar() -> None:
    with st.sidebar:
        st.subheader("Session History")
        sessions = list_sessions(mode="business")
        if not sessions:
            st.caption("No saved sessions yet.")
            return
        for s in reversed(sessions[-8:]):
            ts      = (s.get("created_at") or "")[:16].replace("T", " ")
            company = s.get("company_name") or "Unknown"
            pcs     = s.get("total_pcs") or 0
            total   = s.get("total_rm")  or 0.0
            with st.expander(f"{company}"):
                st.markdown(f"**{pcs} PCs** | RM {total:,.0f}")
                st.caption(f"{ts}  ·  `{s['id']}`")
                if st.button("View details", key=f"view_{s['id']}",
                             use_container_width=True):
                    st.session_state["viewing_session"] = s["id"]
                    st.rerun()


def _render_session_detail(session_id: str) -> None:
    if st.button("← Back to agent"):
        st.session_state.pop("viewing_session", None)
        st.rerun()

    sess = load_session(session_id)
    if not sess:
        st.error("Session not found.")
        return

    cp   = sess.get("company_profile", {})
    summ = sess.get("summary", {})
    ts   = (sess.get("created_at") or "")[:16].replace("T", " ")

    st.markdown(f"### Session — {cp.get('name', 'Unknown')}")
    st.caption(
        f"`{sess.get('id')}`  ·  {ts}  ·  "
        f"{cp.get('industry', '—')} · {cp.get('location', '—')}"
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Total PCs",      summ.get("total_pcs", 0))
    m2.metric("PC Fleet Total", f"RM {summ.get('total_grand_total_rm', 0):,.0f}")
    m3.metric("Network (est)",  f"RM {summ.get('network_estimated_total_rm', 0):,.0f}")

    st.subheader("Role Breakdown")
    rb = sess.get("role_breakdown", [])
    if not rb:
        st.caption("No roles recorded.")
    for r in rb:
        st.markdown(f"- **{r['role'].title()}** ×{r['count']}")


def _render_business_flow() -> None:
    step = st.session_state.get("biz_step", 0)

    # Progress stepper
    labels = ["Company", "Roles", "Office", "Generate"]
    cols   = st.columns(4)
    for i, (col, label) in enumerate(zip(cols, labels)):
        if i < step:
            col.markdown(f"✅ {label}")
        elif i == step:
            col.markdown(f"**▶ {label}**")
        else:
            col.markdown(f"◻ {label}")
    st.divider()

    if step == 0:
        _render_company_form()
    elif step == 1:
        _render_roles_chat(st.session_state.get("biz_company", {}))
    elif step == 2:
        _render_office_form(
            st.session_state.get("biz_company", {}),
            st.session_state.get("biz_roles", []),
        )
    else:
        _render_generate_panel(
            st.session_state.get("biz_company", {}),
            st.session_state.get("biz_roles", []),
            st.session_state.get("biz_office", {}),
        )


def _render_company_form() -> None:
    st.markdown("#### Step 1 — Company Details")
    ex = st.session_state.get("biz_company", {})

    industry_idx = INDUSTRY_OPTIONS.index(ex["industry"]) if ex.get("industry") in INDUSTRY_OPTIONS else 0
    size_idx     = SIZE_OPTIONS.index(ex["size"])         if ex.get("size")     in SIZE_OPTIONS     else 1
    city_idx     = MY_CITIES.index(ex["location"])        if ex.get("location") in MY_CITIES        else 0

    with st.form("biz_company_form"):
        name     = st.text_input("Company name", value=ex.get("name", ""),
                                  placeholder="e.g. Acme Sdn Bhd")
        industry = st.selectbox("Industry", INDUSTRY_OPTIONS, index=industry_idx)
        size     = st.selectbox("Company size (headcount)", SIZE_OPTIONS, index=size_idx)
        location = st.selectbox("City / Location", MY_CITIES, index=city_idx)
        submit   = st.form_submit_button("Continue →", type="primary",
                                          use_container_width=True)
    if submit:
        if not name.strip():
            st.error("Company name is required.")
            return
        st.session_state["biz_company"] = {
            "name":     name.strip(),
            "industry": industry,
            "size":     size,
            "location": location,
        }
        st.session_state["biz_step"] = 1
        st.rerun()


def _render_roles_chat(company: dict) -> None:
    st.markdown(f"#### Step 2 — Role Specs  ·  {company['name']}")

    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Edit company"):
            st.session_state["biz_step"] = 0
            st.rerun()

    if "biz_chat_messages" not in st.session_state:
        st.session_state["biz_chat_messages"] = [{
            "role": "assistant",
            "content": (
                f"Got it — **{company['name']}** is a {company['size']}-person "
                f"{company['industry']} company in {company['location']}. "
                "Now let's spec the fleet. What job roles or functions need PCs? "
                "Start with the first role — what do they do day-to-day and how many people?"
            ),
        }]

    for m in st.session_state["biz_chat_messages"]:
        with st.chat_message(m["role"]):
            display = clean_for_display(m["content"]) if m["role"] == "assistant" else m["content"]
            st.markdown(display)

    if prompt := st.chat_input("Describe a role, headcount, or answer the agent's question…"):
        st.session_state["biz_chat_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                reply = chat_turn(st.session_state["biz_chat_messages"],
                                  company_context=company)
            st.markdown(clean_for_display(reply))
        st.session_state["biz_chat_messages"].append({"role": "assistant", "content": reply})

        spec = extract_spec(reply)
        if spec and "roles" in spec:
            st.session_state["biz_roles"] = spec["roles"]
            st.session_state["biz_step"]  = 2
            st.rerun()


def _render_office_form(company: dict, roles: list) -> None:
    st.markdown(f"#### Step 3 — Office Layout  ·  {company['name']}")

    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Edit roles"):
            st.session_state["biz_step"] = 1
            st.rerun()

    total_pcs = sum(r.get("count", 1) for r in roles)
    st.success(f"{len(roles)} role(s) · {total_pcs} total PCs confirmed")
    for r in roles:
        budget_str = f"RM {r['budget_rm']:,}/unit" if r.get("budget_rm") else ""
        st.markdown(
            f"- **{r['role'].title()}** ×{r.get('count', 1)}  "
            f"{budget_str}  ·  {r.get('needs', '')}"
        )

    st.divider()
    st.caption("Office layout is used to size the network infrastructure recommendation.")
    ex = st.session_state.get("biz_office", {})
    with st.form("biz_office_form"):
        floor_area   = st.number_input("Floor area (sqm)", min_value=0,
                                        value=int(ex.get("floor_area_sqm") or 0),
                                        help="Leave 0 if unknown")
        total_floors = st.number_input("Number of floors", min_value=1,
                                        value=int(ex.get("total_floors") or 1))
        has_remote   = st.checkbox("Has remote workers",
                                    value=bool(ex.get("has_remote_workers", False)))
        submit       = st.form_submit_button("Continue →", type="primary",
                                              use_container_width=True)
    if submit:
        st.session_state["biz_office"] = {
            "floor_area_sqm":     float(floor_area) if floor_area > 0 else None,
            "total_floors":       int(total_floors),
            "has_remote_workers": has_remote,
        }
        st.session_state["biz_step"] = 3
        st.rerun()


def _render_generate_panel(company: dict, roles: list, office: dict) -> None:
    st.markdown(f"#### Step 4 — Generate Fleet Quote  ·  {company['name']}")

    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Edit office"):
            st.session_state["biz_step"] = 2
            st.rerun()

    total_pcs = sum(r.get("count", 1) for r in roles)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Roles:**")
        for r in roles:
            budget_str = f"RM {r['budget_rm']:,}/unit" if r.get("budget_rm") else ""
            st.markdown(f"- **{r['role'].title()}** ×{r.get('count', 1)}  {budget_str}")
    with col2:
        st.markdown("**Office:**")
        area_str = f"{office['floor_area_sqm']:,.0f} sqm" if office.get("floor_area_sqm") else "area unknown"
        st.markdown(f"- {area_str} · {office.get('total_floors', 1)} floor(s)")
        st.markdown(f"- Remote workers: {'Yes' if office.get('has_remote_workers') else 'No'}")

    st.divider()
    if st.button(f"🏢 Generate Fleet Quote ({total_pcs} PCs)", type="primary",
                  use_container_width=True):
        spec = {
            "company_profile": company,
            "roles":           roles,
            "office":          office,
        }
        with st.spinner("Building fleet — running 3-layer pipeline per role…"):
            result = generate_quote_from_spec(spec)
        st.session_state["business_result"] = result
        st.rerun()


def _rebuild_business_role(result: dict, role: str, new_budget: float, new_needs: str) -> None:
    data    = result["role_results"][role]
    count   = data.get("count", 1)
    company = result["company_profile"]
    intent_input = {
        "mode": "business", "company_profile": company,
        "role": {"role": role, "count": count},
        "purposes": [], "budget_rm_per_unit": new_budget,
        "owned_parts": [], "free_text": new_needs,
        "location": company.get("location", "Kuala Lumpur"),
    }
    status = st.status(f"Rebuilding {role.title()}…", expanded=True)
    with status:
        try:
            intent     = parse_intent(intent_input)
            candidates = search_all_categories(intent, top_k=3)
            build      = generate_build(intent, candidates)
            per_unit   = build["costs"]["grand_total_rm"]
            result["role_results"][role] = {
                "count":      count,
                "per_unit":   per_unit,
                "role_total": round(per_unit * count, 2),
                "build":      build,
                "candidates": candidates,
            }
            result["total_cost"] = sum(
                d.get("role_total", 0) for d in result["role_results"].values()
                if "error" not in d
            )
            st.session_state["business_result"] = result
            status.update(label=f"{role.title()} rebuilt — RM {per_unit:,.2f}/unit", state="complete")
        except Exception as e:
            status.update(label=f"Rebuild failed: {e}", state="error")
            return
    st.rerun()


def render_business_result(result: dict) -> None:
    company      = result["company_profile"]
    role_results = result["role_results"]
    network      = result["network"]

    st.divider()
    st.markdown(f"### Fleet Quote — {company['name']}")
    st.caption(f"Session `{result.get('session_id', '')}`  ·  saved to sessions.json")

    # Two separate budget lines — network is advisory, NOT part of the PC budget
    net_total = network.get("estimated_total_rm", 0)
    m1, m2, m3 = st.columns(3)
    m1.metric("Total PCs",       result["total_pcs"])
    m2.metric("PC Fleet Budget", f"RM {result['total_cost']:,.0f}")
    m3.metric("Network Budget",  f"RM {net_total:,.0f}",
              help="Separate advisory line — not included in the PC fleet budget.")
    st.caption(
        f"PC fleet and network are **separate budget lines**.  "
        f"Combined estimate (informational): RM {result['total_cost'] + net_total:,.0f}."
    )

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

            if build.get("budget_exceeded") or any(
                "OVER BUDGET" in str(w) for w in build.get("warnings", [])
            ):
                with st.expander(f"🔄 Rebuild {role.title()} with adjusted parameters"):
                    nb = st.number_input(
                        "New budget/unit (RM)", min_value=500,
                        value=int(per_unit * 1.15), step=500,
                        key=f"biz_retry_budget_{role}",
                    )
                    nn = st.text_area(
                        "Simplified workload needs (optional)", value="",
                        key=f"biz_retry_needs_{role}",
                    )
                    if st.button(f"Rebuild {role.title()}", type="primary",
                                 key=f"biz_retry_btn_{role}"):
                        _rebuild_business_role(
                            st.session_state["business_result"], role, float(nb), nn
                        )

    render_network_section(network)
    _render_export_section(result)


def _render_export_section(result: dict) -> None:
    st.divider()
    st.subheader("📥 Export Reports")
    company_slug = result["company_profile"].get("name", "fleet").replace(" ", "_")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📊 Download Financial Report (Excel)",
            data=generate_financial_excel(result),
            file_name=f"financial_report_{company_slug}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.caption("BOM + cost breakdown — Summary, per-role, and Network sheets.")
    with col2:
        st.download_button(
            "📋 Download RFP Document (PDF)",
            data=generate_rfp_pdf(result),
            file_name=f"rfp_{company_slug}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        st.caption("Vendor-facing procurement document with 8 sections.")


def render_network_section(network: dict) -> None:
    """Network infrastructure as its own BOM-style section + separate budget total."""
    st.subheader("🌐 Network Infrastructure")
    st.caption(network.get("disclaimer", "Advisory only — separate budget line, not in the PC quote."))

    h1, h2, h3 = st.columns([2, 5, 2])
    h1.markdown("**Item**")
    h2.markdown("**Details**")
    h3.markdown("**Price (RM)**")
    st.markdown("---")

    rows: list[tuple[str, str, float]] = []

    sw = network.get("switch")
    if sw:
        qty = sw.get("quantity", 1)
        rows.append((
            "Switch",
            f"{sw['name']} — {sw['description']} (×{qty})",
            sw.get("subtotal_rm", sw.get("price_rm", 0)),
        ))

    rt = network.get("router")
    if rt:
        rows.append(("Router", f"{rt['name']} — {rt['description']}", rt.get("price_rm", 0)))

    nas = network.get("nas")
    if nas:
        rows.append(("NAS", f"{nas['name']} — {nas['description']}", nas.get("price_rm", 0)))

    wifi = network.get("wifi")
    if wifi:
        rows.append((
            "WiFi APs",
            f"{wifi.get('recommendation', '')} "
            f"(×{wifi.get('access_points_qty', 0)} @ RM {wifi.get('unit_price_rm', 0):,})",
            wifi.get("subtotal_rm", 0),
        ))

    cabling = network.get("cabling")
    if cabling:
        rows.append((
            "Cat6 Cabling",
            f"~{cabling.get('estimated_metres', 0)} m · "
            f"{cabling.get('bulk_boxes_qty', 0)} box(es) + "
            f"{cabling.get('patch_cables_qty', 0)} patch cables",
            cabling.get("subtotal_rm", 0),
        ))

    for name, details, price in rows:
        c1, c2, c3 = st.columns([2, 5, 2])
        c1.markdown(f"**{name}**")
        c2.write(details)
        c3.write(f"RM {price:,.0f}")

    st.markdown("---")
    net_total    = network.get("estimated_total_rm", 0)
    budget_range = network.get("estimated_budget_range_rm", [0, 0])
    st.markdown(
        f"### Network Total: RM {net_total:,.0f}"
    )
    st.caption(
        f"Budget range: RM {budget_range[0]:,} – RM {budget_range[1]:,}  ·  "
        f"separate from the PC fleet budget."
    )


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    init_resources()             # warm up catalogue + embeddings
    render_sidebar_header()

    pages = [
        st.Page(render_personal_mode, title="Personal",      icon="🖥️", default=True),
        st.Page(render_business_mode, title="Business",      icon="🏢"),
        st.Page(render_compare_page,  title="Compare Parts", icon="⚖️"),
    ]
    st.navigation(pages).run()


if __name__ == "__main__":
    main()

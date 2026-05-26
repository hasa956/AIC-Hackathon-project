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
    list_sessions, load_session, generate_quote_from_spec, save_session, delete_session,
)
from agent.business_chat import chat_turn, extract_spec, clean_for_display
from agent.personal_chat import (
    details_chat_turn, extract_details, clean_details_display,
)
from agent.reports import generate_financial_excel, generate_rfp_pdf

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SpekAI — Your AI Sales Engineer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
PURPOSE_OPTIONS = [
    "Work & Office", "Gaming & Entertainment", "Content Creation",
    "Development & Programming", "General Purpose",
]

PURPOSE_FIRST_QUESTION = {
    "Work & Office": (
        "What apps do you use most — Microsoft 365, video calls (Teams/Zoom), "
        "or any specialised software like accounting tools or ERP systems?"
    ),
    "Gaming & Entertainment": (
        "What games do you mainly play — competitive FPS (Valorant, CS2), "
        "AAA titles (Cyberpunk, RDR2), or a mix? And what monitor resolution are you targeting?"
    ),
    "Content Creation": (
        "What kind of content do you create — video editing, photo work, 3D/animation, or streaming? "
        "And which software do you use (Premiere, DaVinci, Blender, Photoshop)?"
    ),
    "Development & Programming": (
        "What's your main stack — heavy compiling, Docker/VMs, data science/ML, or general web dev? "
        "And do you run any resource-heavy workloads like training models or large builds?"
    ),
    "General Purpose": (
        "What do you mainly use a PC for day-to-day — browsing, light gaming, streaming, "
        "or home/family use?"
    ),
}

PURPOSE_CONTEXT = {
    "Work & Office": (
        "Typical activities: documents, spreadsheets, email, video calls (Teams/Zoom), "
        "web browsing, light data work. Software: Microsoft 365, Google Workspace, Outlook. "
        "Priority: CPU stability, RAM, fast SSD. GPU is secondary — integrated is often enough."
    ),
    "Gaming & Entertainment": (
        "Typical activities: PC gaming (AAA/competitive/indie), streaming content, "
        "light video playback. Key details to gather: target FPS, game titles, monitor resolution. "
        "Priority: GPU is king, then CPU, then RAM speed. Storage for game libraries."
    ),
    "Content Creation": (
        "Typical activities: video editing (Premiere/DaVinci), photo editing (Photoshop/Lightroom), "
        "3D rendering, illustration, audio production, YouTube/streaming. "
        "Priority: CPU core count, RAM (32GB+), fast NVMe storage, capable GPU for rendering/encoding."
    ),
    "Development & Programming": (
        "Typical activities: coding in IDEs (VS Code/JetBrains), running Docker containers, "
        "compiling builds, running local servers, virtual machines, data science notebooks. "
        "Priority: CPU multi-core, RAM (16–32GB+), fast NVMe. GPU optional unless ML workloads."
    ),
    "General Purpose": (
        "Typical activities: everyday computing — web browsing, streaming, light office work, "
        "casual gaming, social media, home use. "
        "Priority: balanced build, value for money, reliability over raw performance."
    ),
}
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

CATEGORY_ICONS = {
    "cpu": "", "motherboard": "", "ram": "",
    "gpu": "", "storage": "", "psu": "",
    "cooler": "", "case": "", "case_fans": "",
    "thermal_paste": "",
}


def _inject_personal_css() -> None:
    st.markdown("""<style>
    .pc-card {
        background: linear-gradient(135deg, #0D1424, #0A0F1E);
        border-radius: 12px;
        padding: 14px 20px;
        margin: 6px 0 2px 0;
        border: 1px solid #1E2A3A;
        border-left: 3px solid #00D4FF;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .pc-card:hover {
        border-color: #2D3748;
        border-left-color: #33DDFF;
        box-shadow: 0 4px 18px rgba(0,212,255,0.10);
    }
    .pc-card-left { flex: 1; min-width: 0; }
    .pc-cat { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.10em; color: #6B7280; margin-bottom: 3px; font-weight: 600; }
    .pc-name { font-size: 0.96rem; font-weight: 600; color: #F9FAFB; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .pc-vendor { font-size: 0.78rem; color: #4B5563; }
    .pc-price { font-size: 1.1rem; font-weight: 700; color: #00D4FF; white-space: nowrap; margin-left: 20px; padding-top: 2px; }
    .phase-bar { display: flex; align-items: center; gap: 0; margin-bottom: 28px; }
    .phase-step { display: flex; align-items: center; gap: 8px; }
    .phase-dot-done {
        width: 28px; height: 28px; border-radius: 50%;
        background: #00D4FF; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.72rem; font-weight: 700; color: #0A0F1E;
    }
    .phase-dot-active {
        width: 28px; height: 28px; border-radius: 50%;
        background: #00D4FF; box-shadow: 0 0 0 4px rgba(0,212,255,0.2);
        flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.72rem; font-weight: 700; color: #0A0F1E;
    }
    .phase-dot-todo {
        width: 28px; height: 28px; border-radius: 50%;
        background: #111827; border: 2px solid #1E2A3A; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.72rem; color: #4B5563;
    }
    .phase-line { flex: 1; height: 2px; background: #1E2A3A; margin: 0 8px; min-width: 32px; max-width: 80px; }
    .phase-line-done { flex: 1; height: 2px; background: #00D4FF; margin: 0 8px; min-width: 32px; max-width: 80px; }
    .phase-lbl { font-size: 0.80rem; color: #6B7280; font-weight: 500; }
    .phase-lbl-active { font-size: 0.80rem; color: #F9FAFB; font-weight: 700; }
    .budget-ok-badge {
        background: linear-gradient(135deg, #061812, #092215);
        border: 1px solid rgba(16,185,129,0.3);
        border-radius: 14px;
        padding: 22px 26px;
        margin: 12px 0;
    }
    .budget-ok-badge .big-total { font-size: 2.4rem; font-weight: 800; color: #10B981; letter-spacing: -0.02em; font-family: 'Syne', sans-serif; }
    .budget-ok-badge .sub { font-size: 0.83rem; color: #34D399; margin-top: 5px; opacity: 0.9; }
    .budget-over-badge {
        background: linear-gradient(135deg, #1A1000, #231500);
        border: 1px solid rgba(245,158,11,0.3);
        border-radius: 14px;
        padding: 22px 26px;
        margin: 12px 0;
    }
    .budget-over-badge .big-total { font-size: 2.4rem; font-weight: 800; color: #F59E0B; letter-spacing: -0.02em; font-family: 'Syne', sans-serif; }
    .budget-over-badge .sub { font-size: 0.83rem; color: #FCD34D; margin-top: 5px; opacity: 0.9; }
    </style>""", unsafe_allow_html=True)


def _inject_business_css() -> None:
    st.markdown("""<style>
    .biz-card {
        background: linear-gradient(135deg, #0D1424, #0A0F1E);
        border-radius: 12px;
        padding: 13px 18px;
        margin: 5px 0 2px 0;
        border: 1px solid #1E2A3A;
        border-left: 3px solid #7C3AED;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        display: flex;
        justify-content: space-between;
        align-items: center;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .biz-card:hover {
        border-color: #2D3748;
        border-left-color: #A78BFA;
        box-shadow: 0 4px 18px rgba(124,58,237,0.12);
    }
    .biz-card-left { flex: 1; min-width: 0; }
    .biz-cat { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.10em; color: #6B7280; margin-bottom: 1px; font-weight: 600; }
    .biz-name { font-size: 0.92rem; font-weight: 600; color: #F9FAFB; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .biz-vendor { font-size: 0.78rem; color: #4B5563; }
    .biz-price { font-size: 1.05rem; font-weight: 700; color: #A78BFA; white-space: nowrap; margin-left: 16px; }
    .role-badge { display: inline-block; background: rgba(124,58,237,0.12); color: #A78BFA; padding: 3px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; border: 1px solid rgba(124,58,237,0.3); }
    /* Business stepper */
    .biz-stepper { display: flex; align-items: center; margin-bottom: 28px; padding: 0 2px; }
    .biz-step-wrap { display: flex; align-items: center; }
    .biz-step-dot {
        width: 32px; height: 32px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.78rem; font-weight: 700; flex-shrink: 0;
    }
    .biz-step-dot-done { background: #7C3AED; color: #fff; }
    .biz-step-dot-active { background: #7C3AED; color: #fff; box-shadow: 0 0 0 4px rgba(124,58,237,0.22); }
    .biz-step-dot-todo { background: #111827; border: 2px solid #1E2A3A; color: #4B5563; }
    .biz-step-content { padding-left: 10px; padding-right: 4px; }
    .biz-step-num { font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.08em; color: #6B7280; font-weight: 600; line-height: 1; }
    .biz-step-lbl { font-size: 0.88rem; font-weight: 600; color: #F9FAFB; line-height: 1.3; }
    .biz-step-lbl-todo { font-size: 0.88rem; font-weight: 500; color: #6B7280; line-height: 1.3; }
    .biz-step-line { flex: 1; height: 2px; margin: 0 12px; min-width: 20px; }
    .biz-step-line-done { background: #7C3AED; }
    .biz-step-line-todo { background: #1E2A3A; }
    </style>""", unsafe_allow_html=True)


def _render_personal_phase_progress(phase: int) -> None:
    phases = ["Select Purpose", "Tell Us More", "Your Build"]
    parts = []
    for i, label in enumerate(phases, 1):
        if i < phase:
            parts.append(f'<div class="phase-step"><div class="phase-dot-done">&#10003;</div><span class="phase-lbl">{label}</span></div>')
            if i < len(phases):
                parts.append('<div class="phase-line-done"></div>')
        elif i == phase:
            parts.append(f'<div class="phase-step"><div class="phase-dot-active">{i}</div><span class="phase-lbl-active">{label}</span></div>')
            if i < len(phases):
                parts.append('<div class="phase-line"></div>')
        else:
            parts.append(f'<div class="phase-step"><div class="phase-dot-todo">{i}</div><span class="phase-lbl">{label}</span></div>')
            if i < len(phases):
                parts.append('<div class="phase-line"></div>')
    st.markdown(f'<div class="phase-bar">{"".join(parts)}</div>', unsafe_allow_html=True)


def _inject_global_css() -> None:
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Sans:wght@300;400;500;600;700&display=swap');

    :root {
        --bg-primary: #0A0F1E;
        --bg-secondary: #111827;
        --bg-card: #0D1424;
        --accent-cyan: #00D4FF;
        --accent-violet: #7C3AED;
        --accent-violet-light: #A78BFA;
        --text-primary: #F9FAFB;
        --text-secondary: #9CA3AF;
        --success: #10B981;
        --warning: #F59E0B;
        --border: #1E2A3A;
        --border-light: #2D3748;
    }

    html, body { background-color: var(--bg-primary) !important; }
    .stApp { background-color: var(--bg-primary) !important; font-family: 'DM Sans', sans-serif !important; }

    html, body, .stMarkdown, p, li,
    .stCaption, label { font-family: 'DM Sans', sans-serif !important; }

    /* Restore Material Symbols font for sidebar toggle icon spans */
    button[data-testid="collapsedControl"] span,
    [data-testid="stSidebarCollapseButton"] span,
    [data-testid="stSidebarCollapseButton"] button span {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', sans-serif !important;
    }

    /* Collapsed sidebar re-open button — make it visible */
    button[data-testid="collapsedControl"] {
        background: #111827 !important;
        border: 1px solid #1E2A3A !important;
        border-left: none !important;
        border-radius: 0 8px 8px 0 !important;
        color: #9CA3AF !important;
        width: 28px !important;
        opacity: 1 !important;
        visibility: visible !important;
    }
    button[data-testid="collapsedControl"]:hover {
        background: #1E2A3A !important;
        border-color: #00D4FF !important;
        color: #00D4FF !important;
    }
    button[data-testid="collapsedControl"] svg {
        fill: #9CA3AF !important;
    }
    button[data-testid="collapsedControl"]:hover svg {
        fill: #00D4FF !important;
    }

    /* Subtle dot grid on main content area */
    section.main > div:first-child {
        background-image: radial-gradient(rgba(0,212,255,0.035) 1px, transparent 1px);
        background-size: 36px 36px;
    }

    h1, h2, h3, h4, h5, h6,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
        font-family: 'Syne', sans-serif !important;
        color: var(--text-primary) !important;
        font-weight: 700 !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] { background: var(--bg-secondary) !important; border-right: 1px solid var(--border) !important; }
    section[data-testid="stSidebar"] > div { background: var(--bg-secondary) !important; }

    /* Primary buttons — cyan */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button {
        background: var(--accent-cyan) !important;
        color: #0A0F1E !important;
        border: none !important;
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 0 16px rgba(0,212,255,0.18) !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover {
        background: #33DDFF !important;
        box-shadow: 0 0 28px rgba(0,212,255,0.35) !important;
        transform: translateY(-1px) !important;
    }

    /* Secondary buttons */
    .stButton > button:not([kind="primary"]) {
        background: transparent !important;
        color: var(--text-secondary) !important;
        border: 1px solid var(--border-light) !important;
        border-radius: 8px !important;
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button:not([kind="primary"]):hover {
        border-color: var(--accent-cyan) !important;
        color: var(--accent-cyan) !important;
        background: rgba(0,212,255,0.05) !important;
    }

    /* Inputs */
    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
        font-family: 'DM Sans', sans-serif !important;
        transition: border-color 0.2s ease !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
        border-color: var(--accent-cyan) !important;
        box-shadow: 0 0 0 2px rgba(0,212,255,0.12) !important;
    }

    /* Selectbox */
    .stSelectbox > div > div {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
    }

    /* Slider accent */
    .stSlider > div > div > div > div { background: var(--accent-cyan) !important; }

    /* Metrics */
    div[data-testid="metric-container"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        padding: 14px 18px !important;
    }
    div[data-testid="metric-container"] label {
        color: var(--text-secondary) !important;
        font-size: 0.76rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.07em !important;
    }

    /* Expanders */
    details {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
    }

    /* Divider */
    hr { border-color: var(--border) !important; opacity: 0.4 !important; }

    /* Custom scrollbar */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: var(--bg-primary); }
    ::-webkit-scrollbar-thumb { background: #1E2A3A; border-radius: 99px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--accent-cyan); }

    /* Chat */
    .stChatMessage { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: 12px !important; }

    /* SpekAI branded loading pulse */
    .spek-loading {
        background: linear-gradient(135deg, #0D1424, #0A1628);
        border: 1px solid rgba(0,212,255,0.25);
        border-radius: 12px;
        padding: 18px 24px;
        color: var(--accent-cyan);
        font-weight: 600;
        font-size: 0.92rem;
        text-align: center;
        animation: spekPulse 1.8s ease-in-out infinite;
        margin: 8px 0;
    }
    @keyframes spekPulse {
        0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(0,212,255,0.25); }
        50% { opacity: 0.75; box-shadow: 0 0 24px rgba(0,212,255,0.12); }
    }

    /* Sidebar logo */
    .spek-sidebar-logo { padding: 4px 0 12px 0; }
    .spek-logo-mark { font-family: 'Syne', sans-serif; font-size: 1.35rem; font-weight: 800; line-height: 1; }
    .spek-logo-spek { color: #F9FAFB; }
    .spek-logo-ai { color: #00D4FF; }
    .spek-logo-bolt { color: #00D4FF; margin-right: 4px; }
    .spek-tagline { font-size: 0.72rem; color: #9CA3AF; margin-top: 3px; letter-spacing: 0.04em; }
    .spek-cyan-rule { height: 1px; background: linear-gradient(90deg, rgba(0,212,255,0.5), transparent); margin: 12px 0; }
    .spek-api-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #10B981; margin-right: 6px; vertical-align: middle; }
    .spek-api-dot-off { background: #6B7280; }
    .spek-api-label { font-size: 0.78rem; color: #9CA3AF; }
    .spek-sidebar-footer { font-size: 0.70rem; color: #4B5563; text-align: center; padding: 8px 0 4px 0; letter-spacing: 0.02em; }

    /* Compare winner badge */
    .cmp-winner-badge {
        display: inline-block;
        background: rgba(0,212,255,0.12);
        color: #00D4FF;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 4px;
        border: 1px solid rgba(0,212,255,0.25);
        margin-right: 6px;
        vertical-align: middle;
    }

    </style>""", unsafe_allow_html=True)


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


def render_bom_item(item: dict, build: dict, candidates: dict, prefix: str = "", mode: str = "business") -> None:
    cat    = item["category"]
    name   = item["name"]
    pid    = item.get("product_id", name)
    price  = item.get("unit_price_rm", 0)
    vendor = item.get("vendor_name", "—")
    icon   = CATEGORY_ICONS.get(cat, "")
    alts   = [c for c in candidates.get(cat, []) if c["id"] != pid]
    explain_key = f"{prefix}explain_{pid}"

    if mode == "personal":
        cat_display = CATEGORY_DISPLAY.get(cat, cat)
        st.markdown(f"""
        <div class="pc-card">
            <div class="pc-card-left">
                <div class="pc-cat">{icon}&nbsp;&nbsp;{cat_display}</div>
                <div class="pc-name">{name}</div>
                <div class="pc-vendor">{vendor}</div>
            </div>
            <div class="pc-price">RM {price:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    else:
        cat_display = CATEGORY_DISPLAY.get(cat, cat)
        st.markdown(f"""
        <div class="biz-card">
            <div class="biz-card-left">
                <div class="biz-cat">{icon}&nbsp;&nbsp;{cat_display}</div>
                <div class="biz-name">{name}</div>
                <div class="biz-vendor">{vendor}</div>
            </div>
            <div class="biz-price">RM {price:,.0f}</div>
        </div>""", unsafe_allow_html=True)

    ex1, ex2 = st.columns(2)
    with ex1:
        with st.expander("Explain"):
            if explain_key in st.session_state:
                st.write(st.session_state[explain_key])
            else:
                if st.button("Generate explanation", key=f"{prefix}btn_exp_{pid}"):
                    with st.spinner("Asking DeepSeek-V3.2…"):
                        _stream_to_state(explain_key, explain_component(item, build, alts, stream=True))
    with ex2:
        with st.expander("Vendors"):
            render_vendor_table(pid, cat)


def render_build_costs(costs: dict, mode: str = "business") -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Subtotal",    f"RM {costs.get('subtotal_rm',       0):,.2f}")
    c2.metric("Shipping",    f"RM {costs.get('shipping_total_rm', 0):,.2f}")
    c3.metric("SST (6%)",    f"RM {costs.get('sst_rm',            0):,.2f}")
    c4.metric("Grand Total", f"RM {costs.get('grand_total_rm',    0):,.2f}")


def render_full_build(build: dict, candidates: dict, prefix: str = "", mode: str = "business") -> None:
    costs       = build.get("costs", {})
    grand_total = costs.get("grand_total_rm", 0)
    intent_data = build.get("intent", {})
    budget_rm   = intent_data.get("budget_rm")

    issues = build.get("compatibility_issues", [])
    if not issues:
        st.success("✓ All compatibility checks passed")
    else:
        for issue in issues:
            st.error(f"Warning: {issue}")

    if budget_rm:
        if grand_total > budget_rm:
            overage = grand_total - budget_rm
            if mode == "personal":
                st.markdown(f"""<div class="budget-over-badge">
                    <div class="big-total">RM {grand_total:,.0f}</div>
                    <div class="sub">Warning: Over budget by RM {overage:,.0f} (budget: RM {budget_rm:,.0f} incl. SST & shipping)</div>
                </div>""", unsafe_allow_html=True)
            else:
                st.error(f"Warning: Over budget by RM {overage:,.2f} — total RM {grand_total:,.2f} vs RM {budget_rm:,.2f}")
        else:
            remaining = budget_rm - grand_total
            if mode == "personal":
                st.markdown(f"""<div class="budget-ok-badge">
                    <div class="big-total">RM {grand_total:,.0f}</div>
                    <div class="sub">✓ RM {remaining:,.0f} under budget (budget: RM {budget_rm:,.0f} incl. SST & shipping)</div>
                </div>""", unsafe_allow_html=True)
            else:
                st.info(f"Within budget — RM {remaining:,.2f} remaining (total RM {grand_total:,.2f} of RM {budget_rm:,.2f})")

    if mode == "business":
        render_build_costs(costs, mode)

    rationale = build.get("build_rationale", "")
    warnings  = build.get("warnings", [])
    if rationale or warnings:
        with st.expander("Agent's Reasoning"):
            if rationale:
                st.write(rationale)
            for w in warnings:
                st.warning(w)

    st.subheader("Bill of Materials")
    for item in build.get("items", []):
        render_bom_item(item, build, candidates, prefix=prefix, mode=mode)


# ── Landing page ─────────────────────────────────────────────────────────────
def _inject_landing_css() -> None:
    st.markdown("""<style>
    /* ── Hero ────────────────────────────────── */
    .landing-hero {
        text-align: center;
        padding: 52px 0 32px;
        position: relative;
        overflow: hidden;
    }
    .hero-glow-orb {
        position: absolute;
        width: 800px; height: 360px;
        background: radial-gradient(ellipse at center, rgba(0,212,255,0.09) 0%, transparent 65%);
        top: -40px; left: 50%; transform: translateX(-50%);
        pointer-events: none;
        z-index: 0;
    }
    .hero-glow-violet {
        position: absolute;
        width: 500px; height: 300px;
        background: radial-gradient(ellipse at center, rgba(124,58,237,0.07) 0%, transparent 65%);
        top: 20px; right: 10%;
        pointer-events: none;
        z-index: 0;
    }
    .landing-tag {
        display: inline-block;
        background: rgba(0,212,255,0.07);
        color: #00D4FF;
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        padding: 5px 16px;
        border-radius: 99px;
        border: 1px solid rgba(0,212,255,0.2);
        margin-bottom: 24px;
        position: relative; z-index: 1;
    }
    .landing-title {
        font-family: 'Syne', sans-serif;
        font-size: 5.2rem;
        font-weight: 800;
        line-height: 1;
        margin-bottom: 12px;
        text-shadow: 0 0 80px rgba(0,212,255,0.4);
        position: relative; z-index: 1;
    }
    .t-spek { color: #F9FAFB; }
    .t-ai   { color: #00D4FF; }
    .landing-tagline {
        font-family: 'Syne', sans-serif;
        font-size: 1.05rem;
        color: #9CA3AF;
        font-weight: 500;
        letter-spacing: 0.06em;
        margin-bottom: 28px;
        position: relative; z-index: 1;
    }

    /* ── Feature strip ───────────────────────── */
    .feature-strip {
        display: flex;
        gap: 10px;
        justify-content: center;
        flex-wrap: wrap;
        margin-bottom: 8px;
        position: relative; z-index: 1;
    }
    .feature-pill {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 99px;
        padding: 6px 14px;
        font-size: 0.78rem;
        color: #9CA3AF;
        font-weight: 500;
        white-space: nowrap;
    }
    .fp-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .fp-cyan { background: #00D4FF; box-shadow: 0 0 6px rgba(0,212,255,0.6); }
    .fp-violet { background: #A78BFA; box-shadow: 0 0 6px rgba(167,139,250,0.5); }

    /* ── Mode cards ──────────────────────────── */
    .mode-card {
        border-radius: 16px;
        padding: 28px 24px 24px 24px;
        margin-bottom: 12px;
        min-height: 300px;
        border: 1px solid #1E2A3A;
        background: linear-gradient(160deg, #0D1424 0%, #0A0F1E 100%);
        box-shadow: 0 4px 28px rgba(0,0,0,0.45);
        transition: box-shadow 0.25s ease, border-color 0.25s ease, transform 0.25s ease;
        cursor: pointer;
        position: relative;
        overflow: hidden;
    }
    .mode-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        transition: opacity 0.25s ease;
    }
    .mode-card-personal::before { background: linear-gradient(90deg, #00D4FF, #33DDFF); }
    .mode-card-business::before { background: linear-gradient(90deg, #7C3AED, #A78BFA); }
    .mode-card-compare::before  { background: linear-gradient(90deg, #A78BFA, #C4B5FD); }

    .mode-card-personal:hover {
        border-color: rgba(0,212,255,0.28);
        box-shadow: 0 12px 48px rgba(0,212,255,0.12), 0 4px 28px rgba(0,0,0,0.5);
        transform: translateY(-4px);
    }
    .mode-card-business:hover {
        border-color: rgba(124,58,237,0.3);
        box-shadow: 0 12px 48px rgba(124,58,237,0.12), 0 4px 28px rgba(0,0,0,0.5);
        transform: translateY(-4px);
    }
    .mode-card-compare:hover {
        border-color: rgba(167,139,250,0.28);
        box-shadow: 0 12px 48px rgba(167,139,250,0.10), 0 4px 28px rgba(0,0,0,0.5);
        transform: translateY(-4px);
    }

    .mode-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 42px; height: 42px;
        border-radius: 11px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 14px;
        font-family: 'Syne', sans-serif;
        letter-spacing: 0.04em;
    }
    .badge-personal { background: rgba(0,212,255,0.10); color: #00D4FF; border: 1px solid rgba(0,212,255,0.22); }
    .badge-business { background: rgba(124,58,237,0.12); color: #A78BFA; border: 1px solid rgba(124,58,237,0.25); }
    .badge-compare  { background: rgba(167,139,250,0.10); color: #C4B5FD; border: 1px solid rgba(167,139,250,0.2); }

    .mode-title { font-size: 1.25rem; font-weight: 700; color: #F9FAFB; margin-bottom: 8px; font-family: 'Syne', sans-serif; }
    .mode-desc { font-size: 0.87rem; color: #6B7280; margin-bottom: 16px; line-height: 1.65; }
    .mode-features { padding-left: 0; color: #6B7280; font-size: 0.83rem; line-height: 1.95; margin: 0; list-style: none; }
    .mode-features li::before { content: '· '; color: #374151; font-weight: 700; }
    </style>""", unsafe_allow_html=True)


def render_landing_page() -> None:
    _inject_landing_css()

    # Hero with glow orbs + feature strip
    st.markdown("""
    <div class="landing-hero">
        <div class="hero-glow-orb"></div>
        <div class="hero-glow-violet"></div>
        <div class="landing-tag">AI Marathon 2026 &nbsp;·&nbsp; Autonomous Sales Engineer</div>
        <div class="landing-title">
            <span class="t-spek">Spek</span><span class="t-ai">AI</span>
        </div>
        <div class="landing-tagline">Your AI Sales Engineer</div>
        <div class="feature-strip">
            <div class="feature-pill"><div class="fp-dot fp-cyan"></div>3-Layer AI Pipeline</div>
            <div class="feature-pill"><div class="fp-dot fp-violet"></div>Malaysian Pricing</div>
            <div class="feature-pill"><div class="fp-dot fp-cyan"></div>Personal &amp; Business</div>
            <div class="feature-pill"><div class="fp-dot fp-violet"></div>Excel &amp; PDF Exports</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("""<div class="mode-card mode-card-personal">
            <div class="mode-badge badge-personal">PC</div>
            <div class="mode-title">Personal Build</div>
            <div class="mode-desc">Chat-guided build tailored to your workflow, preferences, and budget.</div>
            <ul class="mode-features">
                <li>Purpose-driven component selection</li>
                <li>Budget-aware with SST &amp; shipping</li>
                <li>Chat-guided detail gathering</li>
                <li>Save &amp; compare past builds</li>
            </ul>
        </div>""", unsafe_allow_html=True)
        if st.button("Start Personal Build", key="go_personal",
                     use_container_width=True, type="primary"):
            st.session_state["app_mode"] = "personal"
            st.rerun()

    with col2:
        st.markdown("""<div class="mode-card mode-card-business">
            <div class="mode-badge badge-business">BIZ</div>
            <div class="mode-title">Business Fleet</div>
            <div class="mode-desc">Spec and price an entire PC fleet with per-role builds and network advisory.</div>
            <ul class="mode-features">
                <li>Per-role PC specifications</li>
                <li>Network infrastructure advisory</li>
                <li>Fleet cost breakdown</li>
                <li>Excel &amp; PDF exports</li>
            </ul>
        </div>""", unsafe_allow_html=True)
        if st.button("Get Fleet Quote", key="go_business",
                     use_container_width=True, type="primary"):
            st.session_state["app_mode"] = "business"
            st.rerun()


# ── Sidebar header ────────────────────────────────────────────────────────────
def render_sidebar_header() -> None:
    with st.sidebar:
        api_ok = bool(os.getenv("CHUTES_API_KEY"))
        dot_cls = "spek-api-dot" if api_ok else "spek-api-dot spek-api-dot-off"
        api_label = "Chutes / DeepSeek-V3.2" if api_ok else "No API key configured"

        st.markdown(f"""
        <div class="spek-sidebar-logo">
            <div class="spek-logo-mark">
                <span class="spek-logo-bolt">⚡</span><span class="spek-logo-spek">Spek</span><span class="spek-logo-ai">AI</span>
            </div>
            <div class="spek-tagline">Your AI Sales Engineer</div>
            <div class="spek-cyan-rule"></div>
            <div style="margin-top:8px;">
                <span class="{dot_cls}"></span>
                <span class="spek-api-label">{api_label}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        mode = st.session_state.get("app_mode")
        if mode:
            st.divider()
            if st.button("← Home", use_container_width=True, key="sidebar_home"):
                st.session_state["app_mode"] = None
                st.rerun()

        st.divider()


# ── Compare widget (inline, reusable) ─────────────────────────────────────────
def _render_compare_widget(key_prefix: str = "cmp") -> None:
    """Inline compare widget — embeds inside expanders in personal/business sections."""
    catalogue = init_resources()

    c1, c2, c3 = st.columns(3)
    cmp_cat = c1.selectbox(
        "Category", CATEGORIES,
        format_func=lambda c: CATEGORY_DISPLAY[c],
        key=f"{key_prefix}_cat",
    )
    products_in_cat = catalogue.get(cmp_cat, [])

    result_key = f"{key_prefix}_result"

    if len(products_in_cat) >= 2:
        opts  = {p["name"]: p["id"] for p in products_in_cat}
        names = list(opts.keys())

        name_a = c2.selectbox("Part A", names, key=f"{key_prefix}_a")
        opts_b = [n for n in names if n != name_a]
        name_b = c3.selectbox("Part B", opts_b, key=f"{key_prefix}_b")

        if st.button("Compare ↔", use_container_width=True, type="primary",
                     key=f"{key_prefix}_btn"):
            try:
                st.session_state[result_key] = compare_products(opts[name_a], opts[name_b])
            except CompareError as e:
                st.error(str(e))
    else:
        st.caption("Need ≥ 2 products in this category.")
        return

    result = st.session_state.get(result_key)
    if not result:
        return

    a  = result["a"]
    b  = result["b"]
    wc = result["win_counts"]
    ow = result["overall_winner"]
    winner_name = a["name"] if ow == "a" else (b["name"] if ow == "b" else "Tie")

    if ow != "tie":
        st.success(f"Overall winner: **{winner_name}**  ({wc['a']}–{wc['b']} spec wins, {wc['tie']} ties)")
    else:
        st.info(f"Tie  ({wc['a']}–{wc['b']} spec wins, {wc['tie']} ties)")

    col_spec, col_a, col_b = st.columns([3, 4, 4])
    col_spec.markdown("**Spec**")
    col_a.markdown(f"**{a['name']}**  \nRM {(a['price_rm'] or 0):,} @ {a['vendor'] or '—'}")
    col_b.markdown(f"**{b['name']}**  \nRM {(b['price_rm'] or 0):,} @ {b['vendor'] or '—'}")

    for row in result["specs"]:
        sc, sa, sb = st.columns([3, 4, 4])
        sc.write(row["key"].replace("_", " ").title())
        va = str(row["a"]) if row["a"] is not None else "—"
        vb = str(row["b"]) if row["b"] is not None else "—"
        w  = row["winner"]
        winner_badge = '<span class="cmp-winner-badge">Winner</span>'
        sa.markdown(f"{winner_badge} {va}" if w == "a" else va, unsafe_allow_html=True)
        sb.markdown(f"{winner_badge} {vb}" if w == "b" else vb, unsafe_allow_html=True)

    with st.expander("AI Analysis"):
        analysis_key = f"{key_prefix}_analysis_{a['name']}_{b['name']}"
        if analysis_key in st.session_state:
            st.write(st.session_state[analysis_key])
        else:
            if st.button("Generate AI comparison", key=f"{key_prefix}_ai_btn"):
                with st.spinner("Analysing with DeepSeek-V3.2…"):
                    analysis = _compare_llm_analysis(result)
                st.session_state[analysis_key] = analysis
                st.rerun()

    if st.button("Clear comparison", key=f"{key_prefix}_clear"):
        st.session_state.pop(result_key, None)
        st.rerun()


# ── Compare Parts page ────────────────────────────────────────────────────────
def render_compare_page() -> None:
    st.title("Compare Parts")
    st.caption("Side-by-side spec comparison of two products in the same category.")

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
            f"Overall winner: **{winner_name}**  "
            f"({wc['a']}–{wc['b']} spec wins, {wc['tie']} ties)"
        )
    else:
        st.info(f"Tie  ({wc['a']}–{wc['b']} spec wins, {wc['tie']} ties)")

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
        winner_badge = '<span class="cmp-winner-badge">Winner</span>'
        sa.markdown(f"{winner_badge} {va}" if w == "a" else va, unsafe_allow_html=True)
        sb.markdown(f"{winner_badge} {vb}" if w == "b" else vb, unsafe_allow_html=True)

    with st.expander("AI Analysis"):
        analysis_key = f"cmp_analysis_{result['a']['name']}_{result['b']['name']}"
        if analysis_key in st.session_state:
            st.write(st.session_state[analysis_key])
        else:
            if st.button("Generate AI comparison", key="btn_cmp_ai"):
                with st.spinner("Analysing with DeepSeek-V3.2…"):
                    analysis = _compare_llm_analysis(result)
                st.session_state[analysis_key] = analysis
                st.rerun()

    if st.button("Clear comparison", key="close_cmp"):
        del st.session_state["compare_result"]
        st.rerun()


# ── Personal Agent mode ───────────────────────────────────────────────────────
def render_personal_mode() -> None:
    _inject_personal_css()
    st.markdown('<h2 style="font-family:\'Syne\',sans-serif;font-weight:800;color:#F9FAFB;margin-bottom:4px;">Personal Build</h2>', unsafe_allow_html=True)
    st.caption("AI-powered PC recommendation tailored to your needs and budget")

    _render_personal_session_sidebar()

    if st.session_state.get("personal_session_view"):
        _render_personal_session_detail(st.session_state["personal_session_view"])
        return

    if st.session_state.get("personal_compare_mode"):
        _render_saved_builds_compare()
        return

    initial = st.session_state.get("personal_initial_input")
    details = st.session_state.get("personal_gathered_details")

    if initial and not details:
        _render_personal_phase_progress(2)
        _render_personal_details_chat()
        return

    if initial and details and "personal_build" not in st.session_state:
        _render_personal_phase_progress(3)
        merged = _merge_details_into_input(initial, details)
        _run_personal_pipeline(merged)
        return

    if "personal_build" in st.session_state:
        _render_personal_phase_progress(3)
        _render_personal_build_phase()
        return

    _render_personal_phase_progress(1)
    _render_personal_form_phase()


def _render_personal_form_phase() -> None:
    _, col, _ = st.columns([1, 3, 1])
    with col:
        with st.form("personal_form"):
            st.markdown("### What are you building for?")
            purpose = st.selectbox(
                "Primary use case",
                PURPOSE_OPTIONS,
                label_visibility="collapsed",
            )
            st.markdown("&nbsp;", unsafe_allow_html=True)
            st.markdown("**Budget range (RM)**")
            budget_min, budget_max = st.slider(
                "Budget", 2000, 20_000, (3000, 6000), 500,
                label_visibility="collapsed",
            )
            st.markdown(f"<p style='color:#6B7280;font-size:0.85rem;margin-top:-8px;'>RM {budget_min:,} – RM {budget_max:,}</p>", unsafe_allow_html=True)
            st.markdown("&nbsp;", unsafe_allow_html=True)
            submit = st.form_submit_button("Continue →", use_container_width=True, type="primary")

    if submit:
        for k in ("personal_details_chat", "personal_gathered_details", "personal_build",
                   "personal_candidates", "personal_user_input", "personal_refine_chat",
                   "personal_refining", "personal_session_id"):
            st.session_state.pop(k, None)
        st.session_state["personal_initial_input"] = {
            "purposes": [purpose],
            "budget_min": budget_min,
            "budget_max": budget_max,
        }
        st.rerun()


def _render_personal_details_chat() -> None:
    initial  = st.session_state["personal_initial_input"]
    purposes = ", ".join(initial["purposes"])
    bmin     = initial["budget_min"]
    bmax     = initial["budget_max"]
    ctx      = PURPOSE_CONTEXT.get(initial["purposes"][0], "")
    purpose_summary = (
        f"Selected purpose: {purposes}. "
        f"Budget: RM {bmin:,} – RM {bmax:,}. "
        f"Purpose context: {ctx}"
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
        first_q = PURPOSE_FIRST_QUESTION.get(
            initial["purposes"][0],
            "Tell me more about what you'll use this PC for."
        )
        st.session_state["personal_details_chat"] = [{
            "role": "assistant",
            "content": (
                f"You've selected **{purposes}** with a budget of RM {bmin:,}–RM {bmax:,}. "
                f"{first_q}"
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
            with st.spinner("Thinking with DeepSeek-V3.2…"):
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

    render_full_build(build, candidates, prefix="p_", mode="personal")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Compare saved builds", use_container_width=True):
            st.session_state["personal_compare_mode"] = True
            st.rerun()
    with c2:
        if st.button("Start fresh", use_container_width=True):
            for k in ("personal_build", "personal_candidates", "personal_user_input",
                      "personal_initial_input", "personal_details_chat",
                      "personal_gathered_details", "personal_session_id"):
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()
    with st.expander("Compare Parts", expanded=False):
        st.caption("Side-by-side spec comparison of any two components in the catalogue.")
        _render_compare_widget(key_prefix="p_cmp")


def _run_personal_pipeline(user_input: dict) -> None:
    st.markdown('<div class="spek-loading">⚡ SpekAI is building your spec...</div>', unsafe_allow_html=True)
    status = st.status("Running AI pipeline…", expanded=True)
    with status:
        st.write("**Layer 1** — Parsing intent with Gemma 4 31B…")
        try:
            intent = parse_intent(user_input)
        except IntentValidationError as e:
            status.update(label="Intent parsing failed", state="error")
            st.error(str(e))
            return
        st.write(f"OK: `{', '.join(intent.get('use_cases', []))}` · tier: `{intent.get('budget_tier', '')}`")

        st.write("**Layer 2** — Semantic catalogue search…")
        candidates = search_all_categories(intent, top_k=3)
        st.write(f"OK: {sum(len(v) for v in candidates.values())} candidates")

        st.write("**Layer 3** — Generating compatible build…")
        _l3_ph = st.empty()

        def _l3_status(chars: int):
            _l3_ph.caption(f"⚡ {chars} chars received…")

        try:
            build = generate_build(intent, candidates, status_fn=_l3_status)
        except BuildGenerationError as e:
            status.update(label="Build generation failed", state="error")
            st.error(str(e))
            return
        _l3_ph.empty()

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
        f"Warning: Over budget by **RM {overage:,.2f}** — "
        f"total RM {grand_total:,.2f} vs budget RM {budget_rm:,.2f} (incl. SST & shipping)"
    )
    with st.expander("Adjust & Retry to fit budget"):
        new_min, new_max = st.slider(
            "Budget range (RM)", 2000, 20_000,
            (int(user_input.get("budget_min_rm", budget_rm * 0.8)),
             int(max(grand_total, budget_rm) + 1000)), 500,
            key="retry_budget",
        )
        current_purpose = user_input.get("purposes", PURPOSE_OPTIONS)[0] if user_input.get("purposes") else PURPOSE_OPTIONS[0]
        new_purpose = st.selectbox(
            "Primary use case", PURPOSE_OPTIONS,
            index=PURPOSE_OPTIONS.index(current_purpose) if current_purpose in PURPOSE_OPTIONS else 0,
            key="retry_purposes",
        )
        if st.button("Rebuild with adjusted parameters", type="primary", key="retry_rebuild"):
            new_input = {**user_input, "budget_rm": new_max, "budget_min_rm": new_min,
                         "purposes": [new_purpose]}
            for k in ("personal_refine_chat", "personal_refining"):
                st.session_state.pop(k, None)
            _run_personal_pipeline(new_input)




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
                    btn1, btn2 = st.columns(2)
                    with btn1:
                        if st.button("View", key=f"pview_{s['id']}",
                                     use_container_width=True):
                            st.session_state["personal_session_view"] = s["id"]
                            st.rerun()
                    with btn2:
                        if st.button("Delete", key=f"pdel_{s['id']}",
                                     use_container_width=True):
                            delete_session(s["id"])
                            st.rerun()
        st.divider()
        st.markdown('<div class="spek-sidebar-footer">Powered by Chutes AI · DeepSeek V3.2</div>', unsafe_allow_html=True)


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
        render_full_build(build, candidates, prefix=f"hist_{session_id[-6:]}_", mode="personal")
    else:
        st.caption("Full build data not stored for this session.")


def _render_saved_builds_compare() -> None:
    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Back"):
            st.session_state.pop("personal_compare_mode", None)
            st.rerun()

    st.subheader("Compare Saved Builds")
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


def _render_business_step_progress(step: int) -> None:
    labels = ["Company", "Roles", "Office", "Generate"]
    parts = []
    for i, label in enumerate(labels):
        if i < step:
            dot_cls, lbl_cls, content = "biz-step-dot-done", "biz-step-lbl", "&#10003;"
            line_cls = "biz-step-line-done"
        elif i == step:
            dot_cls, lbl_cls, content = "biz-step-dot-active", "biz-step-lbl", str(i + 1)
            line_cls = "biz-step-line-todo"
        else:
            dot_cls, lbl_cls, content = "biz-step-dot-todo", "biz-step-lbl-todo", str(i + 1)
            line_cls = "biz-step-line-todo"
        parts.append(
            f'<div class="biz-step-wrap">'
            f'<div class="biz-step-dot {dot_cls}">{content}</div>'
            f'<div class="biz-step-content">'
            f'<div class="biz-step-num">Step {i + 1}</div>'
            f'<div class="{lbl_cls}">{label}</div>'
            f'</div></div>'
        )
        if i < len(labels) - 1:
            parts.append(f'<div class="biz-step-line {line_cls}"></div>')
    st.markdown(f'<div class="biz-stepper">{"".join(parts)}</div>', unsafe_allow_html=True)


# ── Business Agent mode (hybrid form → chat → form) ──────────────────────────
def render_business_mode() -> None:
    _inject_business_css()
    st.markdown('<h2 style="font-family:\'Syne\',sans-serif;font-weight:800;color:#F9FAFB;margin-bottom:4px;">Business Fleet</h2>', unsafe_allow_html=True)
    st.caption("Spec and price an entire PC fleet — per-role builds, network advisory, and export-ready reports")

    _render_session_history_sidebar()

    if st.session_state.get("viewing_session"):
        _render_session_detail(st.session_state["viewing_session"])
        return

    if "business_result" in st.session_state:
        render_business_result(st.session_state["business_result"])
        st.divider()
        if st.button("Start a new quote"):
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
        else:
            for s in reversed(sessions[-8:]):
                ts      = (s.get("created_at") or "")[:16].replace("T", " ")
                company = s.get("company_name") or "Unknown"
                pcs     = s.get("total_pcs") or 0
                total   = s.get("total_rm")  or 0.0
                with st.expander(f"{company}"):
                    st.markdown(f"**{pcs} PCs** | RM {total:,.0f}")
                    st.caption(f"{ts}  ·  `{s['id'][-8:]}`")
                    btn1, btn2 = st.columns(2)
                    with btn1:
                        if st.button("View", key=f"bview_{s['id']}",
                                     use_container_width=True):
                            st.session_state["viewing_session"] = s["id"]
                            st.rerun()
                    with btn2:
                        if st.button("Delete", key=f"bdel_{s['id']}",
                                     use_container_width=True):
                            delete_session(s["id"])
                            st.rerun()
        st.divider()
        st.markdown('<div class="spek-sidebar-footer">Powered by Chutes AI · DeepSeek V3.2</div>', unsafe_allow_html=True)


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

    _render_business_step_progress(step)
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
            with st.spinner("Thinking with DeepSeek-V3.2…"):
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
    ex = st.session_state.get("biz_office", {})
    include_net_default = ex.get("include_network", total_pcs >= 5)
    with st.form("biz_office_form"):
        include_network = st.checkbox(
            "Include network infrastructure advisory",
            value=include_net_default,
            help="Generates switch, router, WiFi AP, NAS, and cabling recommendations sized to your fleet.",
        )
        st.caption("Office layout helps size WiFi APs and switch count. Leave blank if not relevant.")
        floor_area   = st.number_input("Floor area (sqm)", min_value=0,
                                        value=int(ex.get("floor_area_sqm") or 0),
                                        help="Leave 0 if unknown — defaults to 1 AP per floor")
        total_floors = st.number_input("Number of floors", min_value=1,
                                        value=int(ex.get("total_floors") or 1))
        has_remote   = st.checkbox("Has remote workers",
                                    value=bool(ex.get("has_remote_workers", False)),
                                    help="Ensures a VPN-capable router is recommended")
        submit       = st.form_submit_button("Continue →", type="primary",
                                              use_container_width=True)
    if submit:
        st.session_state["biz_office"] = {
            "include_network":    include_network,
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
        net_label = "Yes" if office.get("include_network", True) else "No"
        st.markdown(f"- Network advisory: {net_label}")

    st.divider()
    if st.button(f"Generate Fleet Quote ({total_pcs} PCs)", type="primary",
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
            _rb_ph = st.empty()

            def _rb_status(chars: int):
                _rb_ph.caption(f"⚡ {chars} chars received…")

            build      = generate_build(intent, candidates, status_fn=_rb_status)
            _rb_ph.empty()
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

    if network:
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
    else:
        m1, m2 = st.columns(2)
        m1.metric("Total PCs",       result["total_pcs"])
        m2.metric("PC Fleet Budget", f"RM {result['total_cost']:,.0f}")

    # ── Per-role builds ───────────────────────────────────────────────────────
    st.subheader("Per-Role Builds")

    for role, data in role_results.items():
        count = data["count"]

        if "error" in data:
            with st.expander(f"Error: {role.title()} x{count} — Generation failed"):
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
                    st.error(f"Warning: {issue}")

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
                render_bom_item(item, build, candidates, prefix=f"{role}_", mode="business")

            if build.get("budget_exceeded") or any(
                "OVER BUDGET" in str(w) for w in build.get("warnings", [])
            ):
                with st.expander(f"Rebuild {role.title()} with adjusted parameters"):
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

    if network:
        render_network_section(network)

    st.divider()
    with st.expander("Compare Parts", expanded=False):
        st.caption("Side-by-side spec comparison of any two components in the catalogue.")
        _render_compare_widget(key_prefix="b_cmp")

    _render_export_section(result)


def _render_export_section(result: dict) -> None:
    st.divider()
    st.subheader("Export Reports")
    company_slug = result["company_profile"].get("name", "fleet").replace(" ", "_")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download Financial Report (Excel)",
            data=generate_financial_excel(result),
            file_name=f"financial_report_{company_slug}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.caption("BOM + cost breakdown — Summary, per-role, and Network sheets.")
    with col2:
        st.download_button(
            "Download RFP Document (PDF)",
            data=generate_rfp_pdf(result),
            file_name=f"rfp_{company_slug}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        st.caption("Vendor-facing procurement document with 8 sections.")


def render_network_section(network: dict) -> None:
    """Network infrastructure as its own BOM-style section + separate budget total."""
    st.subheader("Network Infrastructure")
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
    _inject_global_css()
    init_resources()
    render_sidebar_header()

    mode = st.session_state.get("app_mode")
    if mode == "personal":
        render_personal_mode()
    elif mode == "business":
        render_business_mode()
    elif mode == "compare":
        render_compare_page()
    else:
        render_landing_page()


if __name__ == "__main__":
    main()

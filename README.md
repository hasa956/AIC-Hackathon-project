# PC Agent — AI Marathon 2026
**Problem Statement 1: Autonomous Sales Engineer**

AI-powered PC recommendation system for both personal buyers and business fleet procurement. Built with a 3-layer LLM pipeline, semantic catalogue search, and a Streamlit dark-mode dashboard.

---

## Overview

Two distinct modes:

- **Personal Build** — Chat-guided flow: user picks purpose + budget, answers a few targeted questions, gets a full tailored BOM
- **Business Fleet** — Role-based fleet quoting: input company size and role breakdown, get per-role PC specs, network advisory, and exportable reports (Excel + PDF)

---

## Architecture

```
User Input
    │
    ▼
Layer 1 — Intent Parser          (Chutes / Gemma 4 31B — fast model)
    │  Parses purpose, budget, use-cases into structured intent JSON
    ▼
Layer 2 — Catalogue Search       (Sentence Transformers / cosine similarity)
    │  Semantic search across component catalogue, returns candidates per category
    ▼
Layer 3 — Build Reasoner         (Chutes / Gemma 4 31B — streamed)
    │  Picks optimal combination, validates compatibility, enriches with vendor pricing
    ▼
Streamlit Dashboard              (dark-mode UI, card-based BOM, streaming explanations)
```

### Key modules

| File | Role |
|------|------|
| `agent/config.py` | OpenAI-compatible client config for Chutes + Morpheus |
| `agent/intent_parser.py` | Layer 1 — structured intent extraction (Gemma 4 31B) |
| `agent/catalogue.py` | Component catalogue loader + embedding-based search |
| `agent/reasoner.py` | Layer 3 — BOM generation + compatibility validation (DeepSeek-V3.2) |
| `agent/explainer.py` | On-demand plain-English component explanation (DeepSeek-V3.2) |
| `agent/personal_chat.py` | Details chat protocol for personal mode |
| `agent/business_chat.py` | Role-spec extraction chat for business mode |
| `agent/business.py` | Business quote orchestrator — per-role builds + fleet aggregation |
| `agent/network.py` | Network infrastructure advisory for business fleets |
| `agent/compare.py` | Side-by-side component comparison |
| `agent/reports.py` | Excel (openpyxl) + PDF (reportlab) report generation |
| `agent/compatibility.py` | Pure-Python compatibility validation rules |
| `app.py` | Streamlit dashboard — routing, UI, session state |

---

## Personal Mode Flow

```
1. Form Phase
   └─ Select purpose (Work / Gaming / Content Creation / Dev / General)
   └─ Set budget range (slider, RM 2,000–20,000)

2. Details Chat Phase
   └─ Purpose-specific first question (no redundant "what's your focus?" after Gaming was picked)
   └─ 4 targeted questions: workload specifics, owned parts, software/targets, build priorities
   └─ Chat ends when details are complete — triggers build automatically

3. Build Phase
   └─ Runs full 3-layer pipeline
   └─ Displays card-based BOM with vendor pricing
   └─ Budget badge: RM total vs budget (green = under, red = over)
   └─ Expand any component for a plain-English AI explanation
   └─ Save build to session history
```

---

## Business Mode Flow

```
1. Chat Phase
   └─ Collects: company name, industry, headcount per role, budget per seat, constraints
   └─ Extracts structured spec via <<SPEC>>...<<END>> protocol

2. Quote Generation
   └─ Per-role: runs full 3-layer pipeline with role-appropriate defaults
   └─ Aggregates fleet cost
   └─ Network advisory optional (switches, APs, firewall, cabling estimate)

3. Reports
   └─ Excel export: per-role BOM + cost breakdown
   └─ PDF RFP document
   └─ Session persistence (sessions.json)
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/hasa956/AIC-Hackathon-project.git
cd AIC-Hackathon-project
pip install -r requirements.txt
```

### 2. Environment variables

Create `.env` in the project root:

```env
# Chutes (primary — required)
CHUTES_API_KEY=your_chutes_api_key
CHUTES_BASE_URL=https://llm.chutes.ai/v1
CHUTES_MODEL=deepseek-ai/DeepSeek-V3.2
CHUTES_FAST_MODEL=google/gemma-4-31B-turbo-TEE

# Morpheus (fallback — optional)
MORPHEUS_API_KEY=your_morpheus_api_key
MORPHEUS_BASE_URL=https://api.mor.org/api/v1
MORPHEUS_MODEL=llama-3.3-70b
```

> **Get a Chutes API key:** [https://chutes.ai](https://chutes.ai)

### 3. Run

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| UI | Streamlit 1.57 (forced dark mode via `.streamlit/config.toml`) |
| LLM — fast | Chutes API / Gemma 4 31B turbo (intent parsing, build generation) |
| LLM — reasoning | Chutes API / DeepSeek-V3.2 (component explanations) |
| Semantic search | `sentence-transformers` — cosine similarity over component embeddings |
| Reports | `openpyxl` (Excel), `reportlab` (PDF) |
| Compatibility | Pure Python rules engine (`agent/compatibility.py`) |
| Session storage | Local `sessions.json` |

---

## Features

- **Dark mode** — forced via `.streamlit/config.toml`, consistent across all pages
- **Purpose-aware chat** — 4 targeted questions, first adapts to selected purpose (Gaming != Office)
- **Streamed build generation** — Layer 3 streams tokens with live progress counter
- **Budget enforcement** — SST + shipping included in total, clear over/under badge
- **Component explanations** — click any BOM item to get a plain-English AI explanation
- **Compatibility validation** — socket/TDP/RAM slot checks with auto-retry on conflicts
- **Fleet procurement** — multi-role builds, optional network advisory, Excel + PDF export
- **Part comparison** — side-by-side spec comparison for any two catalogue items
- **Session history** — save, reload, and delete past builds

---

## Project Structure

```
AIC-Hackathon-project/
├── app.py                    # Streamlit dashboard
├── requirements.txt
├── sessions.json             # Business session persistence
├── .env                      # API keys (not committed)
├── .streamlit/
│   └── config.toml           # Dark mode theme
└── agent/
    ├── __init__.py
    ├── config.py             # LLM client config
    ├── intent_parser.py      # Layer 1
    ├── catalogue.py          # Layer 2 — semantic search
    ├── reasoner.py           # Layer 3 — build generation
    ├── explainer.py          # Component explanation
    ├── personal_chat.py      # Personal details chat
    ├── business_chat.py      # Business spec chat
    ├── business.py           # Business orchestrator
    ├── network.py            # Network advisory
    ├── compare.py            # Part comparison
    ├── reports.py            # Excel + PDF export
    ├── compatibility.py      # Compatibility rules
    ├── tools.py              # Cost calculation utilities
    ├── diagnostics.py        # Candidate diagnostics
    └── prompts.py            # All LLM system prompts
```

---

## Team

Built for **AI Marathon 2026** — Problem Statement 1: Autonomous Sales Engineer

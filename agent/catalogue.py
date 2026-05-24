"""
Layer 2 — Catalogue layer.

Responsibilities:
  1. Load all 10 category JSON files into memory.
  2. Embed every product's `chunk_text` once at startup, cache to disk as .npy.
  3. Semantic search: for each required category, return top-K candidates
     ranked by cosine similarity against an intent-derived query.

No API call at query time. Embeddings use local sentence-transformers (free).

Entry points:
  - load_catalogue(data_dir)
  - build_or_load_embeddings(catalogue, cache_dir)
  - search_category(category, intent, top_k=3)
  - search_all_categories(intent, top_k=3)
"""

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


# All build categories — must match the JSON filenames in data/
CATEGORIES = [
    "cpu", "motherboard", "ram", "gpu", "storage",
    "psu", "cooler", "case", "case_fans", "thermal_paste",
]

# Categories where the user's aesthetic preference matters
VISUAL_CATEGORIES = {"case", "case_fans", "cooler", "ram"}

# Module-level caches so we only load once per process
_embedder: SentenceTransformer | None = None
_catalogue: dict | None = None
_embeddings: dict | None = None


# ── Internal helpers ─────────────────────────────────────────────────

def _get_embedder() -> SentenceTransformer:
    """Lazy-load the embedding model on first call."""
    global _embedder
    if _embedder is None:
        print("Loading embedding model (all-MiniLM-L6-v2)...")
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Pure-numpy cosine similarity. Range [-1, 1]."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _build_query_for_category(category: str, intent: dict) -> str:
    """Construct a natural-language search query for a category from intent."""
    parts = [category]

    use_cases = intent.get("use_cases", [])
    if use_cases:
        parts.append("for " + " ".join(uc.replace("_", " ") for uc in use_cases))

    tier = intent.get("budget_tier")
    if tier:
        parts.append(tier.replace("_", " "))

    # Style only matters for visible categories
    if category in VISUAL_CATEGORIES:
        style = intent.get("style_profile", {})
        if style.get("vibe"):
            parts.append(style["vibe"])
        if style.get("colour_palette"):
            parts.append(" ".join(style["colour_palette"]))

    # Noise only matters for fans and coolers
    if category in {"cooler", "case_fans"}:
        noise = intent.get("noise_preference")
        if noise:
            parts.append(f"{noise} noise")

    return " ".join(parts)


def _passes_style_filter(product: dict, intent: dict) -> bool:
    """Hard filter: for visible categories, exclude RGB products if user is stealth/minimal."""
    category = product.get("category")
    if category not in VISUAL_CATEGORIES:
        return True

    style = intent.get("style_profile", {})
    rgb_pref = style.get("rgb_preference", False)
    style_tags = [t.lower() for t in product.get("style_tags", [])]

    if rgb_pref is False and "rgb" in style_tags:
        return False
    return True


# ── Public API ───────────────────────────────────────────────────────

def load_catalogue(data_dir: str = "data") -> dict:
    """
    Load every category JSON from data_dir into a dict.

    Returns:
        dict[category_name, list[product_dict]]
    """
    global _catalogue
    if _catalogue is not None:
        return _catalogue

    catalogue = {}
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(
            f"Data directory '{data_dir}' not found. "
            f"Copy your catalogue JSON files into HACKATHON/data/."
        )

    for category in CATEGORIES:
        path = data_path / f"{category}.json"
        if not path.exists():
            print(f"WARNING: {path} missing — category skipped.")
            catalogue[category] = []
            continue
        with open(path, "r", encoding="utf-8") as fp:
            catalogue[category] = json.load(fp)

    total = sum(len(v) for v in catalogue.values())
    print(f"Loaded {total} products across {len(catalogue)} categories.")
    _catalogue = catalogue
    return catalogue


def build_or_load_embeddings(catalogue: dict, cache_dir: str = "cache") -> dict:
    """
    Embed every product's chunk_text. Cache the result on disk so we only pay
    the cost once per machine.

    Returns:
        dict[product_id, np.ndarray]
    """
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    cache_path = Path(cache_dir) / "embeddings.npy"

    if cache_path.exists():
        _embeddings = np.load(cache_path, allow_pickle=True).item()
        print(f"Loaded {len(_embeddings)} cached embeddings from {cache_path}")
        return _embeddings

    print("Building embeddings (first run only)...")
    Path(cache_dir).mkdir(exist_ok=True)
    embedder = _get_embedder()

    all_chunks, all_ids = [], []
    for products in catalogue.values():
        for p in products:
            text = p.get("chunk_text") or f"{p.get('name', '')} {p.get('category', '')}"
            all_chunks.append(text)
            all_ids.append(p["id"])

    vectors = embedder.encode(all_chunks, show_progress_bar=True, convert_to_numpy=True)
    _embeddings = {pid: vec for pid, vec in zip(all_ids, vectors)}

    np.save(cache_path, _embeddings)
    print(f"Cached {len(_embeddings)} embeddings to {cache_path}")
    return _embeddings


def search_category(category: str, intent: dict, top_k: int = 3) -> list[dict]:
    """
    Return top-K product candidates for one category, ranked by semantic similarity.

    Hard filters applied first:
      - in_stock must be True
      - style filter (no RGB for stealth/minimal users) on visible categories
    """
    catalogue = load_catalogue()
    embeddings = build_or_load_embeddings(catalogue)

    products = catalogue.get(category, [])
    if not products:
        return []

    candidates = [
        p for p in products
        if p.get("in_stock", True) and _passes_style_filter(p, intent)
    ]
    if not candidates:
        return []

    query = _build_query_for_category(category, intent)
    qvec = _get_embedder().encode(query, convert_to_numpy=True)

    scored = []
    for p in candidates:
        pvec = embeddings.get(p["id"])
        if pvec is None:
            continue
        scored.append((_cosine_sim(qvec, pvec), p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 4), **p} for s, p in scored[:top_k]]


def search_all_categories(intent: dict, top_k: int = 3) -> dict:
    """
    Run search_category for every required category in the intent.

    Returns:
        dict[category, list[product_with_score]]
    """
    return {
        category: search_category(category, intent, top_k=top_k)
        for category in intent.get("required_categories", [])
    }
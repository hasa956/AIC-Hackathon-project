"""
Centralized API client configuration.

Both Chutes and Morpheus are OpenAI-compatible. Only base_url and model differ.

Usage:
    from agent.config import chutes, CHUTES_MODEL
    response = chutes.chat.completions.create(model=CHUTES_MODEL, ...)
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


# ── Chutes (Layer 1 intent parser + Layer 3 reasoning) ────────────────
chutes = OpenAI(
    api_key=os.getenv("CHUTES_API_KEY"),
    base_url=os.getenv("CHUTES_BASE_URL", "https://llm.chutes.ai/v1"),
)
CHUTES_MODEL = os.getenv("CHUTES_MODEL", "deepseek-ai/DeepSeek-V3.2")
CHUTES_FAST_MODEL = os.getenv("CHUTES_FAST_MODEL", "google/gemma-4-31B-turbo-TEE") 

# ── Morpheus (Explain feature + Network advisory) ─────────────────────
morpheus = OpenAI(
    api_key=os.getenv("MORPHEUS_API_KEY"),
    base_url=os.getenv("MORPHEUS_BASE_URL", "https://api.mor.org/api/v1"),
)
MORPHEUS_MODEL = os.getenv("MORPHEUS_MODEL", "llama-3.3-70b")
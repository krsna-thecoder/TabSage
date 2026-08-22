"""List the models a Gemini API key can access, grouped by capability.

Usage (from backend/, venv active):
    python scripts/list_models.py

Key is read from TABSAGE_TEST_KEY env var or a hidden prompt. Never stored.
Use the output to pick valid embedding / generation model names for
providers/gemini.py.
"""
from __future__ import annotations

import getpass
import os

from google import genai


def main() -> int:
    key = os.environ.get("TABSAGE_TEST_KEY") or getpass.getpass(
        "Paste your Gemini API key (hidden input): "
    )
    client = genai.Client(api_key=key)

    embed_models: list[str] = []
    gen_models: list[str] = []
    for m in client.models.list():
        actions = list(m.supported_actions or [])
        if "embedContent" in actions:
            embed_models.append(m.name)
        if "generateContent" in actions:
            gen_models.append(m.name)

    print("\n=== Models supporting embedContent (embeddings) ===")
    for n in embed_models:
        print("  ", n)
    print("\n=== Models supporting generateContent (chat/answers) ===")
    for n in gen_models:
        print("  ", n)

    print("\nSuggested constants for providers/gemini.py:")
    if embed_models:
        print("  GEMINI_EMBEDDING_MODEL =", repr(embed_models[0].replace("models/", "")))
    # Prefer a 'flash' generation model (free-tier friendly) if present.
    flash = next((n for n in gen_models if "flash" in n and "lite" not in n), None)
    chosen_gen = flash or (gen_models[0] if gen_models else None)
    if chosen_gen:
        print("  GEMINI_GENERATION_MODEL =", repr(chosen_gen.replace("models/", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

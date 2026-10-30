"""Measure raw provider latency, with the browser/extension out of the loop.

Usage (from backend/, venv active):
    python scripts/probe_latency.py            # gemini (default)
    python scripts/probe_latency.py openai

Key is read from the TABSAGE_TEST_KEY env var, or a hidden prompt. It is used
transiently and never stored. This times the embedding calls that dominate
ingest latency, so we can tell whether the slowness is the provider endpoint
itself (vs the browser or the network between the extension and the backend).
"""
from __future__ import annotations

import getpass
import os
import sys
import time

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from providers import ProviderError, get_provider  # noqa: E402
from schemas import Provider  # noqa: E402


def main() -> int:
    name = sys.argv[1].lower() if len(sys.argv) > 1 else "gemini"
    try:
        provider = Provider(name)
    except ValueError:
        print(f"Unknown provider {name!r}. Use 'gemini' or 'openai'.")
        return 2

    key = os.environ.get("TABSAGE_TEST_KEY") or getpass.getpass(
        f"Paste your {name} API key (hidden input): "
    )

    try:
        p = get_provider(provider, key)
    except ProviderError as err:
        print(f"Provider build failed: {type(err).__name__}: {err}")
        return 1

    print(f"provider:           {p}")
    print(f"embedding_model_id: {p.embedding_model_id}")

    sample = (
        "Retrieval-augmented generation retrieves relevant passages from a "
        "knowledge base and supplies them to a language model as context so the "
        "answer stays grounded in the source material. "
    )

    # Warm-up + a few batch sizes that mirror a real page ingest.
    for n in (1, 10, 24):
        texts = [f"{sample} (chunk {i})" for i in range(n)]
        try:
            t0 = time.perf_counter()
            vectors = p.embed(texts)
            dt = time.perf_counter() - t0
        except ProviderError as err:
            print(f"\nembed({n}) FAILED: {type(err).__name__}: {err}")
            return 1
        dim = len(vectors[0]) if vectors else 0
        print(f"embed({n:>2} texts): {dt:6.2f}s   (dim={dim})")

    print("\nDone. The embed(24) time is close to what one real page costs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Manual Phase 2 provider check.

Usage (run from the backend/ folder, venv active):
    python scripts/try_provider.py            # defaults to gemini
    python scripts/try_provider.py gemini
    python scripts/try_provider.py openai

The API key is read from the TABSAGE_TEST_KEY env var if set, otherwise via a
hidden prompt (getpass). The key is used transiently and never written anywhere.
"""
from __future__ import annotations

import getpass
import os
import sys

# Make the backend package root importable when run as a script.
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
        print("provider:           ", p)
        print("embedding_model_id: ", p.embedding_model_id)

        texts = [
            "TabSage turns selected study tabs into a source-grounded knowledge base.",
            "Retrieval-augmented generation retrieves passages before answering.",
        ]
        vectors = p.embed(texts)
        dim = len(vectors[0]) if vectors else 0
        print(f"embed():             {len(vectors)} vectors, dim={dim}")

        answer = p.generate(
            "In one sentence, what is retrieval-augmented generation (RAG)?"
        )
        print("generate():         ", answer.strip()[:300])
        print("\nOK — provider works end to end.")
        return 0
    except ProviderError as err:
        # Friendly, normalized error (never contains the key).
        print(f"\nProvider error: {type(err).__name__}: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

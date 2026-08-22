# TabSage

> Study-from-your-tabs RAG chatbot. A publishable Chrome extension (Manifest V3) +
> a Python/FastAPI RAG backend that is **stateless about secrets**.

TabSage turns the study tabs you explicitly select (GeeksforGeeks, freeCodeCamp,
W3Schools, etc.) into a temporary, source-grounded knowledge base. Ask a question,
get an answer built **only** from those tabs — with citations.

## Core design

- **BYOK (Bring Your Own Key):** each user supplies their own provider key
  (Google **Gemini** free tier by default, OpenAI optional). The key lives only in
  the user's browser (`chrome.storage.local`), transits the backend in memory per
  request, and is **never** stored, logged, or persisted server-side.
- **Two deploy targets, one repo:**
  - `extension/` → zipped and submitted to the Chrome Web Store.
  - `backend/`   → deployed separately as an HTTPS API (Chrome can't run Python).

## Repo layout

```text
TabSage/
├── extension/          # Manifest V3 extension (vanilla JS) — Web Store target
├── backend/            # FastAPI RAG API — deployed separately over HTTPS
│   ├── providers/      # Provider interface: embed() / generate() (Gemini, OpenAI)
│   ├── rag/            # clean → chunk → store → chat
│   └── tests/
├── DOCUMENTATION.md    # Full project documentation
└── CHECKLIST.md        # Master build checklist
```

## Backend — local dev quickstart

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows (PowerShell: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
uvicorn main:app --reload      # http://localhost:8000/docs
```

> The backend holds **no provider key**. During dev you pass your own Gemini key
> from the extension settings (or the `X-Provider-Key` header in Swagger), exactly
> as a real user would.

## Status

Phase 0 — platform & environment setup.

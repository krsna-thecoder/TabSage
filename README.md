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

## Install

> **You need your own free Google Gemini API key** (or an OpenAI key). Get a free
> Gemini key at <https://aistudio.google.com/app/apikey>. Your key is stored only
> in your browser and is never stored on TabSage's servers — see the
> [privacy policy](https://tabsage.duckdns.org/privacy).

### Microsoft Edge (store)

Install from the Edge Add-ons listing: _&lt;link once published&gt;_ → **Get**,
then open the TabSage side panel from the toolbar.

### Chrome or Edge (load unpacked)

Works today, no store needed:

1. Download this repo (**Code → Download ZIP**, or `git clone`) and unzip it.
2. Open your extensions page: `chrome://extensions` (Chrome) or
   `edge://extensions` (Edge).
3. Turn on **Developer mode**.
4. Click **Load unpacked** and select the **`extension/`** folder.
5. Click the TabSage toolbar icon to open the side panel.

### First run

1. Open **Settings** (gear icon), paste your provider key, click **Save**.
2. Open a study page (a docs page or tutorial), then click **+ (Add this tab)**.
3. Ask a question — you get an answer built only from your added tabs, with
   citations, streamed as it's written.

> The extension talks to the hosted TabSage backend over HTTPS. To run your own
> backend, deploy `backend/` (see the backend quickstart above) and set the
> `prod` URL in `extension/config.js`.

## Status

v1.0.0 — backend live over HTTPS (FastAPI on AWS); extension packaged for Edge
Add-ons / Chrome Web Store. BYOK, streaming answers, source-grounded with
citations.

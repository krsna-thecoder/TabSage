# ✓ TabSage — Master Build Checklist

> **Project:** TabSage — Study-from-your-tabs RAG Chatbot, **publishable on the Chrome Web Store**
> **Stack:** Chrome Extension (Manifest V3, vanilla JS) + Python/FastAPI RAG API (stateless about secrets)
> **Model access:** **Bring Your Own Key (BYOK).** Each user pastes their own provider key.
> **Default provider:** Google **Gemini** (real free tier). **Optional:** OpenAI (`gpt-4o-mini` + `text-embedding-3-small`).
> **Why BYOK:** developer pays **$0 for AI/model usage at any scale**; each user runs on their **own free quota**; the key
> lives only in the user's browser and is **never stored on the backend** (it does transit the backend in memory per request).
> ⚠️ BYOK removes the *AI* bill only — the backend host + any server-side storage still cost money and scale with usage.
> **Publishing model:** one Git repo → `extension/` is zipped and submitted to the Store; `backend/` is
> deployed separately over HTTPS. Chrome can't run Python, so only the extension goes to the Store.
> **Goal:** Answer study questions **only from user-selected tabs** (RAG), with citations, as a real product.

---

## 🏁 Phase 0 — Platform & Environment Setup
### 0a — Provider key (for your own dev/testing)
- [ ] Create a **Google AI Studio / Gemini API key** (free tier) — this is TabSage's default provider
- [ ] (Optional) Create an **OpenAI key** if you want to test the OpenAI provider too
- [ ] ⚠️ These are **your** dev keys — in production, each user brings their own (BYOK), so you host no key
### 0b — Local tooling
- [ ] Install **Python 3.10+**, **Google Chrome**, a code editor (VS Code)
- [ ] Install **git** and **Docker** (Docker needed for production deploy)
### 0c — Repo skeleton (one repo, two deploy targets)
- [ ] Create repo `tabsage/` with `backend/` and `extension/` subfolders
- [ ] `cd backend` → `python -m venv .venv` → activate it
- [ ] `.gitignore` ignores `.venv/`, `.env`, `__pycache__/`, `chroma_db/`, build/zip artifacts
- [ ] Starter `README.md`; keep `DOCUMENTATION.md` in sync
### 0d — Config (note: NO provider key lives in the backend)
- [ ] `backend/.env.example` + `backend/.env` for **non-secret settings only** (allowed origins, env name)
- [ ] For local testing, you may pass your dev key from the extension settings just like a real user would
- [ ] `requirements.txt` — fastapi, uvicorn, gunicorn, google-generativeai, openai (optional), langchain, chromadb (dev), pydantic, python-dotenv
- [ ] `pip install -r requirements.txt` and confirm no errors

---

## 🧱 Phase 1 — Backend Foundations (FastAPI, stateless about secrets)
- [ ] `config.py` — non-secret settings only (⚠️ do **not** load a provider key here)
- [ ] `main.py` — FastAPI app + `uvicorn` entry
- [ ] `GET /health` returns `{status:"ok"}` (deploy health check; no secrets)
- [ ] Enable **CORS**, restricted (not `*`) — allowlist the extension origin `chrome-extension://<extension-id>` (+ `http://localhost` in dev)
- [ ] Swagger loads at `http://localhost:8000/docs`
- [ ] **Pydantic models**: `IngestRequest`, `ChatRequest`, `ChatResponse` (include `session_id` + `provider`)
- [ ] Read the **user's key from a request header** (e.g. `X-Provider-Key`), never from server config

---

## 🔌 Phase 2 — Provider Abstraction (the BYOK core)
- [ ] `providers/base.py` — interface with `embed(texts)` + `generate(prompt)`
- [ ] `providers/gemini.py` — Gemini implementation (default)
- [ ] `providers/openai.py` — OpenAI implementation (optional)
- [ ] Factory: pick implementation from the request's `provider` field
- [ ] ⚠️ Use the passed-in key **transiently** — never write it to disk, DB, or logs
- [ ] ⚠️ **Embedding consistency**: a session's index must be queried with the same model that built it;
      switching provider requires a session reset (document this)
  - [ ] Store the **embedding model name/version** in each chunk's metadata; verify it at query time and refuse/auto-reset on mismatch
- [ ] ⚠️ **Provider rate limits**: batch embedding calls + backoff/retry (ingesting one page = many embed calls → free-tier RPM limits); surface a "rate limited, retrying" state

---

## 📥 Phase 3 — INGEST: Clean & Chunk
- [ ] `clean.py` — strip nav/boilerplate/whitespace from raw page text
- [ ] `chunker.py` — LangChain `RecursiveCharacterTextSplitter` (~800 chars, ~150 overlap; note why)
- [ ] Attach metadata per chunk: `session_id`, `tab_id`, `title`, `url`
- [ ] Enforce **payload limits**: max page size, max chunks, max sources
- [ ] Edge cases: empty / tiny / huge page

---

## 🧮 Phase 4 — EMBED & STORE
- [ ] Embeddings go **through the provider interface** (Gemini default) using the user's key
- [ ] `store.py` behind an interface; dev impl = **Chroma** (local)
- [ ] Scope every read/write by `session_id` (+ `user_id` later) for isolation
- [ ] Dedupe re-ingested tabs (by `tab_id`/`url`) or reset the session first
- [ ] ⚠️ **Default = ephemeral short-TTL session store** (in-memory/Chroma with auto-expiry). Persisting scraped page content server-side is an **opt-in** only — less cost, less privacy risk. Phase 9 adds a persistent per-user store *only if* persistence is explicitly required.

---

## 🔍 Phase 5 — RETRIEVE & GENERATE
- [ ] `chat.py` — embed question (user's key) → retrieve **top-K** chunks for the session
- [ ] RAG prompt: "answer ONLY from this context; if absent, say you don't know" + chunks + question
- [ ] Generate via the provider interface; return `{ answer, citations }` (tab title/url per chunk)
- [ ] Honest **"not in your tabs"** handling (no hallucination)
- [ ] Robust **provider error handling** (bad/expired key, rate limit, timeout) → friendly, specific message
- [ ] **Milestone:** run the whole loop as a plain script (paste key + text → ask → grounded answer)

---

## 🌐 Phase 6 — API Endpoints
- [ ] `POST /ingest` — body `{tab_id,title,url,text,session_id,provider}` + `X-Provider-Key` → chunk → embed → store → count
- [ ] `POST /chat` — body `{question,session_id,source_tab_ids?,provider}` + `X-Provider-Key` → retrieve → generate → `{answer,citations}`
  - [ ] `source_tab_ids` filters retrieval to specific tabs → the **store interface must support metadata `where` filtering** (Chroma + pgvector both do)
- [ ] `POST /sessions/reset` — delete a session's content (also used on provider switch)
- [ ] Test via Swagger `/docs` (pass a test key in the header)
- [ ] Confirm a real browser `fetch()` succeeds (CORS works)

---

## 🧩 Phase 7 — Chrome Extension: Scaffold + Settings (Manifest V3)
- [ ] `extension/manifest.json`, **least privilege**: `activeTab`, `scripting`, `storage`, `sidePanel` (if used)
  - [ ] ⚠️ **Permission model:** build the multi-tab knowledge base by adding tabs **one at a time** ("Add this tab" on the active tab). Never read tabs in the background/simultaneously — this is what keeps `activeTab` sufficient and avoids broad `host_permissions` over arbitrary sites (easier Store review)
  - [ ] `host_permissions` → **only** your API origin (dev: `http://localhost:8000/*`)
  - [ ] Single **configurable API base URL** (dev vs prod)
- [ ] **Settings screen** (the BYOK heart):
  - [ ] Provider dropdown (Gemini default / OpenAI)
  - [ ] Key input → saved to `chrome.storage.local`; shown **masked**; "clear key" button
  - [ ] Link/instructions for getting a free Gemini key
  - [ ] Friendly empty state: "Add your free key to start"
- [ ] `icons/` at 16 / 48 / 128 px
- [ ] Load unpacked; confirm settings persist across restarts

---

## 👀 Phase 8 — Extension: Scrape (on user action) & Wire to Backend
- [ ] `content.js` — extract visible text (`innerText`) **only after the user acts**
- [ ] `background.js` (service worker) — the **only** caller of the backend; reads the key from `chrome.storage` and attaches it to each request
- [ ] **Session model:** the extension generates and owns `session_id` (one per study session), stores it in `chrome.storage`, and sends it on every `/ingest` and `/chat`; "Reset session" (and **provider switch**) issue a fresh `session_id` / call `/sessions/reset`
- [ ] UI (`panel.js/html/css`):
  - [ ] "Add this tab" → scrape → `POST /ingest` (with key header) → confirmation
  - [ ] Chat box → `POST /chat` → render answer + **citations**
  - [ ] "Reset session" → `POST /sessions/reset`
- [ ] ⚠️ Content script must **never** call a provider directly (key stays in the worker; network auditable)
- [ ] Handle "no key set", "invalid key", and "backend down" with clear messages
- [ ] **Milestone (v1 works):** paste free Gemini key → open GfG tab → Add → ask → grounded answer + citation

---

## ✨ Phase 9 — Production-Ready Backend (before publishing)
- [ ] **Default: keep the ephemeral short-TTL session store** with an auto-expiry job. Add a **persistent** per-user/session store (Postgres + **pgvector** or managed vector DB) **only if persistence is explicitly required** — storing scraped content server-side adds cost + privacy/compliance burden
- [ ] Isolate data by `session_id` (+ `user_id` later); if persisting, add backups + a **retention/expiry** (TTL) job
- [ ] Reconfirm strict **payload/volume limits** server-side (page size, chunks, sources per session, ingests per window, question length)
- [ ] **Abuse protection & access control:** lightweight anonymous **session token** (extension-issued) so requests are attributable + throttled **per client** (per-IP as fallback). ⚠️ BYOK removes the *AI* bill but the open API can still run up your **compute/storage** bill — this is not optional
- [ ] **Logging/monitoring** that excludes raw page text **and keys** (never log request headers/bodies)
- [ ] `Dockerfile` + production start command (gunicorn + uvicorn workers)

---

## 🚀 Phase 10 — Deploy the Backend (HTTPS)
- [ ] Choose a host: **Render / Railway / Fly.io / Cloud Run** (Render/Railway easiest first)
- [ ] Deploy the `backend/` service from the Dockerfile
- [ ] Set **host settings** (non-secret): allowed origins, env name, DB URL *(only if using the persistent store)* — ⚠️ **no provider key here**
- [ ] *(If persistence is enabled)* attach the managed database; otherwise the ephemeral short-TTL store needs no DB
- [ ] Custom HTTPS domain (e.g. `api.tabsage.example`); verify `GET /health`
- [ ] Confirm keys/page text never appear in production logs

---

## 🧪 Phase 11 — Test & Optimize
- [ ] Unit tests: `clean_text`, `chunk_text` (count/overlap)
- [ ] Provider tests with a mocked client (Gemini + OpenAI paths) — no real key in CI
- [ ] `retrieve()` returns the right chunk for a known question (tiny fixed corpus)
- [ ] "Not in context" returns a refusal, not a hallucination
- [ ] Key-handling test: bad/missing key → clean error; confirm key never logged
- [ ] Provider-switch test: session reset enforced (embedding consistency)
- [ ] Endpoint tests with FastAPI `TestClient`
- [ ] Small eval set (~10 Q&A) → tune chunk size / overlap / top-K; record before/after

---

## 🔐 Phase 12 — Privacy & Compliance (required to publish)
- [ ] Host a public **Privacy Policy URL**: only user-selected tabs are read; text/URLs/questions go to the TabSage backend and on to the user's chosen provider **using the user's own key**; what's stored + retention; how to delete; no selling/ad/training use
- [ ] In-extension **notice** before first ingest + a clear statement that the key is **stored only on the user's device** and sent transiently (never stored server-side) to call the provider on their behalf
- [ ] Complete Chrome Web Store **privacy/data-use disclosures** truthfully (state BYOK)
- [ ] Justify every permission (map each to a feature)
- [ ] ⚠️ Confirm **no key** (yours or a user's) appears in code, commits, screenshots, or the demo video

---

## 📦 Phase 13 — Package & Publish to Chrome Web Store
- [ ] Set the extension's API base URL to the **production HTTPS** endpoint
- [ ] Scope `host_permissions` to **only** that production API origin
- [ ] Build the ZIP of **`extension/` contents only** — ⚠️ verify no `.env`, backend files, source maps, or keys
- [ ] Create/complete a **Chrome Web Store developer account** (registration + applicable fee)
- [ ] Listing assets: name, description, 128px icon, screenshots, category, support URL, privacy URL
- [ ] In the description, clearly state **"requires your own free Gemini API key"**
- [ ] Upload ZIP → complete disclosures → **submit for review**
- [ ] After approval, install the **published** build and test end-to-end with a real free key
- [ ] Push the repo to **GitHub** (⚠️ `.env` gitignored; no keys anywhere)

---

## · Stretch Goals (after it works & ships)
### 🖥️ Local / no-key provider (third option)
- [ ] Add a **local provider**: sentence-transformers embeddings + **Ollama** LLM (no key at all)
- [ ] Provider dropdown gains "Local (Ollama)"
### 🤖 Agentic web-search fallback ("agents" + tool-calling)
- [ ] Detect "not in your tabs" as a trigger
- [ ] Add a web-search **tool** via function calling; label answers tab vs web sourced
### 📈 Quality upgrades
- [ ] Re-ranking retrieved chunks
- [ ] Streaming answers (token-by-token)
- [ ] Highlight the cited passage inside the source tab

---

## 🎯 Build Order / Milestones
1. **Setup:** Phase 0 (free Gemini dev key, venv, deps)
2. **BYOK core + RAG script:** Phase 1 → 5 (provider interface + loop in the terminal, no UI)
3. **Service:** Phase 6 (FastAPI, key via header, test via `/docs`)
4. **Working v1:** Phase 7 → 8 (settings key paste → grounded answer against `localhost`) ✅ demoable
5. **Make it publishable:** Phase 9 → 10 (ephemeral store + abuse limits, HTTPS deploy — no *AI* bill thanks to BYOK, but budget hosting/storage)
6. **Quality:** Phase 11 (tests + eval)
7. **Compliance:** Phase 12 (privacy policy + disclosures)
8. **Ship:** Phase 13 (package extension only, publish, test the Store build)
9. **Bonus:** local no-key provider, agentic fallback, quality upgrades

> Two facts that define this project: **(1)** only `extension/` goes to the Chrome Web Store; the Python
> backend is hosted separately over HTTPS. **(2)** BYOK — each user's key lives only in their browser and
> is used transiently by a backend that is stateless about secrets, so the developer pays **no AI cost** and model
> usage scales per user. (Hosting + storage still cost the developer and scale with usage — cap them with limits.)

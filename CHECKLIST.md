 ✓ TabSage — Master Build Checklist

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

## 🏁 Phase 0 — Platform & Environment Setup  ✅ DONE
### 0a — Provider key (for your own dev/testing)
- [x] Create a **Google AI Studio / Gemini API key** (free tier) — this is TabSage's default provider
- [ ] (Optional) Create an **OpenAI key** if you want to test the OpenAI provider too _(optional — skipped for now)_
- [x] ⚠️ These are **your** dev keys — in production, each user brings their own (BYOK), so you host no key
### 0b — Local tooling
- [x] Install **Python 3.10+** (3.13.2 ✓), **Google Chrome**, a code editor (VS Code)
- [x] Install **git** (2.44.0 ✓) — ⚠️ **Docker deferred to Phase 10** (only needed for production deploy; not installed yet)
### 0c — Repo skeleton (one repo, two deploy targets)
- [x] Create repo `tabsage/` with `backend/` and `extension/` subfolders
- [x] `cd backend` → `python -m venv .venv` → activate it
- [x] `.gitignore` ignores `.venv/`, `.env`, `__pycache__/`, `chroma_db/`, build/zip artifacts
- [x] Starter `README.md`; keep `DOCUMENTATION.md` in sync
### 0d — Config (note: NO provider key lives in the backend)
- [x] `backend/.env.example` + `backend/.env` for **non-secret settings only** (allowed origins, env name)
- [x] For local testing, you may pass your dev key from the extension settings just like a real user would
- [x] `requirements.txt` — fastapi, uvicorn, gunicorn, google-generativeai, openai (optional), langchain-text-splitters, chromadb (dev), pydantic, pydantic-settings, python-dotenv _(used `langchain-text-splitters` instead of full `langchain`)_
- [x] `pip install -r requirements.txt` and confirm no errors _(all imports verified OK)_

---

## 🧱 Phase 1 — Backend Foundations (FastAPI, stateless about secrets)  ✅ DONE
- [x] `config.py` — non-secret settings only (⚠️ do **not** load a provider key here) _(pydantic-settings; no key attr, verified)_
- [x] `main.py` — FastAPI app + `uvicorn` entry
- [x] `GET /health` returns `{status:"ok"}` (deploy health check; no secrets)
- [x] Enable **CORS**, restricted (not `*`) — allowlist the extension origin `chrome-extension://<extension-id>` (+ `http://localhost` in dev) _(localhost allowlisted; extension origin added in Phase 7; verified preflight echoes origin, not `*`)_
- [x] Swagger loads at `http://localhost:8000/docs`
- [x] **Pydantic models**: `IngestRequest`, `ChatRequest`, `ChatResponse` (include `session_id` + `provider`) _(also Citation, IngestResponse, HealthResponse, Provider enum)_
- [x] Read the **user's key from a request header** (e.g. `X-Provider-Key`), never from server config _(deps.get_provider_key; 401 if missing, verified)_

---

## 🔌 Phase 2 — Provider Abstraction (the BYOK core)  ✅ DONE
- [x] `providers/base.py` — interface with `embed(texts)` + `generate(prompt)` _(+ normalized errors, backoff/retry)_
- [x] `providers/gemini.py` — Gemini implementation (default) _(**google-genai** client-per-key; `gemini-embedding-001` 3072-dim + `gemini-3.6-flash`; verified end-to-end with a live key)_
- [x] `providers/openai.py` — OpenAI implementation (optional) _(`text-embedding-3-small` + `gpt-4o-mini`)_
- [x] Factory: pick implementation from the request's `provider` field _(`providers/factory.py: get_provider`)_
- [x] ⚠️ Use the passed-in key **transiently** — never write it to disk, DB, or logs _(in-memory only; excluded from `__repr__`)_
- [x] ⚠️ **Embedding consistency**: a session's index must be queried with the same model that built it;
      switching provider requires a session reset (document this)
  - [x] Store the **embedding model name/version** in each chunk's metadata; verify it at query time and refuse/auto-reset on mismatch _(exposed as `embedding_model_id`; enforcement wired in Phases 4–5)_
- [x] ⚠️ **Provider rate limits**: batch embedding calls + backoff/retry (ingesting one page = many embed calls → free-tier RPM limits); surface a "rate limited, retrying" state _(`embed_batch_size` + `retry_with_backoff`; `ProviderRateLimit` normalized)_

> **SDK note:** switched Gemini from the deprecated `google-generativeai` (global `configure()`, unsafe for concurrent BYOK keys) to **`google-genai`** (per-key `Client`). Model names are editable constants in `providers/gemini.py`; verify with `scripts/list_models.py`.

---

## 📥 Phase 3 — INGEST: Clean & Chunk  ✅ DONE
- [x] `clean.py` — strip nav/boilerplate/whitespace from raw page text _(NFKC normalize, strip zero-width/BOM, collapse inline whitespace, collapse blank runs to one paragraph break, drop consecutive duplicate lines = nav/footer boilerplate signal)_
- [x] `chunker.py` — LangChain `RecursiveCharacterTextSplitter` (~800 chars, ~150 overlap; note why) _(`Chunk` dataclass + `chunk_text`; defaults 800/150 with rationale documented; natural-boundary separators `["\n\n","\n",". "," ",""]`)_
- [x] Attach metadata per chunk: `session_id`, `tab_id`, `title`, `url` _(+ `chunk_index`; embedding-model id attached later at embed/store time in Phase 4)_
- [x] Enforce **payload limits**: max page size, max chunks, max sources _(`rag/ingest.py: prepare_chunks` enforces `max_text_chars` + `max_chunks_per_ingest` → `PayloadTooLargeError`. ⚠️ `max_sources_per_session` needs session state → deferred to the store/endpoint layer, Phases 4/6)_
- [x] Edge cases: empty / tiny / huge page _(empty/whitespace/all-boilerplate → `EmptyContentError`; tiny → single chunk; oversized text + too-many-chunks → `PayloadTooLargeError`; all verified via `scripts/try_ingest.py`, exit 0)_

> **New modules:** `rag/clean.py`, `rag/chunker.py`, `rag/ingest.py`, `rag/errors.py` (`IngestError`/`EmptyContentError`/`PayloadTooLargeError`), exported from `rag/__init__.py`. Manual check: `python scripts/try_ingest.py` (no key/network needed). The API `/ingest` endpoint stays a Phase 6 stub — Phase 3 delivers the clean+chunk building blocks only.

---

## 🧮 Phase 4 — EMBED & STORE  ✅ DONE
- [x] Embeddings go **through the provider interface** (Gemini default) using the user's key _(`rag/index.py: embed_and_store` calls `provider.embed(...)`; `embed_query` for the question. Key stays inside the transient provider instance — never in the store)_
- [x] `store.py` behind an interface; dev impl = **Chroma** (local) _(`VectorStore` ABC + `ChromaVectorStore` on `chromadb.EphemeralClient`; `get_store()` singleton; `Retrieved(text, metadata, score)` where score = 1 − cosine distance; `source_tab_ids` → metadata `where` filter)_
- [x] Scope every read/write by `session_id` (+ `user_id` later) for isolation _(**one collection per session**, `tabsage-<sha1(session_id)[:40]>` — clean isolation, reset = drop collection, and it dodges the Gemini-3072 vs OpenAI-1536 dimension clash a shared collection would hit; verified a 2nd session sees nothing)_
- [x] Dedupe re-ingested tabs (by `tab_id`/`url`) or reset the session first _(re-ingest deletes that tab's chunks before add → count doesn't grow; verified)_
- [x] ⚠️ **Default = ephemeral short-TTL session store** (in-memory/Chroma with auto-expiry). Persisting scraped page content server-side is an **opt-in** only. _(in-memory `EphemeralClient` = nothing on disk; `_last_seen` registry + `purge_expired(ttl)`; the background scheduler that calls it is Phase 9; persistent pgvector opt-in also Phase 9)_
  - [x] **Embedding-model consistency guard** — each chunk stores `embedding_model_id`; add/query with a different model raises `EmbeddingModelMismatchError` (caller refuses/auto-resets in Phase 5/6); verified on both add and query

> **New modules:** `rag/store.py` (`VectorStore`, `ChromaVectorStore`, `Retrieved`, `StoreError`, `EmbeddingModelMismatchError`, `get_store`, `DEFAULT_TOP_K`) and `rag/index.py` (`embed_and_store`, `embed_query`), exported from `rag/__init__.py`. Manual check: `python scripts/try_store.py` (offline, deterministic FakeProvider — no key/network) covers store → semantic query → tab filter → isolation → dedupe → model-switch guard → reset → TTL purge (exit 0). Optional live check with a real Gemini key confirmed 3072-dim vectors flow through. `/ingest` + `/chat` remain Phase 6 stubs.

---

## 🔍 Phase 5 — RETRIEVE & GENERATE  ✅ DONE
- [x] `chat.py` — embed question (user's key) → retrieve **top-K** chunks for the session _(`answer_question`; `embed_query` → `store.query` with `DEFAULT_TOP_K`=5)_
- [x] RAG prompt: "answer ONLY from this context; if absent, say you don't know" + chunks + question _(`build_prompt`; numbered `[i]` sources with title/url for inline citations)_
- [x] Generate via the provider interface; return `{ answer, citations }` (tab title/url per chunk) _(`ChatResult`; one `Citation` per distinct tab in retrieval order + snippet)_
- [x] Honest **"not in your tabs"** handling (no hallucination) _(fixed `NOT_IN_TABS` sentence; two refusal paths — no retrieval skips the generate call, or model emits the line → citations dropped, `grounded=False`)_
- [x] Robust **provider error handling** (bad/expired key, rate limit, timeout) → friendly, specific message _(normalized `ProviderError`s propagate; `describe_provider_error` adds an actionable hint)_
- [x] **Milestone:** run the whole loop as a plain script (paste key + text → ask → grounded answer) _(`scripts/try_chat.py` offline + `live`; live Gemini run verified: ingest → grounded cited answer → honest refusal)_

---

## 🌐 Phase 6 — API Endpoints  ✅ DONE
- [x] `POST /ingest` — body `{tab_id,title,url,text,session_id,provider}` + `X-Provider-Key` → chunk → embed → store → count _(`main.py:ingest`; enforces `max_sources_per_session` → 413, maps `PayloadTooLargeError`→413, `EmptyContentError`→422, `EmbeddingModelMismatchError`→409)_
- [x] `POST /chat` — body `{question,session_id,source_tab_ids?,provider}` + `X-Provider-Key` → retrieve → generate → `{answer,citations}` _(`main.py:chat`; returns `grounded` flag; provider errors → specific HTTP codes)_
  - [x] `source_tab_ids` filters retrieval to specific tabs → the **store interface must support metadata `where` filtering** (Chroma + pgvector both do) _(`ChromaVectorStore.query` `where={"tab_id": {"$in": [...]}}`; verified filter changes results)_
- [x] `POST /sessions/reset` — delete a session's content (also used on provider switch) _(`main.py:reset_session`; no key needed; returns `chunks_removed`)_
- [x] Test via Swagger `/docs` (pass a test key in the header) _(manual steps in `test.txt`; `scripts/try_api.py` drives all endpoints via `TestClient` → **27 passed, 0 failed**)_
- [x] Confirm a real browser `fetch()` succeeds (CORS works) _(CORS preflight verified: allowed origin echoed, not `*`; disallowed origin gets no allow-origin header. Live `uvicorn` boot: `/health`,`/docs`,`/openapi.json` all 200)_

---

## 🧩 Phase 7 — Chrome Extension: Scaffold + Settings (Manifest V3)  ✅ DONE
- [x] `extension/manifest.json`, **least privilege**: `activeTab`, `scripting`, `storage`, `sidePanel` (if used) _(MV3; `background` as ES-module service worker; `options_ui`→`settings.html`; `side_panel`→`sidepanel.html`)_
  - [x] ⚠️ **Permission model:** build the multi-tab knowledge base by adding tabs **one at a time** ("Add this tab" on the active tab). Never read tabs in the background/simultaneously. _(Phase 7 shipped with `activeTab`+`scripting` only. ↪ Phase 8 found `activeTab` isn't granted to a persistent side panel on a button click, so `host_permissions` for `http://*/*`+`https://*/*` were added; the one-tab-at-a-time, user-click-only behavior is unchanged.)_
  - [x] `host_permissions` → API origin in Phase 7 (dev: `http://localhost:8000/*`); **page origins added in Phase 8** so the worker can read an added tab
  - [x] Single **configurable API base URL** (dev vs prod) _(`config.js`: `ENV` switch → `API_BASE_URL`; prod is a placeholder until Phase 13)_
- [x] **Settings screen** (the BYOK heart):
  - [x] Provider dropdown (Gemini default / OpenAI) _(populated from `config.PROVIDERS`; selection persisted on change)_
  - [x] Key input → saved to `chrome.storage.local`; shown **masked**; "clear key" button _(`storage.js` save/clear; masked placeholder + Show/Hide reveal; blank save never wipes a stored key)_
  - [x] Link/instructions for getting a free Gemini key _(per-provider `keyUrl`, `keyHint`, and `linkText`)_
  - [x] Friendly empty state: "Add your free key to start" _(implemented as the restrained empty-chat state `Ask your tabs anything` + `Open settings`; composer remains disabled until configured)_
  - [x] Persistent appearance: **System** (default) / Light / Dark _(`theme.js`; System follows `prefers-color-scheme`; shared header icon menu next to Settings; no duplicate form control; stored as `tabsage.appearance`)_
- [x] `icons/` at 16 / 48 / 128 px _(generated by `backend/scripts/make_icons.py`; valid PNGs verified)_
- [x] Load unpacked; confirm settings persist across restarts _(manually verified by the user in Chrome — extension UI, BYOK settings, and System/Light/Dark theme are working; automated checks: all extension JS passes `node --check`, manifest validated as MV3 JSON)_

---

## 👀 Phase 8 — Extension: Scrape (on user action) & Wire to Backend  ✅ DONE
- [x] `content.js` — extract visible text (`innerText`) **only after the user acts** _(injected via `chrome.scripting.executeScript` on the "Add this tab" click only; not declared in the manifest so it never runs in the background; prefers `<article>`/`<main>`/`[role=main]`, falls back to `<body>`; a single `innerText` call keeps it fast; no network, no key)_
- [x] `background.js` (service worker) — the **only** caller of the backend; reads the key from `chrome.storage` and attaches it to each request _(sole `fetch` surface; `X-Provider-Key` header; key never returned to any page; normalized "no key / invalid key / backend down" errors; 15s injection timeout so a stalled read can't hang the UI)_
- [x] **Session model:** the extension generates and owns `session_id` (one per study session), stores it in `chrome.storage`, and sends it on every `/ingest` and `/chat`; "Reset" and **provider switch** rotate the `session_id` and call `/sessions/reset` _(`getSessionId`/`resetSessionId`; added-tab list cleared on reset and on provider switch)_
- [x] UI (`sidepanel.js/html/css`):
  - [x] "Add this tab" (+) → scrape → `POST /ingest` (with key header) → confirmation + source chip
  - [x] Chat box → `POST /chat` → render answer + **citations** _(answers rendered from Markdown to formatted HTML, XSS-safe; clickable numbered sources with snippets)_
  - [x] "Reset" → `POST /sessions/reset`
- [x] ⚠️ Content script must **never** call a provider directly (key stays in the worker; network auditable) _(content.js makes no network calls)_
- [x] Handle "no key set", "invalid key", and "backend down" with clear messages
- [x] **Milestone (v1 works):** paste free Gemini key → open study tab → Add → ask → grounded cited answer _(verified live end-to-end on GeeksforGeeks / freeCodeCamp)_

> **Permission change (important):** a persistent side panel does **not** receive `activeTab` for the current tab on a panel-button click, so `executeScript` stalled with no result. Fixed by declaring `host_permissions` for `http://*/*` + `https://*/*`. The extractor still runs **only** on the explicit "Add this tab" click and never in the background, so the least-privilege promise is preserved **by behavior** even though the permission scope is broader. This trade-off must be disclosed/justified at Store review (Phase 12). Manual checks in `PHASE8_VERIFY.md`; added dev tool `backend/scripts/probe_latency.py`. Default chunk size raised to 1500 and Gemini embeddings reduced to 768-dim to cut ingest latency.

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

## 🧪 Phase 11 — Test & Optimize  🚧 IN PROGRESS (automated suite done; eval/tuning pending)
- [x] Unit tests: `clean_text`, `chunk_text` (count/overlap) _(`tests/test_clean.py` 9, `tests/test_chunker.py` 7, `tests/test_ingest.py` 6 — whitespace/dupe/zero-width/NFKC/CRLF, chunk metadata+index, size bound, overlap guard, payload caps)_
- [x] Provider tests with a mocked client (Gemini + OpenAI paths) — no real key in CI _(`tests/test_providers.py` 28 — key-required/repr-safety, retry/backoff semantics, factory, vendor-error→normalized mapping for both SDKs, embed batching)_
- [x] `retrieve()` returns the right chunk for a known question (tiny fixed corpus) _(`tests/test_store.py::test_query_returns_most_relevant_tab` + filter/isolation/dedupe/reset/TTL/delete-tab; 12 total)_
- [x] "Not in context" returns a refusal, not a hallucination _(`tests/test_chat.py` — no-retrieval refusal skips generate; model-refusal drops citations; filtered-out tab refuses; 11 total)_
- [x] Key-handling test: bad/missing key → clean error; confirm key never logged _(missing→401, bad→401 mapping in `test_api.py`; `test_providers.py::test_repr_never_leaks_key`)_
- [x] Provider-switch test: session reset enforced (embedding consistency) _(`test_store.py` mismatch guard on add+query; `test_api.py::test_ingest_model_switch_is_409`)_
- [x] Endpoint tests with FastAPI `TestClient` _(`tests/test_api.py` 16 — health/root, auth, 422/409/413/429 mappings, happy path, reset, CORS allow/deny)_
- [ ] Small eval set (~10 Q&A) → tune chunk size / overlap / top-K; record before/after _(not started — needs a labeled corpus + a real provider key; tracked for a later pass)_

> **Suite:** `backend/tests/` (pytest). Run `python -m pytest` from `backend/` → **89 passed** (offline, no key/network; providers mocked via `tests/_fakes.FakeProvider` + `fake_factory`). Config in `pytest.ini` (`pythonpath=.`). `pytest==8.4.2` added to `requirements.txt`. The manual `scripts/` remain as live smoke checks.

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
- [ ] Set `host_permissions` to the production API origin **plus** the page origins the extractor needs (`https://*/*`, and `http://*/*` only if non-HTTPS study sites must be supported)
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

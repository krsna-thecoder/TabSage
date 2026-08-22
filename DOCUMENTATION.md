# TabSage — Project Documentation

> **Product:** A publishable Chrome extension that answers study questions from web pages the user explicitly selects.
> **Architecture:** Chrome Extension (Manifest V3) + a Python/FastAPI RAG API that is stateless about secrets (holds no provider key; ephemeral session data by default).
> **Model access:** **Bring Your Own Key (BYOK).** Each user supplies their own provider key.
> **Default provider:** Google **Gemini** (real free tier). **Optional:** OpenAI (`gpt-4o-mini` + `text-embedding-3-small`).

## 1. Overview

**TabSage** turns selected study tabs—such as GeeksforGeeks, freeCodeCamp, or W3Schools—into a temporary, source-grounded knowledge base. A user selects tabs, asks a question, and receives an answer based only on retrieved passages from those tabs, with citations.

TabSage is a **Retrieval-Augmented Generation (RAG)** product. It does not train a model on the pages; it retrieves relevant passages at question time and supplies them as context to the LLM.

Because TabSage uses a **Bring-Your-Own-Key (BYOK)** model, each user provides their own AI provider key (a free Gemini key by default). This means the developer pays **$0 for AI/model usage at any scale**, and the product can be published publicly without the developer paying for every user's model calls.

> **Cost clarification:** BYOK removes the *AI/model* bill only. It does **not** make the project free to operate. The FastAPI backend still needs a host (compute), and any server-side storage (see Section 7) costs money that scales with traffic and usage. Budget for hosting + storage, and cap usage with payload/volume limits (Section 10).

## 2. The Problem It Solves

Studying across many browser tabs makes it slow to find a forgotten concept, compare explanations, or verify that an answer matches the material currently being read. A general chatbot may answer from unrelated training knowledge.

TabSage makes the selected tabs the source of truth. It is designed to:
- answer questions using selected page content;
- name and link the source tabs that support the answer;
- say that the answer is unavailable when the selected sources do not contain it;
- require deliberate user action before reading a tab.

## 3. The BYOK Model (Core Design Decision)

Instead of the developer paying a central AI bill, **each user brings their own key**:

```text
User A → their own Gemini free-tier key → their own free quota
User B → their own Gemini free-tier key → their own free quota
...many users, $0 *AI cost* to the developer, no shared model rate limit
```

**Why BYOK:**
- The developer pays **nothing for AI/model usage**, at any number of users.
- Model usage scales per user — each user runs on their own provider quota (no shared model rate limit).
- It keeps full model quality (Gemini/OpenAI), not a weak local model.
- The only user cost is a **one-time key paste** in TabSage's settings.

> BYOK is about *model cost*, not *infrastructure cost*. Hosting the backend and any server-side storage still cost the developer money and scale with usage — see the cost clarification in Section 1 and abuse/limits in Section 10.

**The key is never *stored* on the developer's servers.** It is stored in the user's own browser (`chrome.storage.local`) and sent with each request so the backend can call the provider on that user's behalf. The backend uses it transiently in memory and never logs or persists it.

> **Honest framing:** the key *does transit* the backend on every request — it does not bypass the server. So there is no honeypot of keys *at rest*, but a compromised or malicious backend build could observe keys *in transit*. The residual trust is in the backend code and its transport (HTTPS). The consciously rejected alternative — the extension calling the provider directly, keeping the key entirely off the server — was traded away to centralize RAG logic. See Section 10.

### Why there is still a backend

The extension *could* call the provider directly, but a thin backend keeps the RAG logic (cleaning, chunking, retrieval, prompt construction) in one testable place and keeps provider differences out of the UI. The backend is **stateless about secrets**: it holds no provider key of its own (though it is *stateful about session vector data* — see Section 7).

## 4. Important Publishing Constraint

A Chrome extension can run JavaScript, HTML, CSS, and WebAssembly; it **cannot run a Python/FastAPI server inside Chrome**. The full TabSage repository contains both parts, but the Chrome Web Store package contains **only** the extension files.

```text
Git repository (one project)
├── extension/       → zipped and submitted to Chrome Web Store
└── backend/         → deployed separately as an HTTPS API (stateless about secrets)
```

## 5. End-to-End Architecture

```text
┌──────────────────────────── User's Chrome ─────────────────────────────┐
│  Settings: user pastes their own provider key → chrome.storage (local)  │
│                                                                         │
│  Selected study tab                                                     │
│       │ (user action)                                                   │
│       ▼                                                                 │
│  Content script extracts visible text                                   │
│       │ chrome.runtime message                                          │
│       ▼                                                                 │
│  Service worker ── HTTPS (request carries the user's key) ──► Backend    │
│  Side panel / popup ◄──────────── JSON (answer + citations) ──┘          │
└──────────────────────────────────────────────┼──────────────────────────┘
                                                 │
                   ┌─────────────────────────────▼───────────────────────┐
                   │ FastAPI backend (stateless about secrets)            │
                   │ /ingest: validate → clean → chunk → embed → store    │
                   │ /chat: retrieve → prompt → generate → cite           │
                   │ uses the user's key transiently; never stores it     │
                   └───────────────┬──────────────────────┬───────────────┘
                                   │                      │
                    ┌──────────────▼──────────┐  ┌────────▼──────────────┐
                    │ Vector store (per user/  │  │ User's chosen provider│
                    │ session)                 │  │ Gemini (default)/OpenAI│
                    └─────────────────────────┘  └───────────────────────┘
```

### Request flow

1. Once, the user pastes their provider key into TabSage settings; it is saved in `chrome.storage`.
2. The user adds tabs to the session **one at a time**: while a tab is active, the user clicks "Add this tab," which grants `activeTab` access to *that* page only. Repeating this on other tabs builds a multi-tab knowledge base without ever reading tabs in the background.
3. A content script reads visible text from that one active page only.
4. It messages the service worker, which sends authenticated JSON — **including the user's key** — to `/ingest`.
5. The backend uses the key to create embeddings and stores chunks with source metadata, scoped to that session.
6. The user asks a question; the service worker calls `/chat` with the key.
7. The backend retrieves the top chunks, prompts the model to answer only from that context, and returns an answer plus citations.
8. The extension renders the answer and source links.

> **Permission model:** TabSage never reads multiple tabs simultaneously or in the background. Each tab enters the knowledge base through a deliberate "Add this tab" gesture on the active tab, which is exactly what `activeTab` grants. This keeps the extension at **least privilege** (no broad `host_permissions` over arbitrary sites) and simplifies Chrome Web Store review, while still delivering the "study across many tabs" experience.

## 6. Provider Abstraction

TabSage talks to models through a small **provider interface** with two methods: `embed(texts)` and `generate(prompt)`. Concrete implementations:

| Provider | Embeddings | Answers | Cost to user |
|---|---|---|---|
| **Gemini (default)** | Gemini embeddings | Gemini model | Free tier |
| **OpenAI (optional)** | `text-embedding-3-small` | `gpt-4o-mini` | Paid |
| **Local (future)** | sentence-transformers | Ollama | Free, self-hosted |

The user picks a provider in settings and pastes the matching key. Swapping providers is a config choice, not a code change, because everything downstream depends only on the interface.

⚠️ **Embedding consistency:** a vector index must be queried with the **same** embedding model that built it. If a user switches providers, that session's index must be rebuilt (reset), because embeddings from different models are not comparable. **Store the embedding model name/version in each chunk's metadata** and verify it at query time (see Section 9), so a mismatch fails loudly instead of returning meaningless results.

## 7. Local Development vs Public Release

| Concern | Local development | Public Chrome Web Store release |
|---|---|---|
| API URL | `http://localhost:8000` | `https://api.tabsage.example` |
| Backend | FastAPI on the developer's machine | Dockerized FastAPI on a cloud host |
| Provider key | Developer's own key in settings | Each user's own key in settings (BYOK) |
| Who pays AI cost | Developer (their key) | **Each user (their key)** |
| Vector store | Local/in-memory Chroma | **Ephemeral short-TTL in-memory/session store (default)**; persistent per-user store (e.g. Postgres + pgvector) only as an explicit opt-in |
| Transport | Local HTTP acceptable | HTTPS only |
| Extension install | Chrome "Load unpacked" | ZIP uploaded and reviewed in the Store |

## 8. Tech Stack

| Layer | Development | Public release | Why |
|---|---|---|---|
| Extension | Manifest V3, vanilla JS | Same | No build step; current Chrome standard |
| UI | Popup (v1) → Side Panel | Side Panel | Better for multi-turn study chat |
| Settings | Key + provider stored in `chrome.storage` | Same | BYOK; key stays on the user's device |
| Page extraction | Content script + `innerText` (after user action) | Same | Captures visible study content |
| Backend | FastAPI + Uvicorn | FastAPI in Docker | Typed API, clear endpoints, stateless about secrets |
| RAG helpers | LangChain splitter + provider clients | Same | Fast chunking + model calls |
| Vectors | Chroma (dev) | **Ephemeral short-TTL session store by default**; Postgres + pgvector / managed vector DB only if persistence is explicitly needed | Minimize stored user content: less cost, less privacy risk, less compliance burden |
| Model access | BYOK (Gemini default / OpenAI optional) | Same | $0 *AI cost* to developer; scales per-user model quota |

## 9. Backend Components and API Contract

```text
backend/
├── main.py              # FastAPI app and routes
├── config.py            # settings (NOT provider keys)
├── requirements.txt
├── Dockerfile
├── providers/
│   ├── base.py           # Provider interface: embed(), generate()
│   ├── gemini.py         # Gemini implementation
│   └── openai.py         # OpenAI implementation
├── rag/
│   ├── clean.py          # page-text cleanup
│   ├── chunker.py        # split text + attach metadata
│   ├── store.py          # vector-store interface + impls
│   └── chat.py           # retrieve, prompt, generate, cite
└── tests/
```

### Endpoints (the user's key travels per request)

- `GET /health` — deployment health check; no secrets.
- `POST /ingest` — `{tab_id, title, url, text, session_id, provider}` + key via a request header (e.g. `X-Provider-Key`) → validate → chunk → embed → store → return count.
- `POST /chat` — `{question, session_id, source_tab_ids?, provider}` + key header → retrieve → generate → `{answer, citations}`. `source_tab_ids` filters retrieval to specific tabs, so the **store interface must support metadata `where` filtering** (Chroma and pgvector both do).
- `POST /sessions/reset` — delete a session's indexed content (also used when switching providers).

The key is read from the request, used in memory to call the provider, and discarded. It is **never** written to disk, database, or logs.

### Session model and lifecycle

- The **extension generates and owns `session_id`** (e.g., one per side-panel/study session), stores it in `chrome.storage`, and sends it on every `/ingest` and `/chat` call.
- The default store is **ephemeral with a short TTL**: sessions expire automatically after a stated idle/lifetime window, and are also cleared by `POST /sessions/reset`. Persistent per-user storage is an explicit opt-in, not the baseline (see Sections 7–8).
- Switching providers **must** trigger a session reset (embeddings are not comparable across models — see Section 6).

### Embedding-model metadata (correctness guard)

- Each stored chunk records the **embedding model name/version** that produced it.
- `/chat` compares the query's embedding model against the session's stored model; on mismatch it **refuses or auto-resets** rather than returning garbage similarity results. This is a hard guard against the most common RAG correctness bug.

### Rate limits and CORS

- **Provider rate limits:** ingesting one page produces many chunks → many embedding calls, which can hit the Gemini free-tier per-minute limit. The backend must **batch embeddings** and apply **backoff/retry**, and surface a friendly "rate limited, retrying" state to the extension.
- **CORS:** restrict allowed origins (not `*`). Requests from the extension carry `Origin: chrome-extension://<extension-id>`, so that exact origin (plus `http://localhost` in dev) must be allowlisted or browser calls will fail.

## 10. Security, Privacy, and Key Handling

### The user's key

- Stored only in the user's browser (`chrome.storage.local`), entered by the user in settings.
- Sent over **HTTPS** with each request; used by the backend transiently, then discarded.
- **Never** stored server-side, logged, or included in error messages.
- Never placed in `manifest.json`, extension source committed to Git, screenshots, or demo videos.
- The extension shows the key masked and offers a "clear key" action.

### What BYOK does and does not protect

Because the developer holds no central AI key, there is **no shared model bill to protect** and **no honeypot of user keys stored at rest** on the server. This is simpler and safer than a shared-key design.

But BYOK does **not** remove every risk:
- **Keys still transit the backend** in memory on every request; a compromised backend could observe them. Mitigate with HTTPS, minimal dependencies, and never logging headers/bodies.
- **The backend itself is a cost surface.** Even with zero AI cost, an open API that accepts page text and writes to a store can be abused to run up your **compute and storage** bill. BYOK protects the AI bill, not the infrastructure bill.

The backend needs basic hygiene regardless: HTTPS, input/payload limits (max page size, chunks, sources, question length), request validation, and provider-error handling.

### Backend access control and abuse protection

The API is network-exposed and does **not** require a provider key of its own, so it must not be left fully open:
- Add a **lightweight anonymous session/identity check** (e.g., an extension-issued session token) so requests are attributable and rate-limitable per client, not just per IP.
- Enforce **hard payload and volume caps** server-side: max text size per ingest, max chunks, max sources per session, max ingests per session/time window, max question length.
- Apply **per-client throttling** (per session token, with per-IP as a fallback).
- These limits bound your storage/compute cost even though AI usage is BYOK.

### Content script boundary

The content script never calls a provider or third party directly. It only messages the service worker, which calls the configured TabSage backend. This keeps network access auditable and the key handling in one place.

### Privacy model to implement and disclose

Before ingestion, the extension must tell users that selected page text, URLs/titles, and questions are sent to the TabSage backend and on to the user's chosen provider (Gemini/OpenAI) to create embeddings and answers, using the user's own key.

Define and publish a simple policy:
- process only user-selected tabs;
- do not sell or use source content for advertising/training;
- expire raw page text, embeddings, and chats after a stated session TTL or on Reset;
- provide deletion/reset controls;
- do not log raw page content or keys.

Create an accurate public privacy-policy URL and complete the Chrome Web Store privacy disclosures. Chrome requires transparent handling/disclosure of extension user data and a privacy policy when applicable: [Chrome Web Store user-data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq) and [privacy policy requirements](https://developer.chrome.com/docs/webstore/program-policies/privacy).

## 11. Chrome Web Store Release Model

The Store receives a ZIP containing the **contents of `extension/` only**. The Python backend, Docker files, and databases are never uploaded. Because of BYOK, there is also **no developer provider key anywhere** in the submission.

Release sequence:
1. Deploy the (secret-stateless) HTTPS backend and verify `/health`.
2. Set the production API URL in the extension configuration.
3. Scope `host_permissions` to that exact API URL.
4. Build the extension ZIP; verify it contains no keys, `.env`, source maps, or backend files.
5. Create/complete a Chrome Web Store developer account (registration + applicable fee).
6. Upload the ZIP, listing assets, support URL, and privacy-policy URL.
7. Complete permission and privacy disclosures truthfully (state that users provide their own key).
8. Submit for review, then test the installed Store build against production.

Manifest V3 is required for new submissions. See Chrome's [publishing best practices](https://developer.chrome.com/docs/webstore/best-practices) and [developer-account registration](https://developer.chrome.com/docs/webstore/register).

## 12. RAG Concepts

- **Embedding:** a numeric representation of a passage's meaning.
- **Chunking:** splitting long pages into overlapping, retrievable passages.
- **Vector database:** storage that finds chunks semantically similar to a question.
- **Retrieval:** selecting the top relevant chunks before generation.
- **Grounded generation:** instructing the LLM to answer only from retrieved context.
- **Citation:** returning tab title/URL + passage metadata so users can verify an answer.

## 13. Build Roadmap

1. Build the local RAG core behind a provider interface: clean → chunk → embed → store → retrieve → answer (Gemini default).
2. Wrap it in FastAPI; the key arrives per request, used transiently.
3. Build the Manifest V3 extension with a **settings screen for key + provider**; test against `localhost`.
4. Add source selection, citations, reset/delete, provider switching, and error states.
5. Keep the ephemeral short-TTL session store as the default; add a persistent per-user/session store only if persistence is explicitly required.
6. Add privacy notice, hard payload/volume limits, per-client throttling (anonymous session token), and monitoring. BYOK removes the AI bill but **not** the infra/abuse surface.
7. Deploy the (secret-stateless) backend to HTTPS; point the extension at production.
8. Package only the extension, publish to the Chrome Web Store, and test the Store build.

## 14. Future Enhancements

- Local/private mode (Ollama + sentence-transformers) as a third provider — no key at all.
- Re-ranking retrieved chunks for higher precision.
- Streaming answer tokens in the side panel.
- Highlighting the cited passage in the source tab.
- Optional agentic web-search fallback, clearly separated from tab-only answers.
- Automated retrieval/answer evaluation on a small labeled set.

> External policy guidance was summarized and rephrased for compliance with licensing restrictions.

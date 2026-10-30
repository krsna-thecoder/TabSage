# Phase 8 — Manual Verification

Phase 8 wires the extension to the backend: scrape the active tab on a user
action, send it through the service worker (the only backend caller) to
`/ingest`, ask questions via `/chat`, render answers with citations, and reset
the session. These checks need the backend running locally.

## 0. Prerequisites

1. **Start the backend** (from `backend/`, with the venv active):
   ```bash
   uvicorn main:app --reload
   ```
   Confirm `http://localhost:8000/health` returns `{"status":"ok"}` and
   `http://localhost:8000/docs` loads.
2. **A free Gemini key** from https://aistudio.google.com/app/apikey.
3. **Reload the extension**: open `chrome://extensions`, enable Developer mode,
   and reload TabSage (or **Load unpacked** → `C:\Users\KRSNA\Desktop\TabSage\extension`).
   Confirm the card shows no errors.

> If you change `ENV` in `config.js` you must also match `host_permissions` in
> `manifest.json`. Dev uses `http://localhost:8000` and `http://localhost:8000/*`.

## 1. Set your key (BYOK)

1. Click the TabSage toolbar icon to open the side panel, then open **Settings**.
2. Provider = **Google Gemini (free tier)**. Paste your real Gemini key, click
   **Save**. Confirm the badge reads **Configured**.

## 2. The "no key" state (do this before step 1 if starting fresh)

With no key saved, the side panel shows **Ask your tabs anything** / **Open
settings**, the composer hint says `Add an API key in Settings to begin.`, and
the **+**, input, and send button are all disabled.

## 3. Add this tab → /ingest (the core gesture)

1. Open a normal study page in a tab, for example a GeeksforGeeks or
   freeCodeCamp article.
2. Open the TabSage side panel (click the toolbar icon if it isn't already
   open) and make sure your study tab is the active, visible tab.
3. Click the **+** button in the composer.
4. Confirm:
   - a transient `Reading this tab…` line appears, then becomes
     `Added "<page title>" · N passages indexed.` (N ≥ 1);
   - a **chip with the page title** appears in the Tabs bar at the top;
   - the input and send button become **enabled**.
5. In the backend terminal, confirm a `POST /ingest` returned `200`.

> **If you see** `Couldn't read this tab…`: the active tab wasn't granted to the
> extension (common if you switched tabs after opening the panel). Go to the
> page, click the TabSage toolbar icon on it, then click **+** again.
>
> **If you see** `This page can't be read…`: you're on a `chrome://`,
> extension, or Web Store page. Those can't be scraped by design.

## 4. Ask a grounded question → /chat + citations

1. Type a question answerable from that page and press **Enter** (or click send).
2. Confirm:
   - your question appears as a right-aligned bubble;
   - a typing indicator (three dots) shows while waiting;
   - an answer replaces it, followed by a **Sources** list with numbered,
     clickable links (title → the tab URL) and short snippets;
   - clicking a source opens the page in a new tab.
3. In the backend terminal, confirm `POST /chat` returned `200`.

## 5. Honest "not in your tabs" refusal

1. Ask something clearly unrelated to the added page (e.g. "What's the capital
   of France?" on a page about sorting algorithms).
2. Confirm the answer is the refusal line
   *"I couldn't find that in your selected tabs."*, shown in the muted/italic
   style, with **no citations**. This proves answers are grounded, not invented.

## 6. Multiple tabs (optional)

1. Open a second study page, click the TabSage icon on it, then **+**.
2. Confirm a second chip appears and questions can draw from either tab (watch
   the citations change based on the question).

## 7. Reset session → /sessions/reset

1. Click **Reset** in the Tabs bar.
2. Confirm the chips disappear, the conversation clears, the composer returns to
   the `Add a tab…` disabled state, and a `Session reset.` note appears.
3. In the backend terminal, confirm `POST /sessions/reset` returned `200`.
4. In the service-worker console (`chrome://extensions` → TabSage → **service
   worker**), run `chrome.storage.local.get(console.log)` and confirm
   `tabsage.sessionId` changed and `tabsage.sources` is gone.

## 8. Provider switch resets the session

1. Add a tab so a session exists.
2. Open **Settings** and change Provider to **OpenAI** (then back to Gemini).
3. Confirm Settings reports `Provider saved. Session reset for the new model.`
   and the side panel's Tabs bar is now empty. (Embeddings aren't comparable
   across models, so the session must reset — this is the correctness guard.)

## 9. Error handling

- **Invalid key:** set an obviously bad key in Settings, add a tab. Confirm the
  system line shows a specific message like *"Invalid or unauthorized Gemini API
  key…"* (surfaced from the backend's 401), not a stack trace.
- **Backend down:** stop `uvicorn`, then click **+** or ask. Confirm the message
  is *"Can't reach the TabSage backend. Make sure it's running…"*. Restart
  `uvicorn` and confirm it works again.

## 10. Key never leaves the worker (security check)

1. Open the **side panel** DevTools (right-click the panel → Inspect) and the
   **service worker** DevTools separately.
2. In the side-panel console, run:
   ```js
   chrome.storage.local.get("tabsage.apiKey", console.log)
   ```
   The key is in storage (expected), but note the panel only ever *reads it for
   display masking in Settings* — it is never put on a network request. All
   `fetch` calls to the backend happen in the **service worker**, which is the
   only place the `X-Provider-Key` header is attached. The content script
   (`content.js`) makes no network calls at all.

## Pass criteria

- [ ] No-key state disables the composer with a clear hint.
- [ ] **+** scrapes the active tab and `POST /ingest` succeeds; a chip appears.
- [ ] Asking a grounded question returns an answer **with clickable citations**.
- [ ] An unanswerable question returns the refusal line with **no citations**.
- [ ] **Reset** clears tabs + conversation and rotates the session id via
      `POST /sessions/reset`.
- [ ] Switching provider resets the session.
- [ ] Invalid-key and backend-down both show specific, friendly messages.
- [ ] All backend network calls originate from the service worker; the content
      script never calls out and never sees the key.

> **Milestone:** paste a free Gemini key → open a study tab → **+** → ask →
> grounded answer + citation. That is Phase 8's "v1 works" goal.

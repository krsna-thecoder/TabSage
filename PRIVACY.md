# TabSage Privacy Policy

**Effective date:** 30 October 2026

TabSage is a browser extension that answers your study questions using only the
web pages (tabs) you explicitly choose. This policy explains what data TabSage
handles, where it goes, and the choices you have. Plain version first: **TabSage
reads a page only when you click "Add this tab," uses your own AI provider key,
and does not sell, advertise with, or train models on your content.**

## Who processes your data

- **The TabSage extension**, running in your browser.
- **The TabSage backend**, an HTTPS API that performs the retrieval logic. It is
  *stateless about secrets* — it never stores your API key.
- **Your chosen AI provider** — Google Gemini (default) or OpenAI — which you
  access with **your own API key** (BYOK, "bring your own key").

## What data is processed

When you add a tab and ask a question, the following is processed:

- **Selected page content** — the visible text of a tab, read **only** when you
  click "Add this tab." TabSage never reads tabs in the background or reads
  multiple tabs at once.
- **Page title and URL** — used to label and link citations.
- **Your questions** — the text you type to ask about your added tabs.
- **A session identifier** — a random id generated in your browser to group one
  study session's tabs together.
- **A random installation identifier** — used only to rate-limit abuse. It
  identifies this browser installation and can link that installation's
  requests; it is not tied to your personal identity.
- **Your AI provider API key** — see "How your API key is handled" below.

## How your data flows

1. You paste your provider API key once; it is saved **only in your browser**
   (`chrome.storage.local`).
2. When you add a tab, its text, title, and URL are sent over **HTTPS** to the
   TabSage backend.
3. The backend uses **your API key** (sent with the request) to create
   embeddings via your chosen provider and stores them **only for your session**.
4. When you ask a question, the backend retrieves the most relevant passages and
   sends them, with your question, to your provider to generate an answer.
5. The answer and its citations are returned to the extension and shown to you.

## How your API key is handled

- Stored **only on your device** in `chrome.storage.local`. You can view it
  masked and remove it any time with **Clear key** in Settings.
- Sent over HTTPS with each request so the backend can call your provider **on
  your behalf**. It is used **transiently in memory** and then discarded.
- **Never** stored on a server, written to a database, written to logs, or
  included in error messages. It is never placed in the extension's source,
  screenshots, or demo materials.
- Honest limitation: because the key *passes through* the backend in memory on
  each request, a compromised backend could in principle observe it in transit.
  TabSage mitigates this with HTTPS, minimal dependencies, and never logging
  request headers or bodies. There is no store of keys at rest to breach.

## Storage and retention

- The vector data for a session is **ephemeral and in-memory**. Nothing is
  written to disk by default.
- It is removed when you click **Reset**, when you switch providers, and
  **automatically** after a period of inactivity (a short session TTL). It is
  also cleared if the backend restarts.
- **Raw page text and API keys are never logged.** Access logs record only
  request method, path, status, latency, and caller IP.

## What TabSage does not do

- Does **not** sell your data or share it for advertising.
- Does **not** use your page content or questions to train any model.
- Does **not** read tabs you have not explicitly added, and does not read tabs
  in the background.

## Third parties

- **Your AI provider (Google Gemini or OpenAI)** processes the content and
  questions you send, under *your* account and their terms. Review their
  policies: Google Gemini / Google AI, and OpenAI.
- **Hosting:** the backend runs on a cloud host (AWS) solely to serve the API.

## Your choices and controls

- **Add tabs deliberately** — nothing is read until you click "Add this tab."
- **Reset** clears the current session's tabs, chat, and stored passages.
- **Clear key** removes your API key from your device.
- **Uninstall** removes all TabSage data stored in your browser.

## Children

TabSage is not directed to children and does not knowingly collect data from
children.

## Changes

We may update this policy; the effective date above will change accordingly.
Material changes will be reflected in the extension listing.

## Contact

Questions about this policy: **krsna.thecoder@gmail.com**

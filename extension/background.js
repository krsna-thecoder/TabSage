/**
 * TabSage background service worker (ES module) — the ONLY backend caller.
 *
 * Phase 8: the side panel and Settings never touch the network. They send
 * messages here; this worker reads the user's provider key from
 * chrome.storage.local and attaches it to /ingest and /chat as the
 * `X-Provider-Key` header. The key is used transiently and is NEVER returned to
 * any page — pages only ever receive non-secret results.
 *
 * Message API (all async, respond with {ok:true,...} or {ok:false,error,status}):
 *   ingestActiveTab           → scrape the active tab + POST /ingest
 *   chat {question}           → POST /chat, returns {answer,citations,grounded}
 *   resetSession              → POST /sessions/reset + rotate local session id
 */
import { API_BASE_URL } from "./config.js";
import {
  addSource,
  clearSources,
  getClientToken,
  getSessionId,
  getSettings,
  resetSessionId,
} from "./storage.js";

// Open the side panel when the user clicks the toolbar icon.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error("sidePanel.setPanelBehavior failed:", err));
});

// ── backend helper ──────────────────────────────────────────────────────────
class BackendError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "BackendError";
    this.status = status;
  }
}

// Build a friendly message from a non-OK backend response. Shared by the
// request and streaming paths so the {detail} extraction + Retry-After hint
// can't diverge.
async function describeBackendError(resp) {
  let detail = `The backend returned an error (${resp.status}).`;
  try {
    const data = await resp.json();
    if (data && data.detail) {
      detail =
        typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    }
  } catch {
    // Non-JSON error body — keep the generic message.
  }
  if (resp.status === 429) {
    const retryAfter = resp.headers.get("Retry-After");
    if (retryAfter) detail += ` (retry in ~${retryAfter}s)`;
  }
  return detail;
}

async function callBackend(path, { method = "POST", body, key } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // Random per-install id for per-client rate limiting (not a secret).
  headers["X-Client-Token"] = await getClientToken();
  // The key travels only here, worker → backend. Never to a page.
  if (key) headers["X-Provider-Key"] = key;

  let resp;
  try {
    resp = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    // Connection refused / DNS / offline → the backend is unreachable.
    throw new BackendError(
      "Can't reach the TabSage backend. Make sure it's running, then try again.",
      0,
    );
  }

  if (!resp.ok) {
    throw new BackendError(await describeBackendError(resp), resp.status);
  }
  return resp.json();
}

// ── page extraction (user gesture only) ──────────────────────────────────────
const _RESTRICTED = /^(chrome|edge|about|chrome-extension|devtools|view-source):/i;

async function extractActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || tab.id == null) {
    throw new BackendError("No active tab to add.", 0);
  }

  const url = tab.url || "";
  if (
    _RESTRICTED.test(url) ||
    url.startsWith("https://chrome.google.com/webstore") ||
    url.startsWith("https://chromewebstore.google.com")
  ) {
    throw new BackendError(
      "This page can't be read (a browser or Web Store page). Open a normal web page and try again.",
      0,
    );
  }

  let results;
  const injection = chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["content.js"],
  });
  const timeout = new Promise((_, reject) =>
    setTimeout(
      () =>
        reject(
          new BackendError(
            "Reading this page timed out. Reload the tab, then Add it again.",
            0,
          ),
        ),
      15000,
    ),
  );
  try {
    results = await Promise.race([injection, timeout]);
  } catch (err) {
    if (err instanceof BackendError) throw err; // our timeout message
    // activeTab wasn't granted for this tab (e.g. you switched tabs after
    // opening the panel), or the page blocks injection.
    throw new BackendError(
      "Couldn't read this tab. Open the page, click the TabSage toolbar icon on it, then Add this tab.",
      0,
    );
  }

  const payload = results && results[0] ? results[0].result : null;
  if (!payload || !payload.text) {
    throw new BackendError("This page has no readable text to add.", 0);
  }

  return {
    tab_id: String(tab.id),
    title: payload.title || tab.title || "Untitled",
    url: payload.url || url,
    text: payload.text,
  };
}

// ── actions ───────────────────────────────────────────────────────────────
async function ingestActiveTab() {
  const { provider, apiKey, hasKey } = await getSettings();
  if (!hasKey) {
    throw new BackendError(
      "No API key set. Add your provider key in Settings first.",
      401,
    );
  }

  const page = await extractActiveTab();
  const session_id = await getSessionId();

  const data = await callBackend("/ingest", {
    key: apiKey,
    body: {
      tab_id: page.tab_id,
      title: page.title,
      url: page.url,
      text: page.text,
      session_id,
      provider,
    },
  });

  await addSource({ tab_id: page.tab_id, title: page.title, url: page.url });

  return {
    tab: { tab_id: page.tab_id, title: page.title, url: page.url },
    chunksIndexed: data.chunks_indexed ?? 0,
  };
}

async function chat(question, sourceTabIds) {
  const q = (question || "").trim();
  if (!q) throw new BackendError("Ask a question first.", 0);

  const { provider, apiKey, hasKey } = await getSettings();
  if (!hasKey) {
    throw new BackendError(
      "No API key set. Add your provider key in Settings first.",
      401,
    );
  }

  const session_id = await getSessionId();
  const body = { question: q, session_id, provider };
  if (Array.isArray(sourceTabIds) && sourceTabIds.length) {
    body.source_tab_ids = sourceTabIds;
  }

  const data = await callBackend("/chat", { key: apiKey, body });
  return {
    answer: data.answer,
    citations: data.citations || [],
    grounded: Boolean(data.grounded),
  };
}

async function resetSession() {
  const session_id = await getSessionId();
  let chunksRemoved = 0;
  try {
    const data = await callBackend("/sessions/reset", { body: { session_id } });
    chunksRemoved = data.chunks_removed ?? 0;
  } catch (err) {
    // If the backend is simply unreachable, still rotate locally so the user
    // gets a clean slate. Re-raise anything else (unexpected server error).
    if (!(err instanceof BackendError) || err.status !== 0) throw err;
  }
  await clearSources();
  const sessionId = await resetSessionId();
  return { sessionId, chunksRemoved };
}

// ── streaming chat (Server-Sent Events relayed over a port) ──────────────────
// The side panel opens a "chat-stream" port and posts {type:"chat", question}.
// We fetch /chat/stream, read the SSE body, and relay each event to the panel:
//   {type:"delta", text}  → append tokens
//   {type:"done", citations, grounded} → finalize
//   {type:"error", error, status} → show error
// The key travels only here (worker → backend), never to the panel.
async function streamChat(question, sourceTabIds, port) {
  const q = (question || "").trim();

  // Abort the upstream request if the panel disconnects mid-stream, so the
  // backend stops generating tokens (and spending the user's provider quota)
  // for an answer nobody is reading. Aborting also unblocks reader.read().
  const controller = new AbortController();
  let closed = false;
  port.onDisconnect.addListener(() => {
    closed = true;
    controller.abort();
  });
  const post = (msg) => {
    if (closed) return;
    try {
      port.postMessage(msg);
    } catch {
      // port already closed
    }
  };

  if (!q) {
    post({ type: "error", error: "Ask a question first." });
    return;
  }

  const { provider, apiKey, hasKey } = await getSettings();
  if (!hasKey) {
    post({
      type: "error",
      error: "No API key set. Add your provider key in Settings first.",
      status: 401,
    });
    return;
  }

  const session_id = await getSessionId();
  const body = { question: q, session_id, provider };
  if (Array.isArray(sourceTabIds) && sourceTabIds.length) {
    body.source_tab_ids = sourceTabIds;
  }

  let resp;
  try {
    resp = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        "X-Client-Token": await getClientToken(),
        "X-Provider-Key": apiKey,
      },
      body: JSON.stringify(body),
    });
  } catch (err) {
    if (err?.name === "AbortError") return; // panel closed before we connected
    post({
      type: "error",
      error: "Can't reach the TabSage backend. Make sure it's running, then try again.",
      status: 0,
    });
    return;
  }

  // Errors that happen before streaming starts come back as a normal JSON body.
  if (!resp.ok) {
    post({ type: "error", error: await describeBackendError(resp), status: resp.status });
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // Handle one complete SSE frame ("data: ...") — relay it to the panel.
  const handleFrame = (raw) => {
    const frame = raw.trim();
    if (!frame.startsWith("data:")) return;
    const payload = frame.slice(5).trim();
    if (!payload) return;
    let evt;
    try {
      evt = JSON.parse(payload);
    } catch {
      return;
    }
    if (evt.type === "error") {
      post({
        type: "error",
        error: evt.detail || "Something went wrong.",
        status: evt.status ?? null,
      });
    } else {
      post(evt); // delta | done
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Split on a CRLF-tolerant separator. The backend writes plain "\n\n"
      // frames today, but tolerating "\r\n\r\n" means a proxy or an
      // sse-starlette-style server that emits CRLF can't silently starve the
      // panel of every delta/done event.
      let m;
      const sepRe = /\r?\n\r?\n/;
      while ((m = sepRe.exec(buffer)) !== null) {
        handleFrame(buffer.slice(0, m.index));
        buffer = buffer.slice(m.index + m[0].length);
      }
    }
    // Flush any decoder state and a trailing frame the server sent without a
    // final blank line — otherwise the last event (usually "done", which
    // carries the citations) would be dropped when the read loop exits.
    buffer += decoder.decode();
    if (buffer.trim()) handleFrame(buffer);
  } catch (err) {
    // AbortError = panel closed; exit quietly. Anything else is a real break.
    if (err?.name !== "AbortError") {
      post({ type: "error", error: "The answer stream was interrupted.", status: 0 });
    }
    return;
  }
  post({ type: "end" });
}

// ── message router ────────────────────────────────────────────────────────
const HANDLERS = {
  ingestActiveTab: () => ingestActiveTab(),
  chat: (msg) => chat(msg.question, msg.sourceTabIds),
  resetSession: () => resetSession(),
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handler = message && HANDLERS[message.type];
  if (!handler) return false;

  Promise.resolve(handler(message))
    .then((result) => sendResponse({ ok: true, ...result }))
    .catch((err) =>
      sendResponse({
        ok: false,
        error: err?.message || String(err),
        status: err?.status ?? null,
      }),
    );
  return true; // keep the channel open for the async response
});

// Streaming chat uses a long-lived port so the worker can push many events.
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "chat-stream") return;
  port.onMessage.addListener((message) => {
    if (!message || message.type !== "chat") return;
    streamChat(message.question, message.sourceTabIds, port).catch((err) => {
      try {
        port.postMessage({
          type: "error",
          error: err?.message || String(err),
          status: err?.status ?? null,
        });
      } catch {
        // port already closed
      }
    });
  });
});

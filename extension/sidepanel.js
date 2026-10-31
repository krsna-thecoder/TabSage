/**
 * Side-panel chat behavior (Phase 8).
 *
 * The panel never calls the backend or reads the provider key directly. It
 * triggers actions by messaging the service worker (background.js) and renders
 * the non-secret results: added-tab chips, the conversation, answers, and
 * citations. Settings state (provider + whether a key exists) and the source
 * list are read reactively from chrome.storage.local.
 */
import { PRIVACY_POLICY_URL, PROVIDERS, STORAGE_KEYS } from "./config.js";
import {
  getPrivacyAccepted,
  getSettings,
  getSources,
  setPrivacyAccepted,
} from "./storage.js";
import { attachThemeMenu, initTheme } from "./theme.js";

const el = {
  needsKey: document.getElementById("needsKey"),
  ready: document.getElementById("ready"),
  providerName: document.getElementById("providerName"),
  conversation: document.getElementById("conversation"),
  messages: document.getElementById("messages"),
  sourcesBar: document.getElementById("sourcesBar"),
  sourcesList: document.getElementById("sourcesList"),
  resetButton: document.getElementById("resetButton"),
  composerHint: document.getElementById("composerHint"),
  addTabButton: document.getElementById("addTabButton"),
  askInput: document.getElementById("askInput"),
  sendButton: document.getElementById("sendButton"),
  openSettings: document.getElementById("openSettings"),
  addKeyButton: document.getElementById("addKeyButton"),
  themeButton: document.getElementById("themeButton"),
  themeMenu: document.getElementById("themeMenu"),
  consentOverlay: document.getElementById("consentOverlay"),
  consentAccept: document.getElementById("consentAccept"),
  consentCancel: document.getElementById("consentCancel"),
  consentPolicyLink: document.getElementById("consentPolicyLink"),
  privacyLink: document.getElementById("privacyLink"),
};

let hasKey = false;
let provider = "gemini";
let sources = [];
let busy = false;

function openSettings() {
  chrome.runtime.openOptionsPage();
}

function showConsent() {
  el.consentOverlay.classList.remove("hidden");
  el.consentAccept.focus();
}

function hideConsent() {
  el.consentOverlay.classList.add("hidden");
}

/**
 * Close the consent notice WITHOUT proceeding (Cancel / backdrop / dismiss) and
 * return focus to the control that opened it, so keyboard users aren't stranded
 * on a now-hidden button.
 */
function dismissConsent() {
  hideConsent();
  el.addTabButton.focus();
}

/** Send a message to the service worker and unwrap its {ok,...} envelope. */
async function sendToWorker(message) {
  const res = await chrome.runtime.sendMessage(message);
  if (!res) throw new Error("No response from the TabSage service worker.");
  if (!res.ok) throw new Error(res.error || "Something went wrong.");
  return res;
}

// ── rendering ─────────────────────────────────────────────────────────────
function hasMessages() {
  return el.messages.children.length > 0;
}

function renderShell() {
  el.needsKey.classList.toggle("hidden", hasKey);
  const showReady = hasKey && !hasMessages();
  el.ready.classList.toggle("hidden", !showReady);
  el.messages.classList.toggle("hidden", !hasMessages());

  if (hasKey) {
    const label = PROVIDERS[provider]?.label || provider;
    el.providerName.textContent = `Using ${label}`;
  }

  el.sourcesBar.classList.toggle("hidden", sources.length === 0);

  const canChat = hasKey && sources.length > 0 && !busy;
  el.addTabButton.disabled = !hasKey || busy;
  el.askInput.disabled = !canChat;
  el.sendButton.disabled = !canChat;

  el.composerHint.classList.remove("hidden");
  if (!hasKey) {
    el.composerHint.textContent = "Add an API key in Settings to begin.";
  } else if (sources.length === 0) {
    el.composerHint.textContent = "Add a tab with the + button to enable chat.";
  } else {
    el.composerHint.classList.add("hidden");
  }
}

function renderSources() {
  el.sourcesList.replaceChildren();
  for (const s of sources) {
    const chip = document.createElement("span");
    chip.className = "source-chip";
    chip.title = s.url || s.title || "";
    chip.textContent = s.title || s.url || "Untitled";
    el.sourcesList.appendChild(chip);
  }
}

function scrollToBottom() {
  el.conversation.scrollTop = el.conversation.scrollHeight;
}

function addUserMessage(text) {
  const node = document.createElement("div");
  node.className = "msg msg-user";
  node.textContent = text;
  el.messages.appendChild(node);
  renderShell();
  scrollToBottom();
}

function addSystemMessage(text) {
  const node = document.createElement("div");
  node.className = "msg msg-system";
  node.textContent = text;
  el.messages.appendChild(node);
  renderShell();
  scrollToBottom();
  return node;
}

function addPendingAssistant() {
  const node = document.createElement("div");
  node.className = "msg msg-assistant";
  const dots = document.createElement("div");
  dots.className = "typing";
  dots.append(
    document.createElement("span"),
    document.createElement("span"),
    document.createElement("span"),
  );
  node.appendChild(dots);
  el.messages.appendChild(node);
  renderShell();
  scrollToBottom();
  return node;
}

/**
 * Minimal, safe Markdown → HTML for assistant answers.
 *
 * Everything is HTML-escaped FIRST, then only the tags we generate are added,
 * so model output can never inject markup. Handles the formatting models
 * actually emit: headings, bold/italic, inline code, fenced code blocks,
 * bulleted and numbered lists, links, and paragraphs.
 */
function renderMarkdown(raw) {
  const esc = (s) =>
    s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const inline = (text) => {
    let s = esc(text);
    s = s.replace(/`([^`]+)`/g, (_m, c) => `<code>${c}</code>`);
    s = s.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (_m, t, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`,
    );
    s = s.replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
    return s;
  };

  const lines = String(raw ?? "").replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let list = null; // { tag: "ul" | "ol", items: [] }
  let para = [];
  let code = null; // array of raw lines while inside a ``` fence

  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${para.map(inline).join("<br>")}</p>`);
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      const items = list.items.map((i) => `<li>${inline(i)}</li>`).join("");
      out.push(`<${list.tag}>${items}</${list.tag}>`);
      list = null;
    }
  };

  for (const line of lines) {
    const isFence = line.trim().startsWith("```");

    if (code !== null) {
      if (isFence) {
        out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);
        code = null;
      } else {
        code.push(line);
      }
      continue;
    }
    if (isFence) {
      flushPara();
      flushList();
      code = [];
      continue;
    }

    const h = line.match(/^(#{1,3})\s+(.*)$/);
    const ul = line.match(/^\s*[*\-+]\s+(.*)$/);
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);

    if (h) {
      flushPara();
      flushList();
      const lvl = h[1].length;
      out.push(`<h${lvl}>${inline(h[2])}</h${lvl}>`);
    } else if (ul) {
      flushPara();
      if (list && list.tag !== "ul") flushList();
      if (!list) list = { tag: "ul", items: [] };
      list.items.push(ul[1]);
    } else if (ol) {
      flushPara();
      if (list && list.tag !== "ol") flushList();
      if (!list) list = { tag: "ol", items: [] };
      list.items.push(ol[1]);
    } else if (!line.trim()) {
      flushPara();
      flushList();
    } else {
      flushList();
      para.push(line);
    }
  }

  if (code !== null) out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);
  flushPara();
  flushList();
  return out.join("");
}

function renderStreaming(node, text) {
  node.className = "msg msg-assistant";
  let body = node.querySelector(".answer-text");
  if (!body) {
    node.replaceChildren(); // drop the typing dots on first token
    body = document.createElement("div");
    body.className = "answer-text";
    node.appendChild(body);
  }
  body.innerHTML = renderMarkdown(text);
  scrollToBottom();
}

function renderAnswer(node, { answer, citations, grounded }) {
  node.className = "msg msg-assistant";
  node.replaceChildren();

  const body = document.createElement("div");
  body.className = "answer-text" + (grounded ? "" : " answer-refusal");
  body.innerHTML = renderMarkdown(answer || "");
  node.appendChild(body);

  if (grounded && Array.isArray(citations) && citations.length) {
    const list = document.createElement("div");
    list.className = "citations";

    const heading = document.createElement("div");
    heading.className = "citations-heading";
    heading.textContent = citations.length === 1 ? "Source" : "Sources";
    list.appendChild(heading);

    citations.forEach((c, i) => {
      const item = document.createElement("div");
      item.className = "citation";

      const link = document.createElement("a");
      link.href = c.url || "#";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = `[${i + 1}] ${c.title || c.url || "Source"}`;
      item.appendChild(link);

      if (c.snippet) {
        const snip = document.createElement("p");
        snip.className = "citation-snippet";
        snip.textContent = c.snippet;
        item.appendChild(snip);
      }
      list.appendChild(item);
    });
    node.appendChild(list);
  }
  scrollToBottom();
}

function renderError(node, text) {
  node.className = "msg msg-error";
  node.replaceChildren();
  node.textContent = text;
  scrollToBottom();
}

/**
 * Finalize an answer that was cut off before its `done` event (stream ended or
 * the port disconnected mid-generation). We keep whatever partial text arrived
 * because it may still be useful, but we must NOT present it as a completed,
 * grounded answer: it has no citations and may stop mid-sentence. So it is
 * rendered in the non-grounded style and labelled as interrupted/incomplete.
 */
function renderInterrupted(node, text) {
  node.className = "msg msg-assistant";
  node.replaceChildren();

  const body = document.createElement("div");
  body.className = "answer-text answer-refusal";
  body.innerHTML = renderMarkdown(text || "");
  node.appendChild(body);

  const note = document.createElement("div");
  note.className = "answer-incomplete";
  note.textContent =
    "The answer was interrupted before it finished — it may be incomplete and its sources aren't available. Ask again to get a full, cited answer.";
  node.appendChild(note);
  scrollToBottom();
}

// ── actions ─────────────────────────────────────────────────────────────────
async function addCurrentTab() {
  if (busy || !hasKey) return;
  // Reserve the action BEFORE any await so two quick clicks can't both pass the
  // busy check while getPrivacyAccepted() is in flight and double-ingest the
  // same tab. Release it again if we have to stop and show the consent notice.
  busy = true;
  renderShell();

  // First-use privacy notice — gate the very first ingest until acknowledged.
  // Reading the stored flag can reject (storage unavailable); if it does we must
  // clear the reservation above and surface the error, or the add-tab and chat
  // controls stay disabled until the panel reloads.
  let accepted;
  try {
    accepted = await getPrivacyAccepted();
  } catch (err) {
    busy = false;
    renderShell();
    const node = addSystemMessage("");
    renderError(node, "Couldn't check your privacy settings. Please try again.");
    return;
  }
  if (!accepted) {
    busy = false;
    renderShell();
    showConsent();
    return;
  }

  const pending = addSystemMessage("Reading this tab…");
  try {
    const res = await sendToWorker({ type: "ingestActiveTab" });
    sources = await getSources();
    renderSources();
    const title = res.tab?.title || "this tab";
    const n = res.chunksIndexed ?? 0;
    pending.textContent = `Added “${title}” · ${n} passage${n === 1 ? "" : "s"} indexed.`;
  } catch (err) {
    renderError(pending, err.message || String(err));
  } finally {
    busy = false;
    renderShell();
  }
}

async function ask() {
  const question = el.askInput.value.trim();
  if (!question || busy || !hasKey || sources.length === 0) return;

  busy = true;
  el.askInput.value = "";
  addUserMessage(question);
  renderShell();

  const pending = addPendingAssistant();

  let acc = "";
  let settled = false;
  const finish = () => {
    if (settled) return;
    settled = true;
    busy = false;
    renderShell();
    el.askInput.focus();
  };

  let port;
  try {
    port = chrome.runtime.connect({ name: "chat-stream" });
  } catch {
    renderError(pending, "Can't reach the TabSage service worker.");
    finish();
    return;
  }

  port.onMessage.addListener((msg) => {
    if (!msg) return;
    if (msg.type === "delta") {
      acc += msg.text || "";
      renderStreaming(pending, acc);
    } else if (msg.type === "done") {
      renderAnswer(pending, {
        answer: acc,
        citations: msg.citations,
        grounded: msg.grounded,
      });
      try { port.disconnect(); } catch { /* already closed */ }
      finish();
    } else if (msg.type === "error") {
      renderError(pending, msg.error || "Something went wrong.");
      try { port.disconnect(); } catch { /* already closed */ }
      finish();
    } else if (msg.type === "end" && !settled) {
      // Stream closed without a done event — the answer never completed.
      if (acc) renderInterrupted(pending, acc);
      else renderError(pending, "No response from the backend.");
      finish();
    }
  });

  port.onDisconnect.addListener(() => {
    if (settled) return;
    if (acc) renderInterrupted(pending, acc);
    else renderError(pending, "The connection closed unexpectedly.");
    finish();
  });

  port.postMessage({ type: "chat", question });
}

async function resetSession() {
  if (busy) return;
  busy = true;
  renderShell();

  let notice = "Session reset. Add a tab to start again.";
  try {
    await sendToWorker({ type: "resetSession" });
  } catch (err) {
    notice = err.message || String(err);
  }

  sources = await getSources();
  el.messages.replaceChildren();
  renderSources();
  busy = false;
  renderShell();
  addSystemMessage(notice);
}

// ── load + events ─────────────────────────────────────────────────────────
async function refreshSettings() {
  const s = await getSettings();
  hasKey = s.hasKey;
  provider = s.provider;
}

async function start() {
  await initTheme();
  attachThemeMenu(el.themeButton, el.themeMenu);
  el.consentPolicyLink.href = PRIVACY_POLICY_URL;
  el.privacyLink.href = PRIVACY_POLICY_URL;
  await refreshSettings();
  sources = await getSources();
  renderSources();
  renderShell();
}

el.openSettings.addEventListener("click", openSettings);
el.addKeyButton.addEventListener("click", openSettings);
el.addTabButton.addEventListener("click", addCurrentTab);
el.sendButton.addEventListener("click", ask);
el.resetButton.addEventListener("click", resetSession);

el.consentAccept.addEventListener("click", async () => {
  await setPrivacyAccepted();
  hideConsent();
  addCurrentTab(); // continue the add the user started
});
el.consentCancel.addEventListener("click", dismissConsent);
el.consentOverlay.addEventListener("click", (event) => {
  if (event.target === el.consentOverlay) dismissConsent();
});
el.askInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    ask();
  }
});

chrome.storage.onChanged.addListener(async (changes, area) => {
  if (area !== "local") return;
  let dirty = false;

  if (changes[STORAGE_KEYS.apiKey] || changes[STORAGE_KEYS.provider]) {
    await refreshSettings();
    dirty = true;
  }
  if (changes[STORAGE_KEYS.sources]) {
    sources = await getSources();
    renderSources();
    dirty = true;
  }
  if (dirty) renderShell();
});

start();

/** Settings behavior: BYOK provider/key plus the shared header theme menu. */
import { PROVIDERS } from "./config.js";
import {
  clearApiKey,
  getSettings,
  maskKey,
  saveApiKey,
  saveProvider,
} from "./storage.js";
import { attachThemeMenu, initTheme } from "./theme.js";

const el = {
  form: document.getElementById("settingsForm"),
  provider: document.getElementById("provider"),
  apiKey: document.getElementById("apiKey"),
  toggleReveal: document.getElementById("toggleReveal"),
  getKeyLink: document.getElementById("getKeyLink"),
  clearBtn: document.getElementById("clearBtn"),
  status: document.getElementById("status"),
  keyBadge: document.getElementById("keyBadge"),
  keyBadgeText: document.getElementById("keyBadgeText"),
  themeButton: document.getElementById("themeButton"),
  themeMenu: document.getElementById("themeMenu"),
};

let hasStoredKey = false;

function populateProviders(selected) {
  el.provider.replaceChildren();
  for (const provider of Object.values(PROVIDERS)) {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = provider.label;
    option.selected = provider.id === selected;
    el.provider.appendChild(option);
  }
  updateProviderLink();
}

function updateProviderLink() {
  const provider = PROVIDERS[el.provider.value];
  if (!provider) return;
  el.getKeyLink.href = provider.keyUrl;
  el.getKeyLink.textContent = provider.linkText;
}

function setStatus(message, kind = "") {
  el.status.textContent = message;
  el.status.className = `status ${kind}`.trim();
}

function renderKeyState() {
  el.clearBtn.disabled = !hasStoredKey;
  el.keyBadge.classList.toggle("is-set", hasStoredKey);
  el.keyBadgeText.textContent = hasStoredKey ? "Configured" : "Not configured";
}

function remask(apiKey) {
  el.apiKey.value = "";
  el.apiKey.placeholder = hasStoredKey ? maskKey(apiKey) : "Paste your provider key";
  el.apiKey.type = "password";
  el.toggleReveal.textContent = "Show";
  el.toggleReveal.setAttribute("aria-pressed", "false");
}

async function load() {
  const settings = await getSettings();
  hasStoredKey = settings.hasKey;
  populateProviders(settings.provider);
  remask(settings.apiKey);
  renderKeyState();
  setStatus("");
}

el.provider.addEventListener("change", async () => {
  updateProviderLink();
  await saveProvider(el.provider.value);

  // Switching providers changes the embedding model, so the current session's
  // vectors are no longer comparable (see DOCUMENTATION §6). Reset the session:
  // the worker calls /sessions/reset, rotates the session id, and clears the
  // added-tab list, so the next tab starts a clean, consistent index.
  try {
    await chrome.runtime.sendMessage({ type: "resetSession" });
    setStatus("Provider saved. Session reset for the new model.", "ok");
  } catch {
    // Worker asleep or backend unreachable — the session id still rotates on
    // the next action, so correctness is preserved either way.
    setStatus("Provider saved. Add tabs again for the new model.", "ok");
  }
});

el.toggleReveal.addEventListener("click", () => {
  const isVisible = el.apiKey.type === "text";
  el.apiKey.type = isVisible ? "password" : "text";
  el.toggleReveal.textContent = isVisible ? "Show" : "Hide";
  el.toggleReveal.setAttribute("aria-pressed", String(!isVisible));
});

el.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveProvider(el.provider.value);

  const typed = el.apiKey.value.trim();
  if (typed) {
    await saveApiKey(typed);
    hasStoredKey = true;
    setStatus("API key saved.", "ok");
  } else if (hasStoredKey) {
    setStatus("No changes to API key.");
  } else {
    setStatus("Enter an API key to continue.", "err");
  }

  const { apiKey } = await getSettings();
  remask(apiKey);
  renderKeyState();
});

el.clearBtn.addEventListener("click", async () => {
  await clearApiKey();
  hasStoredKey = false;
  remask("");
  renderKeyState();
  setStatus("API key cleared.", "ok");
});

async function start() {
  await initTheme();
  attachThemeMenu(el.themeButton, el.themeMenu);
  await load();
}

start();

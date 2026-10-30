/**
 * Thin wrapper over chrome.storage.local for TabSage settings (ES module).
 *
 * The provider key lives only on the user's device. This module never sends it
 * anywhere. The service worker will be the sole backend caller in Phase 8.
 */
import {
  APPEARANCES,
  DEFAULT_APPEARANCE,
  DEFAULT_PROVIDER,
  STORAGE_KEYS,
} from "./config.js";

/** Read provider, key presence, and appearance. */
export async function getSettings() {
  const data = await chrome.storage.local.get([
    STORAGE_KEYS.provider,
    STORAGE_KEYS.apiKey,
    STORAGE_KEYS.appearance,
  ]);
  const apiKey = data[STORAGE_KEYS.apiKey] || "";
  const requestedAppearance = data[STORAGE_KEYS.appearance];
  const appearance = Object.hasOwn(APPEARANCES, requestedAppearance)
    ? requestedAppearance
    : DEFAULT_APPEARANCE;

  return {
    provider: data[STORAGE_KEYS.provider] || DEFAULT_PROVIDER,
    apiKey,
    hasKey: Boolean(apiKey),
    appearance,
  };
}

/** Persist the chosen provider. */
export async function saveProvider(provider) {
  await chrome.storage.local.set({ [STORAGE_KEYS.provider]: provider });
}

/** Persist the provider key (trimmed). Empty/blank clears it. */
export async function saveApiKey(apiKey) {
  const trimmed = (apiKey || "").trim();
  if (!trimmed) {
    await clearApiKey();
    return;
  }
  await chrome.storage.local.set({ [STORAGE_KEYS.apiKey]: trimmed });
}

/** Remove the stored key from the device. */
export async function clearApiKey() {
  await chrome.storage.local.remove(STORAGE_KEYS.apiKey);
}

/** Persist System/Light/Dark. Unknown values are rejected. */
export async function saveAppearance(appearance) {
  if (!Object.hasOwn(APPEARANCES, appearance)) {
    throw new TypeError(`Unsupported appearance: ${appearance}`);
  }
  await chrome.storage.local.set({ [STORAGE_KEYS.appearance]: appearance });
}

/** Mask a key for display without rendering the full secret. */
export function maskKey(apiKey) {
  const k = (apiKey || "").trim();
  if (!k) return "";
  if (k.length <= 8) return "•".repeat(k.length);
  return `${k.slice(0, 4)}${"•".repeat(Math.min(16, k.length - 8))}${k.slice(-4)}`;
}


/**
 * The TabSage session id lives only on the device. The service worker sends it
 * on every /ingest and /chat so the backend scopes one study session's tabs
 * together. It is generated lazily on first use.
 */
export async function getSessionId() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.sessionId);
  let id = data[STORAGE_KEYS.sessionId];
  if (!id) {
    id = crypto.randomUUID();
    await chrome.storage.local.set({ [STORAGE_KEYS.sessionId]: id });
  }
  return id;
}

/** Rotate to a fresh session id. Used on reset and on provider switch. */
export async function resetSessionId() {
  const id = crypto.randomUUID();
  await chrome.storage.local.set({ [STORAGE_KEYS.sessionId]: id });
  return id;
}

/** The added-tab list for the current session (display only; never secret). */
export async function getSources() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.sources);
  const list = data[STORAGE_KEYS.sources];
  return Array.isArray(list) ? list : [];
}

/** Add or replace a source by tab_id, returning the updated list. */
export async function addSource(source) {
  const list = await getSources();
  const next = list.filter((s) => s.tab_id !== source.tab_id);
  next.push({ tab_id: source.tab_id, title: source.title, url: source.url });
  await chrome.storage.local.set({ [STORAGE_KEYS.sources]: next });
  return next;
}

/** Drop the whole source list (on reset / provider switch). */
export async function clearSources() {
  await chrome.storage.local.remove(STORAGE_KEYS.sources);
}

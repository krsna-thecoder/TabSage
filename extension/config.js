/**
 * TabSage shared configuration (ES module).
 *
 * One place to flip the backend between local dev and production, plus the
 * constants every other script shares (storage keys, providers). Imported by
 * the service worker, the settings page, and the side panel.
 *
 * ⚠️ No secrets live here. The user's provider key is entered in Settings and
 *    stored only in chrome.storage.local (see STORAGE_KEYS below). It is NEVER
 *    hard-coded, bundled, or committed.
 */

// Flip this to switch the single configurable API base URL.
//   "dev"  → local FastAPI backend
//   "prod" → deployed HTTPS backend (set the real host before publishing)
// NOTE: whatever origin is active here must also be allowed by
// `host_permissions` in manifest.json (dev: http://localhost:8000/*).
export const ENV = "dev";

const API_BASE_URLS = {
  dev: "http://localhost:8000",
  // Placeholder — replaced with the real HTTPS endpoint in Phase 13.
  prod: "https://api.tabsage.example",
};

/** The active backend base URL (no trailing slash). */
export const API_BASE_URL = API_BASE_URLS[ENV];

/** Keys used in chrome.storage.local. Centralized so they never drift. */
export const STORAGE_KEYS = Object.freeze({
  provider: "tabsage.provider",
  apiKey: "tabsage.apiKey",
  sessionId: "tabsage.sessionId",
  clientToken: "tabsage.clientToken",
  sources: "tabsage.sources",
  appearance: "tabsage.appearance",
});

/** Appearance preferences. `system` follows the operating-system setting. */
export const APPEARANCES = Object.freeze({
  system: { id: "system", label: "System" },
  light: { id: "light", label: "Light" },
  dark: { id: "dark", label: "Dark" },
});

/** New installs follow the operating system until the user chooses otherwise. */
export const DEFAULT_APPEARANCE = APPEARANCES.system.id;

/** Supported BYOK providers. Values must match the backend `Provider` enum. */
export const PROVIDERS = Object.freeze({
  gemini: {
    id: "gemini",
    label: "Google Gemini (free tier)",
    keyUrl: "https://aistudio.google.com/app/apikey",
    keyHint: "Create a free API key in Google AI Studio.",
    linkText: "Get a free key in Google AI Studio",
  },
  openai: {
    id: "openai",
    label: "OpenAI (paid)",
    keyUrl: "https://platform.openai.com/api-keys",
    keyHint: "Create an API key in the OpenAI dashboard (billing required).",
    linkText: "Get a key in the OpenAI dashboard",
  },
});

/** Default provider when the user hasn't chosen one yet. */
export const DEFAULT_PROVIDER = PROVIDERS.gemini.id;

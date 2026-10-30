# extension/

Manifest V3 Chrome extension (vanilla JS, ES modules). Only the contents of
this folder are zipped and submitted to the Chrome Web Store.

## Files (Phase 8 — scrape on user action + wired to the backend)

| File | Role |
|---|---|
| `manifest.json` | MV3 manifest. Perms: `storage`, `activeTab`, `scripting`, `sidePanel`. `host_permissions` cover the dev API (`http://localhost:8000/*`) **and** page origins (`http://*/*`, `https://*/*`) so the worker can read a tab the user adds. Least privilege is preserved by behavior: the extractor runs only on the "Add this tab" click. |
| `config.js` | Single configurable API base URL (`ENV` = `dev`/`prod`) + shared storage-key/provider constants. **No secrets.** |
| `theme.css` | Neutral light/dark tokens and shared controls for the restrained chat UI. Flat colors only; no gradients or CSS framework. |
| `theme.js` | Applies persistent System/Light/Dark appearance, follows OS changes in System mode, and manages the side-panel appearance menu. |
| `storage.js` | Thin wrapper over `chrome.storage.local` for provider, key, and appearance, plus the session id (`getSessionId`/`resetSessionId`) and the added-tab list (`getSources`/`addSource`/`clearSources`). |
| `settings.html/.css/.js` | Neutral BYOK settings with the same product header and appearance menu as the side panel; provider, masked key save/clear, and provider-key link. Switching provider resets the session (embedding consistency). |
| `content.js` | Visible-text extractor (`document.body.innerText`). **Not** declared in the manifest — the worker injects it with `chrome.scripting.executeScript` only when the user clicks "Add this tab". No network, no key access. |
| `sidepanel.html/.css/.js` | Chat UI: a sources bar of added-tab chips + Reset, a scrolling conversation with answers and **citations**, and a composer that enables once a key is set and at least one tab is added. Messages the worker; never calls the backend directly. |
| `background.js` | Service worker (ES module) — the **only** backend caller. Reads the key from `chrome.storage.local`, attaches it as `X-Provider-Key`, and handles `ingestActiveTab` / `chat` / `resetSession` with friendly "no key / invalid key / backend down" errors. The key is never returned to any page. |
| `icons/` | `icon16/48/128.png` (regenerate with `backend/scripts/make_icons.py`). |

## Load unpacked (dev)

1. Open `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** → select this `extension/` folder.
3. Click the TabSage toolbar icon to open the side panel. Use the monitor/sun/moon icon for appearance and the sliders icon for Settings.

The provider key is stored only in `chrome.storage.local` on your device and is
never bundled, committed, or sent anywhere except your chosen provider (via the
backend) in later phases.

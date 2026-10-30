/**
 * Persistent appearance support shared by the side panel and Settings.
 *
 * Default behavior needs no JavaScript: theme.css follows prefers-color-scheme.
 * This module applies an explicit Light/Dark override when selected, listens for
 * OS changes while in System mode, syncs open extension pages through
 * chrome.storage.onChanged, and manages the compact theme popover.
 */
import { APPEARANCES, DEFAULT_APPEARANCE, STORAGE_KEYS } from "./config.js";
import { getSettings, saveAppearance } from "./storage.js";

const darkMedia = window.matchMedia("(prefers-color-scheme: dark)");

function validAppearance(value) {
  return Object.hasOwn(APPEARANCES, value) ? value : DEFAULT_APPEARANCE;
}

export function resolvedTheme(appearance) {
  const choice = validAppearance(appearance);
  if (choice === "system") return darkMedia.matches ? "dark" : "light";
  return choice;
}

/** Apply a preference and record both the preference and resolved color mode. */
export function applyAppearance(appearance) {
  const choice = validAppearance(appearance);
  const resolved = resolvedTheme(choice);
  const root = document.documentElement;
  root.dataset.appearance = choice;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  window.dispatchEvent(
    new CustomEvent("tabsage:appearance", { detail: { appearance: choice, resolved } }),
  );
  return { appearance: choice, resolved };
}

/** Initialize from storage and keep this page synchronized. */
export async function initTheme() {
  const { appearance } = await getSettings();
  applyAppearance(appearance);

  darkMedia.addEventListener("change", () => {
    if (document.documentElement.dataset.appearance === "system") {
      applyAppearance("system");
    }
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes[STORAGE_KEYS.appearance]) {
      applyAppearance(changes[STORAGE_KEYS.appearance].newValue);
    }
  });

  return appearance;
}

/**
 * Wire a button + menu containing `[data-appearance]` option buttons.
 * The selected option gets `aria-checked=true`; `data-theme-icon` elements on
 * the trigger are switched among system/sun/moon without replacing DOM.
 */
export function attachThemeMenu(trigger, menu) {
  if (!trigger || !menu) return;

  const setOpen = (open) => {
    menu.classList.toggle("hidden", !open);
    trigger.setAttribute("aria-expanded", String(open));
  };

  const render = () => {
    const appearance = validAppearance(
      document.documentElement.dataset.appearance || DEFAULT_APPEARANCE,
    );
    const resolved = resolvedTheme(appearance);

    for (const option of menu.querySelectorAll("[data-appearance]")) {
      const selected = option.dataset.appearance === appearance;
      option.setAttribute("aria-checked", String(selected));
      option.classList.toggle("is-selected", selected);
      const check = option.querySelector("[data-check]");
      if (check) check.classList.toggle("hidden", !selected);
    }

    for (const icon of trigger.querySelectorAll("[data-theme-icon]")) {
      // Explicit modes use sun/moon. System always keeps the monitor icon so
      // the button communicates that it follows the OS, independent of result.
      const wanted = appearance === "system" ? "system" : resolved;
      icon.classList.toggle("hidden", icon.dataset.themeIcon !== wanted);
    }
    trigger.title = `Appearance: ${APPEARANCES[appearance].label}`;
    trigger.setAttribute("aria-label", `Appearance: ${APPEARANCES[appearance].label}`);
  };

  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    setOpen(menu.classList.contains("hidden"));
  });

  menu.addEventListener("click", async (event) => {
    const option = event.target.closest("[data-appearance]");
    if (!option) return;
    const appearance = validAppearance(option.dataset.appearance);
    await saveAppearance(appearance);
    applyAppearance(appearance);
    render();
    setOpen(false);
    trigger.focus();
  });

  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target) && event.target !== trigger) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setOpen(false);
      trigger.focus();
    }
  });
  window.addEventListener("tabsage:appearance", render);
  render();
}

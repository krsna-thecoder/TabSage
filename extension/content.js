/**
 * TabSage content script — visible-text extractor.
 *
 * NOT declared in the manifest. The service worker injects it with
 * chrome.scripting.executeScript ONLY when the user clicks "Add this tab", so a
 * page is read exclusively on a deliberate gesture. It makes NO network calls
 * and never sees the provider key (the key stays in the service worker).
 *
 * Performance: `innerText` forces a layout pass, so it is called EXACTLY ONCE,
 * on the best single container. We prefer the main article region (dropping
 * nav/footer/banner noise so there's less to embed) and fall back to the whole
 * body when there's no recognizable main region, so nothing is ever missed.
 *
 * The trailing expression is the script's completion value, which executeScript
 * hands back to the worker as `result`.
 */
(() => {
  const title = (document.title || "").trim();
  const url = location.href;

  const main =
    document.querySelector("article") ||
    document.querySelector("main") ||
    document.querySelector("[role='main']") ||
    document.body;

  const text = main ? (main.innerText || "").trim() : "";

  return { title, url, text };
})();

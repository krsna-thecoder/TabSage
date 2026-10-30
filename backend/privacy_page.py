"""Self-contained HTML for the public privacy policy (served at GET /privacy).

Kept as one string so it ships with the backend and gives a stable public URL
(e.g. https://<your-host>/privacy) for the Chrome Web Store listing — no extra
static hosting needed. Mirrors PRIVACY.md at the repo root.
"""
from __future__ import annotations

PRIVACY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>TabSage — Privacy Policy</title>
<style>
  :root { color-scheme: light dark; }
  body { max-width: 760px; margin: 40px auto; padding: 0 20px;
         font: 16px/1.6 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         color: #1a1a1a; background: #fff; }
  @media (prefers-color-scheme: dark) { body { color: #e8e8e8; background: #141414; } }
  h1 { font-size: 28px; margin-bottom: 4px; }
  h2 { font-size: 19px; margin-top: 32px; }
  .eff { color: #888; margin-top: 0; }
  code { background: rgba(127,127,127,.18); padding: 1px 5px; border-radius: 4px; }
  ul { padding-left: 22px; }
  li { margin: 6px 0; }
  .lead { border-left: 3px solid #888; padding-left: 14px; }
</style>
</head>
<body>
<h1>TabSage Privacy Policy</h1>
<p class="eff">Effective date: 30 October 2026</p>

<p class="lead">TabSage reads a page only when you click <strong>"Add this
tab,"</strong> uses <strong>your own AI provider key</strong>, and does
<strong>not</strong> sell, advertise with, or train models on your content.</p>

<h2>Who processes your data</h2>
<ul>
  <li><strong>The TabSage extension</strong>, running in your browser.</li>
  <li><strong>The TabSage backend</strong>, an HTTPS API that performs retrieval.
      It is <em>stateless about secrets</em> — it never stores your API key.</li>
  <li><strong>Your chosen AI provider</strong> — Google Gemini (default) or
      OpenAI — accessed with <strong>your own API key</strong> (BYOK).</li>
</ul>

<h2>What data is processed</h2>
<ul>
  <li><strong>Selected page content</strong> — a tab's visible text, read only
      when you click "Add this tab." TabSage never reads tabs in the background
      or several tabs at once.</li>
  <li><strong>Page title and URL</strong> — to label and link citations.</li>
  <li><strong>Your questions</strong> — the text you ask.</li>
  <li><strong>A session id</strong> — a random id grouping one study session.</li>
  <li><strong>A random installation identifier</strong> — used only to
      rate-limit abuse; it identifies this browser installation and can link
      that installation's requests, and is not tied to your personal identity.</li>
  <li><strong>Your provider API key</strong> — see "How your API key is handled."</li>
</ul>

<h2>How your data flows</h2>
<ul>
  <li>Your key is saved <strong>only in your browser</strong>
      (<code>chrome.storage.local</code>).</li>
  <li>Added page text/title/URL are sent over <strong>HTTPS</strong> to the backend.</li>
  <li>The backend uses <strong>your key</strong> to create embeddings via your
      provider, stored <strong>only for your session</strong>.</li>
  <li>On a question, the backend retrieves the most relevant passages and sends
      them with your question to your provider to generate an answer.</li>
  <li>The answer and citations are returned and shown to you.</li>
</ul>

<h2>How your API key is handled</h2>
<ul>
  <li>Stored <strong>only on your device</strong>; viewable masked and removable
      any time via <strong>Clear key</strong> in Settings.</li>
  <li>Sent over HTTPS per request, used <strong>transiently in memory</strong> to
      call your provider, then discarded.</li>
  <li><strong>Never</strong> stored server-side, written to a database, or logged,
      and never included in error messages, source, or screenshots.</li>
  <li>Honest limitation: the key <em>passes through</em> the backend in memory on
      each request, so a compromised backend could observe it in transit.
      Mitigations: HTTPS, minimal dependencies, and never logging headers/bodies.
      There is no store of keys at rest.</li>
</ul>

<h2>Storage and retention</h2>
<ul>
  <li>Session vector data is <strong>ephemeral and in-memory</strong>; nothing is
      written to disk by default.</li>
  <li>Removed on <strong>Reset</strong>, on provider switch, automatically after
      inactivity (short session TTL), and if the backend restarts.</li>
  <li><strong>Raw page text and API keys are never logged.</strong> Access logs
      record only method, path, status, latency, and caller IP.</li>
</ul>

<h2>What TabSage does not do</h2>
<ul>
  <li>Does <strong>not</strong> sell your data or share it for advertising.</li>
  <li>Does <strong>not</strong> use your content or questions to train any model.</li>
  <li>Does <strong>not</strong> read tabs you have not explicitly added.</li>
</ul>

<h2>Third parties</h2>
<ul>
  <li><strong>Your AI provider (Google Gemini or OpenAI)</strong> processes what
      you send, under your account and their terms — review their policies.</li>
  <li><strong>Hosting:</strong> the backend runs on a cloud host (AWS) solely to
      serve the API.</li>
</ul>

<h2>Your choices and controls</h2>
<ul>
  <li><strong>Add tabs deliberately</strong> — nothing is read until you click
      "Add this tab."</li>
  <li><strong>Reset</strong> clears the session's tabs, chat, and passages.</li>
  <li><strong>Clear key</strong> removes your API key from your device.</li>
  <li><strong>Uninstall</strong> removes all TabSage data in your browser.</li>
</ul>

<h2>Children</h2>
<p>TabSage is not directed to children and does not knowingly collect data from
children.</p>

<h2>Changes</h2>
<p>We may update this policy; the effective date above will change accordingly.</p>

<h2>Contact</h2>
<p>Questions: <strong>REPLACE_WITH_YOUR_CONTACT_EMAIL</strong></p>
</body>
</html>
"""

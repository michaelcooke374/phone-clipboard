"use strict";
// The iPhone's page: copy the computer's text, send text to the computer, set up the shortcuts.
// The key comes from the address (/p/<key>), which the QR code on the computer gives.

const $ = (id) => document.getElementById(id);
const match = location.pathname.match(/^\/p\/([A-Za-z0-9_-]{16,64})\/?$/);
const key = match ? match[1] : null;
let pcText = "";
let toastTimer = 0;
let loading = false;

function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3000);
}

function problem(title, text) {
  const p = $("problem");
  const b = document.createElement("b");
  b.textContent = title;
  const d = document.createElement("div");
  d.textContent = text;
  p.replaceChildren(b, d);
  p.hidden = false;
}

// Copies text on the iPhone. The page is http on the home network, where Safari doesn't offer
// the newer clipboard API, so the classic way is used: select a hidden box and "copy".
function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).catch(() => legacyCopy(text));
    return true;
  }
  return legacyCopy(text);
}

function legacyCopy(text) {
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("aria-hidden", "true");
  box.className = "offscreen";
  document.body.append(box);
  box.contentEditable = "true";
  box.readOnly = false;
  const range = document.createRange();
  range.selectNodeContents(box);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  box.setSelectionRange(0, text.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (e) {
    ok = false;
  }
  selection.removeAllRanges();
  box.remove();
  return ok;
}

async function call(method, text) {
  const options = { method, cache: "no-store", headers: {} };
  if (text !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify({ text });
  }
  const r = await fetch(`/c/${key}?json=1`, options);
  let data = {};
  try {
    data = await r.json();
  } catch (e) { /* not JSON */ }
  return { status: r.status, ok: r.ok && data.ok === true, data };
}

function oldKey() {
  $("app").hidden = true;
  $("state").textContent = "Not connected.";
  problem("This link has an old key.",
    "A new key was made on the computer. On the computer, open Phone Clipboard (Start menu) and scan the new code with the iPhone's Camera.");
}

async function refresh(showToast) {
  if (loading) return;
  loading = true;
  try {
    const r = await call("GET");
    if (r.status === 403) return oldKey();
    if (!r.ok) {
      $("state").textContent = r.data.message || "The computer couldn't read its clipboard. Try Refresh.";
      return;
    }
    $("problem").hidden = true;
    $("app").hidden = false;
    $("state").textContent = "Connected to your computer.";
    pcText = r.data.text || "";
    $("from-pc").value = pcText;
    if (!r.data.has_text) {
      $("from-pc").placeholder = "The computer's clipboard has no text. Copy some text there, then tap Refresh.";
    }
    if (showToast) toast(r.data.has_text ? "Got the computer's text." : "The computer's clipboard has no text.");
  } catch (e) {
    $("state").textContent = "Can't reach the computer.";
    problem("Can't reach your computer.",
      "Check that the iPhone is on the same Wi-Fi as the computer, and that the computer is on and awake. Then tap Refresh or reload this page.");
  } finally {
    loading = false;
  }
}

// The shortcuts' address: the computer's name ("desktop-xyz.local") keeps working when its number
// address changes, so it's used when the iPhone can reach the computer by that name.
async function pickAddress() {
  const port = location.port || "80";
  let base = location.origin;
  let byName = location.hostname.endsWith(".local");
  if (!byName) {
    try {
      const info = await (await fetch("/api/ping", { cache: "no-store" })).json();
      if (info.name) {
        const stop = new AbortController();
        const timer = setTimeout(() => stop.abort(), 2500);
        const r = await fetch(`http://${info.name}:${port}/api/ping`, { cache: "no-store", signal: stop.signal });
        clearTimeout(timer);
        if ((await r.json()).app === "phone-clipboard") {
          base = `http://${info.name}:${port}`;
          byName = true;
        }
      }
    } catch (e) { /* the name doesn't work on this network: use the number address */ }
  }
  $("shortcut-link").value = `${base}/c/${key}`;
  $("link-note").textContent = byName
    ? "This address uses your computer's name, so it keeps working even if the computer's number address changes."
    : "This address uses your computer's number address. Home routers usually keep it the same. If the shortcuts stop connecting one day, scan the code on the computer again and update the address in both.";
}

function start() {
  if (!key) {
    $("state").textContent = "Not connected.";
    problem("Open this page from your computer.",
      "On the computer, open Phone Clipboard (Start menu), then point the iPhone's Camera at the code on that page and tap the link.");
    return;
  }
  $("refresh").addEventListener("click", () => refresh(true));
  $("copy").addEventListener("click", () => {
    if (!pcText) {
      toast("Nothing to copy yet. Copy text on the computer, then tap Refresh.");
      return;
    }
    if (copyText(pcText)) {
      toast("Copied. Paste it anywhere on the iPhone.");
    } else {
      const box = $("from-pc");
      box.focus();
      box.setSelectionRange(0, box.value.length);
      toast("Tap Copy in the menu to copy the selected text.");
    }
  });
  $("send").addEventListener("click", async () => {
    const text = $("to-pc").value;
    if (!text) {
      toast("Tap the box, then Paste, first.");
      return;
    }
    $("send").disabled = true;
    try {
      const r = await call("POST", text);
      if (r.status === 403) return oldKey();
      toast(r.data.message || (r.ok ? "Sent." : "That didn't work. Try again."));
    } catch (e) {
      toast("Can't reach the computer. Is it on, awake, and on the same Wi-Fi?");
    } finally {
      $("send").disabled = false;
    }
  });
  $("clear").addEventListener("click", () => { $("to-pc").value = ""; });
  $("copy-link").addEventListener("click", () => {
    const input = $("shortcut-link");
    if (copyText(input.value)) {
      toast("Address copied. Now paste it into the shortcut.");
    } else {
      input.focus();
      input.setSelectionRange(0, input.value.length);
      toast("Tap Copy in the menu to copy the address.");
    }
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(false); });
  $("shortcut-link").value = `${location.origin}/c/${key}`;
  refresh(false).then(pickAddress);
}

start();

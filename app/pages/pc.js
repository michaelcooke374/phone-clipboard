"use strict";
// The computer's set-up page: QR code, warnings, texts from the iPhone, settings.

const $ = (id) => document.getElementById(id);
let status = null;
let qrVersion = 0;
let toastTimer = 0;

function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}

function ago(seconds) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - seconds));
  if (s < 45) return "just now";
  if (s < 90) return "a minute ago";
  if (s < 3600) return Math.round(s / 60) + " minutes ago";
  if (s < 5400) return "an hour ago";
  if (s < 86400) return Math.round(s / 3600) + " hours ago";
  return new Date(seconds * 1000).toLocaleString();
}

async function load(fresh) {
  try {
    const r = await fetch("/pc/status" + (fresh ? "?fresh=1" : ""), { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    status = await r.json();
  } catch (e) {
    $("state").textContent = "Phone Clipboard isn't running. Start it again: click Start, type Phone Clipboard, press Enter.";
    return;
  }
  render();
}

function addressLabel(a) {
  const where = [a.adapter, a.name && a.name !== a.adapter ? a.name : ""].filter(Boolean).join(", ");
  return where ? `${a.ip} (${where})` : a.ip;
}

function render() {
  const s = status;
  $("state").textContent = s.best
    ? `Running. Your iPhone reaches this computer at ${s.best}.`
    : "Running, but this computer isn't connected to a network.";
  if (!s.windows_checked) $("state").textContent += " (Windows' network settings couldn't be checked.)";

  const w = $("warnings");
  w.replaceChildren();
  for (const x of s.warnings) {
    const box = el("div", "warning");
    box.append(el("b", null, x.title), el("div", null, x.text));
    w.append(box);
  }

  // The address the QR code uses: the best one, unless another was picked.
  const select = $("host");
  const chosen = select.value;
  const choices = s.addresses.map((a) => [a.ip, addressLabel(a)]);
  if (s.name) choices.push([s.name, `${s.name} (this computer's name)`]);
  if (select.dataset.choices !== JSON.stringify(choices)) {    // rebuilt only when changed (keeps it open)
    select.dataset.choices = JSON.stringify(choices);
    select.replaceChildren(...choices.map(([value, label]) => {
      const o = el("option", null, label);
      o.value = value;
      return o;
    }));
  }
  select.value = choices.some(([v]) => v === chosen) ? chosen : (s.best || "");
  $("address-choice").hidden = choices.length < 2;
  const src = `/pc/qr.svg?host=${encodeURIComponent(select.value)}&v=${qrVersion}`;
  if ($("qr").getAttribute("src") !== src) $("qr").setAttribute("src", src);

  $("last-phone").textContent = s.last_phone
    ? `Your iPhone last connected ${ago(s.last_phone.time)} (from ${s.last_phone.ip}).`
    : "No iPhone has connected since Phone Clipboard started.";
  const refused = s.last_refused;
  $("last-refused").hidden = !refused;
  if (refused) {
    $("last-refused").textContent = `A link or shortcut with an old key was turned away ${ago(refused.time)} (from ${refused.ip}). ` +
      "If that was your iPhone, scan the code above again and put the new address in both shortcuts.";
  }

  $("version").textContent = `Phone Clipboard ${s.version} on ${s.computer}, port ${s.port}.`;
  const list = $("recent");
  // Rebuilt only when something new arrived (or once a minute, for the times), so pictures don't flicker.
  const signature = JSON.stringify([s.from_phone.map((e) => e.id), Math.floor(Date.now() / 60000)]);
  if (list.dataset.signature === signature) return;
  list.dataset.signature = signature;
  list.replaceChildren();
  if (!s.from_phone.length) list.append(el("li", "muted", "Nothing yet."));
  for (const item of s.from_phone) {
    const li = el("li");
    const copy = el("button", "secondary", "Copy");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try {
        await post(`/pc/copy/${item.id}`);
        toast("Copied. Paste with Ctrl+V.");
      } catch (e) {
        toast(item.kind === "text" ? "Couldn't copy. Select the text and press Ctrl+C." : "Couldn't copy. Open the pictures folder instead.");
      }
    });
    if (item.kind === "picture") {
      const img = el("img", "thumb");
      img.src = `/pc/picture/${item.id}`;
      img.alt = item.name;
      const about = el("div", "text", `${item.name}\n${item.width} x ${item.height}, ${ago(item.time)}`);
      const show = el("button", "secondary", "Show");
      show.type = "button";
      show.title = "Show it in File Explorer";
      show.addEventListener("click", () => post(`/pc/show/${item.id}`).catch(() => toast("Couldn't open File Explorer.")));
      const actions = el("div", "actions");
      actions.append(copy, show);
      li.append(img, about, actions);
    } else {
      const text = el("div", "text", item.text);
      text.title = ago(item.time);
      li.append(text, copy);
    }
    list.append(li);
  }
}

async function post(path) {
  const r = await fetch(path, { method: "POST", cache: "no-store" });
  if (!r.ok) throw new Error(String(r.status));
}

$("host").addEventListener("change", render);
$("open-folder").addEventListener("click", () => post("/pc/open-folder").catch(() => toast("Couldn't open the folder.")));
$("check").addEventListener("click", async () => {
  $("state").textContent = "Checking...";
  await load(true);
  toast("Checked.");
});
$("new-key").addEventListener("click", async () => {
  if (!confirm("Make a new key? Your iPhone's links and shortcuts stop working until you set it up again with the new code.")) return;
  try {
    await post("/pc/new-key");
    qrVersion++;
    await load(false);
    toast("New key made. Scan the new code with your iPhone.");
  } catch (e) {
    toast("That didn't work. Try again.");
  }
});
$("stop").addEventListener("click", async () => {
  if (!confirm("Stop Phone Clipboard? Your iPhone can't reach this computer until it starts again (from the Start menu, or the next time you sign in).")) return;
  try {
    await post("/pc/stop");
  } catch (e) { /* it may stop before answering */ }
  clearInterval(timer);
  $("state").textContent = "Stopped. To start it again: click Start, type Phone Clipboard, press Enter.";
});

load(false);
const timer = setInterval(() => { if (!document.hidden) load(false); }, 10000);

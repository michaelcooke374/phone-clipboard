# PasteBridge protocol, version 1

How the iPhone app ("the phone") and the Windows app ("the bridge") talk. Both apps are
built from this document; when they disagree, this document wins (or gets fixed).

Draft, October 2026. "PasteBridge" is the working name.

---

## 1. Roles and the network

- The **bridge** (Windows) is a small HTTPS server. It listens on every network of the PC,
  IPv4 and IPv6, on TCP port **47820** (if that's taken: 47821 to 47829; the port in use is
  announced by discovery and the pairing code).
- The **phone** (iPhone) always starts the conversation. iOS doesn't let apps listen in the
  background, so the bridge never connects to the phone.
- The Windows firewall rule comes with the MSIX package (`windows.firewallRules`, profile
  `domainAndPrivate`): private and work networks only, never public Wi-Fi.
- Everything is on the local network. Nothing goes through a server of ours. (A later
  "notifications" feature may add one for a content-free "something is waiting" signal;
  it would get its own section here.)

## 2. Security

- **TLS everywhere**, version 1.2 or later (1.3 where both sides support it), including
  `hello` and pairing.
- **The bridge's identity** is a self-signed ECDSA P-256 certificate made on first start and
  kept for good (protected with Windows DPAPI for the current user). Its **fingerprint** is
  the SHA-256 of the certificate's DER bytes, written in base64url without padding
  (43 characters).
- **The phone pins that fingerprint** at pairing and accepts no other certificate from that
  bridge, whatever its address. A mismatch is never accepted silently: the phone says "This
  PC's identity has changed. Pair again from the PC." (it happens after reinstalling the
  bridge).
- **Each phone has its own token**: 32 random bytes, base64url (43 characters), sent as
  `Authorization: Bearer <token>`. The bridge keeps only the token's SHA-256, so its saved
  data can't be used to impersonate a phone. Removing a phone in the bridge deletes its
  token hash; that phone's next request gets 401.
- **Limits:** at most 10 pairing attempts and 30 failed token checks per minute per
  address, then 429 for a minute. Pairing codes are single-use and expire after 10 minutes.
- **Never logged:** clipboard content, file names, tokens, pairing codes. The bridge's log
  may hold times, sizes, kinds, addresses and phone names.

## 3. Discovery

- The bridge announces itself with DNS-SD over multicast DNS (Windows' own
  `DnsServiceRegister`, Windows 10 and later; no Apple Bonjour needed):
  - service type `_pastebridge._tcp`, domain `local.`
  - instance name: the PC's display name (from the bridge's settings; default: Windows'
    computer name)
  - port: the port in use
  - TXT: `v=1`, `id=<pc_id>`
- The phone browses for `_pastebridge._tcp` (Network framework `NWBrowser`; Info.plist
  lists the service in `NSBonjourServices` and explains local network use in
  `NSLocalNetworkUsageDescription`) and picks the instance whose `id` matches its paired PC.
- Order the phone tries: the last address that worked, then what discovery finds, then the
  addresses from the pairing code. Each attempt: `GET /v1/hello`, 2 seconds timeout.
- `pc_id`: 16 random bytes, base64url (22 characters), made with the certificate.

## 4. Pairing

The bridge shows a QR code (and the same text for copying). The text is a link:

```
https://pastebridge.app/pair#v=1&id=<pc_id>&n=<name>&a=<addresses>&f=<fingerprint>&c=<code>
```

- Everything after `#` stays on the device (browsers don't send it to the website). If the
  app is installed, the link opens it (Universal Link for `pastebridge.app/pair`); if not,
  the page explains what PasteBridge is and links to the App Store. The app's own QR
  scanner accepts the same text, and also `pastebridge://pair?...` with the same fields.
- `n`: the PC's display name, URL-encoded, at most 64 characters.
- `a`: comma-separated `host:port` candidates: the PC's private IPv4 addresses (the one on
  a private network first) and `<computer-name>.local`.
- `f`: the certificate fingerprint. `c`: the pairing code, 16 random bytes, base64url.

The phone then connects to a candidate (TLS, pinned to `f`) and sends:

```
POST /v1/pair
{"code": "<c>", "phone_id": "<uuid>", "phone_name": "Michael's iPhone",
 "platform": "ios", "app_version": "1.0.0"}
```

`200`:
```
{"token": "<43 chars>", "pc_id": "<id>", "pc_name": "DESKTOP-7GH2K1L", "protocol": 1}
```

The bridge shows a notification ("Michael's iPhone is paired"), lists the phone, and makes a
new code for the QR. Pairing the same `phone_id` again replaces its token.

Errors: `403 pairing_code_invalid` (wrong, used or expired), `429 too_many_requests`.

## 5. Requests

All paths start with `/v1/`. JSON is UTF-8. Times are ISO 8601 UTC
(`2026-10-21T15:30:00Z`). Both sides ignore JSON fields they don't know (newer versions
only add fields). Every request but `hello` and `pair` needs the token.

### `GET /v1/hello` (no token)
```
{"app": "pastebridge", "protocol": [1], "pc_id": "<id>", "name": "<display name>"}
```

### Items

Everything that moves is an **item**:

```
{
  "id": "<22 chars>",
  "origin": "pc" | "phone",
  "kind": "text" | "image" | "files",
  "created": "2026-10-21T15:30:00Z",
  "text": "...",              // kind text, when it's 64 KB or less (else fetch the content)
  "size": 1234,               // bytes: the text in UTF-8, the picture, or all files together
  "type": "image/png",        // kind image
  "width": 1920, "height": 1080,   // kind image
  "files": [{"name": "Report.pdf", "size": 1234, "type": "application/pdf"}]  // kind files
}
```

### `GET /v1/clipboard`
What's copied on the PC now, as an item: text if there's text; else a picture (a copied
picture as PNG, or one copied picture file as it is); else copied files (from File
Explorer); `204` when there's nothing usable. The item's `id` stays the same until the PC's
clipboard changes, so the phone can tell whether it already has it.

### `GET /v1/items/{id}/content`
The item's text (`text/plain; charset=utf-8`, line ends `\n`) or picture bytes.

### `GET /v1/items/{id}/files/{index}`
One file of a `files` item, with `Content-Disposition: attachment; filename*=UTF-8''...`.
Supports `Range` (to resume).

### `POST /v1/items`
The phone sends something to the PC.

- Text: `Content-Type: application/json`, body `{"kind": "text", "text": "..."}`.
- A picture or a file: the raw bytes as the body, with
  - `Content-Type`: its type
  - `Content-Length`: required
  - `X-PB-Kind`: `image` or `file`
  - `X-PB-Name`: the file name, percent-encoded UTF-8 (`IMG_0042.jpg`)
  - for several files sent together: `X-PB-Group: <22 chars>` and `X-PB-Group-Count: <n>`

`201` with the stored item plus `"message"`: one sentence for the phone to show, like
"Sent to DESKTOP-7GH2K1L. Paste with Ctrl+V."

What the bridge does:
- Text: onto the clipboard (line ends `\r\n`).
- A picture: saved as sent in `Pictures\PasteBridge\`, then onto the clipboard as a bitmap
  (`CF_DIB`, the right way up by its EXIF orientation, transparency on white), as `PNG` for
  PNG pictures, and as the saved file (`CF_HDROP`, "Preferred DropEffect" = copy). HEIC is
  turned into JPEG by the phone before sending; the bridge answers `415 unsupported` to
  HEIC and to anything it can't open (it opens JPEG, PNG, GIF, WebP and BMP only).
- A file: saved in `Downloads\PasteBridge\` (never overwriting: "name (2).ext"), then onto
  the clipboard as a file. A group goes onto the clipboard together once all its files
  have arrived.
- A notification: "Picture from Michael's iPhone. Press Ctrl+V to paste."

### `GET /v1/outbox` and `POST /v1/outbox/{id}/done`
Items the PC user sent to the phone on purpose ("Send to iPhone" in the bridge: files
dropped on its window, or the hotkey). The phone fetches them when it opens or runs an
action, then marks each done. The outbox keeps an item for 7 days.

### `GET /v1/history?before=<id>&limit=<n>`
Items in both directions, newest first (`limit` up to 100, default 50). The bridge keeps the
last 500 items or 30 days. Texts are kept with the item; pictures and files can be fetched
while their saved files still exist.

### `DELETE /v1/devices/me`
The phone unpairs itself.

## 6. Errors

A JSON body `{"error": "<code>", "message": "<one plain sentence>"}`:

| Status | `error` | When |
| --- | --- | --- |
| 400 | `bad_request` | Missing or malformed fields |
| 401 | `unauthorized` | No token, or not a paired phone (pair again) |
| 403 | `pairing_code_invalid` | Wrong, used or expired pairing code |
| 404 | `not_found` | No such item or file |
| 409 | `nothing_to_send` | Text item with empty text |
| 413 | `too_large` | Over the limits below |
| 415 | `unsupported` | A picture the bridge can't open (HEIC included) |
| 429 | `too_many_requests` | Rate limit; try again in a minute |
| 503 | `clipboard_busy` | Another program holds the clipboard; try again |

## 7. Limits

- Text: 16 MB. A picture: 200 MB. A file: 4 GB.
- Free and Pro are decided on the phone: the bridge doesn't know about purchases. (Pro:
  files, several PCs, history beyond 24 hours.)

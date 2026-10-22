# ClipRoo for Windows

The Windows half of ClipRoo: the "bridge" that the iPhone app talks to
(see `../docs/PROTOCOL.md` and `../docs/PLAN.md`).

## What's here

| Folder | What it is |
| --- | --- |
| `src/ClipRoo.Core` | Everything that isn't Windows-specific: the HTTPS server and every request in the protocol, pairing codes and links, paired phones, history and outbox, file naming, rate limits. Builds and runs on any system. |
| `tests/ClipRoo.Core.Tests` | Tests that start the real server (HTTPS, pinned certificate) on a free port and talk to it like the phone does, with stand-ins for the Windows clipboard, pictures and notifications. |
| `src/ClipRoo.DevBridge` | A stand-in PC for building the iPhone app on a Mac (or anywhere .NET runs): the real server with a pretend clipboard you type into. `dotnet run --project src/ClipRoo.DevBridge` prints the pairing link; type text to "copy" it; what the phone sends is printed. Not shipped. |
| `src/ClipRoo.Windows` | Next: the Windows app itself (tray icon, clipboard, picture decoding, discovery, notifications, start with Windows) and its MSIX package for the Microsoft Store. |

## Build and test

Needs the .NET 10 SDK (`global.json` pins 10.0.100 or a later 10.0 feature band).

```
dotnet test
```

Package versions are locked (`packages.lock.json` in each project) and checked on every
restore.

## How the core fits together

- `Server/Bridge.cs`: the server. Kestrel on every network of the PC, ports 47820 to 47829,
  TLS 1.2/1.3 with the PC's own certificate. Every request but `hello` and `pair` needs a
  phone's token. Answers and errors follow `docs/PROTOCOL.md`.
- `Security/Identity.cs`: the PC's id and its self-signed ECDSA P-256 certificate, made on
  first start and kept (protected by the Windows app with DPAPI). Phones pin its SHA-256.
- `Pairing/Pairing.cs`: the single-use, 10-minute pairing code and the pairing link
  (`https://cliproo.app/pair#v=1&id=...&n=...&a=...&f=...&c=...`).
- `Devices/DeviceStore.cs`: paired phones; only each token's SHA-256 is kept.
- `Items/ItemStore.cs`: history (500 items, 30 days) and outbox (7 days).
- `Items/FileNames.cs`: safe, never-overwriting names for what the phone sends.
- `Server/Addresses.cs`: the addresses for the pairing link.
- `Platform/Platform.cs`: what the Windows app must provide: the clipboard (read; write
  text, picture, files), picture decoding for the clipboard, notifications, folders, DPAPI.

## Notes for the Windows app

- Clipboard calls come from the server's threads; the Windows implementation has to run
  them on the app's STA (UI) thread.
- `IClipboard.Read()`: text if there is text; else a copied picture as PNG; else copied
  files (`CF_HDROP`). Throw `ClipboardBusyException` when the clipboard can't be opened
  within about a second.
- `IClipboard.WritePicture()`: `CF_DIB` from `PreparedPicture.Dib`, `PNG` when there is one,
  and the saved file as `CF_HDROP` with "Preferred DropEffect" = copy (the prototype's
  `app/winclip.py` does the same with ctypes).
- `IPictures.Prepare()`: decode with WIC (JPEG, PNG, GIF, WebP, BMP), apply the EXIF
  orientation, put transparency on white for the bitmap.
- Discovery: announce `_cliproo._tcp` with `DnsServiceRegister` (TXT `v=1`, `id=<pc_id>`)
  on `Bridge.Port` once the server has started.
- The MSIX manifest declares the firewall rule (`windows.firewallRules`, TCP 47820-47829,
  profile `domainAndPrivate`).

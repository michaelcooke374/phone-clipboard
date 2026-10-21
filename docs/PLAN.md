# Plan: from Phone Clipboard to an App Store app

Status: draft, October 2026. The decisions at the end are open until Michael answers them.

Goal: a free iPhone app with a $4.99 lifetime upgrade, plus a free Windows companion in the
Microsoft Store, that moves text, pictures and files between an iPhone and a Windows PC
faster, more reliably and more privately than anything else on the App Store.

The current Phone Clipboard (this repository: a Python program, iPhone Shortcuts and a web
page) stays as the working prototype. Its logic (clipboard formats, picture handling,
security checks) is the reference for the new apps.

---

## 1. The competition (October 2026)

Confidence: [Verified] = read on the project's own GitHub; [Likely] = from search results
and listings that couldn't be opened directly.

| | Cross Paste | Octoclip | KDE Connect | LocalSend |
| --- | --- | --- | --- | --- |
| How it connects | Cloud relay (encrypted), QR or 6-digit code | Local network (Bonjour, PIN pairing, certificates); off-network via your own WebDAV/S3 or Tailscale | Local network (broadcast/mDNS, TLS) | Local network (multicast, HTTPS) |
| Text | Yes | Yes | Yes (text only) | Manual "paste" send |
| Pictures and files | Text-focused [Guessing] | Yes | Files, not clipboard pictures | Yes (its main job) |
| Works without opening the iPhone app | No | Partly: Share Sheet, keyboard, Back Tap shortcuts, a Picture-in-Picture trick | No ("unresponsive in the background is more or less intended") | No (transfers stop when the screen turns off) |
| Price | Free (24 h history, 3 devices); Pro $2.99/month or $19.99/year | Free (1 device, 24 h); $19.99 or $39.99 one-time | Free, open source (GPL) | Free, open source (Apache-2.0) |
| Ads | No | No | No | No |
| App Store rating | 3.0 (2 ratings) | 4.5-4.7 (7-11 ratings) | 4.2 (~278) | ~4.5 (~730) |
| Top complaints | iPhone app didn't work with Windows (wrong download) | Few reviews; Android detection | Can't receive files from PC; clipboard only one way; breaks when switching apps | iPhone not found from Windows; stops with screen off; no background mode |

Sources: [Cross Paste](https://crosspaste.app/), [CrossPaste desktop (a different, open-source product)](https://github.com/CrossPaste/crosspaste-desktop),
[Octoclip pricing](https://octoclip.app/pricing/), [Octoclip iOS limits](https://docs.octoclip.app/advanced/ios/limitations),
[KDE Connect iOS](https://github.com/KDE/kdeconnect-ios), [KDE Connect reviews](https://apps.apple.com/us/app/kde-connect/id1580245991?see-all=reviews&platform=iphone),
[LocalSend](https://github.com/localsend/localsend), [LocalSend background mode](https://github.com/localsend/localsend/issues/1468),
[LocalSend iPhone not found](https://github.com/localsend/localsend/issues/1721).

Also: WinSend (~$13, Shortcuts based), AirDroid ($3.99/month), PairDrop (browser). Intel
Unison shut down in 2025. Apple plans its own iPhone-Windows clipboard for the EU (developer
beta targeted for fall 2027) ([MacRumors](https://www.macrumors.com/2026/08/03/apple-iphone-windows-copy-paste/)).

**What users miss everywhere:**
1. Doing it without opening the iPhone app.
2. The PC finding the iPhone (and the other way round) reliably on Windows: firewall,
   "public" networks, router settings.
3. Text, pictures and files in one app.
4. A fair one-time price (the paid ones are $19.99 or more).
5. A polished Windows app in the Microsoft Store.

---

## 2. How we win

1. **One tap, app closed.** Built-in actions (App Intents) appear by themselves in
   Shortcuts, Siri, Spotlight, Back Tap, the Action button, Control Center and the Lock
   Screen. Nobody builds a shortcut by hand any more (today's three-shortcut setup goes
   away). No competitor found offers Control Center or Action button support [Guessing].
2. **It just connects.** Pair once by scanning a QR code on the PC with the app. After that
   the phone finds the PC by itself (Bonjour), even when its address changes. When it
   can't, a "Can't connect?" screen checks each cause (same Wi-Fi, PC awake, public network,
   firewall, router isolation) and says how to fix it in plain words. The Windows app opens
   its own firewall port from its Store package (no administrator prompts).
3. **Everything in one app.** Text, pictures (HEIC converted automatically) and files of any
   type, both ways, with history on both sides.
4. **Private by design.** Local network only, encrypted (TLS with the PC's certificate
   pinned at pairing), no account, nothing collected: the App Store label can say
   "Data Not Collected".
5. **$4.99 once.** A quarter of Octoclip's price, no subscription.
6. **A real Windows app.** Tray icon, starts with Windows, notifications ("Picture from
   iPhone: press Ctrl+V"), a hotkey, pairing and history, from the Microsoft Store.

Later (after launch), the one thing nobody has: **PC to iPhone with the app closed.** Copy
on the PC, a notification appears on the iPhone ("New from PC, tap to copy"). That needs
Apple's push service and so a small server; the server would only carry a "something is
waiting" signal, never the content, which still travels over the home network. Cost: a few
dollars a month at most [Guessing].

---

## 3. Money: why no ads (recommendation)

Michael's idea was free with ads plus a $5 lifetime purchase. Recommended instead: **free
without ads, plus a $4.99 lifetime Pro upgrade.**

- None of the four competitors shows ads, and the ad-free ones sell on privacy ("no
  tracking, no data collection, no ads"). An ad library makes the App Store privacy label
  list collected data (and usually tracking), next to rivals labelled "Data Not
  Collected" [Likely].
- Clipboard apps are privacy-sensitive: iOS 14 exposed TikTok and 53 other apps reading
  the clipboard ([Sophos](https://www.sophos.com/en-us/blog/ios-14-flags-tiktok-53-other-apps-spying-on-iphone-clipboards)).
- Our best features never open the app (Back Tap, Control Center, Share sheet), so there's
  almost nowhere to show an ad. The income would be small [Guessing].
- Ads add work: Apple's tracking permission prompt, consent screens in Europe, more privacy
  paperwork.
- Fair counterpoint: Send Anywhere (4.7, ~54,600 ratings) carries ads with a $14.99
  "remove ads" purchase, so ads and good ratings can coexist ([AppFollow](https://apps.appfollow.io/ios/send-anywhere-file-transfer/596642855?country=us)).

Proposed split (to decide):

| Free | Pro, $4.99 once |
| --- | --- |
| Text and pictures, both ways | Files of any type and size, and folders |
| One PC | Several PCs |
| All the one-tap actions, Share sheet, widgets | History kept forever (free: last 24 hours), search, pinned items |
| Encrypted, no account | Later: notifications from the PC, use away from home |

The purchase is made in the iPhone app (Apple's in-app purchase). The Windows app stays
free and unlocks nothing by itself, so there's one place to buy and no license system to
build.

---

## 4. How it's built

**iPhone app** (Swift, SwiftUI; iOS 18 or later, because Control Center controls need it;
built with Xcode 26 or later as the App Store requires):
- App Intents: Get from PC, Send to PC, Send picture or file. Control widgets, Lock Screen
  and Home Screen widgets, Siri phrases.
- Share extension: photos (HEIC to JPEG), files, links, text from any app.
- Pairing: in-app QR scanner. The QR holds the PC's address, its certificate fingerprint
  and a one-time pairing code; the phone then gets its own key.
- Discovery: Bonjour (`NSBonjourServices`), with the last known address as a fallback.
  `NSLocalNetworkUsageDescription` and `NSAllowsLocalNetworking` in Info.plist.
- Pasting without permission prompts: `UIPasteControl` inside the app.
- Long transfers: background continued processing (iOS 26) where available.
- StoreKit 2 for the Pro upgrade. No analytics, no ads.

**Windows app** (C#, .NET 10, WinUI 3 or WPF; packaged as MSIX for the Microsoft Store):
- Rewritten from the Python prototype rather than repackaged: no Python to install, a real
  tray app, toast notifications, start with Windows (MSIX startup task), and its firewall
  rule declared in the package (`windows.firewallRules`), so no administrator scripts.
- The same clipboard behaviour as the prototype (text; pictures as bitmap + PNG + file;
  files saved in a folder and put on the clipboard as files).
- Shows the pairing QR, lists paired phones (remove one to revoke it), keeps history.

**Between them** (documented in `docs/PROTOCOL.md` before coding starts):
- HTTPS (TLS 1.3) on the local network. The PC's self-signed certificate is pinned at
  pairing; each phone has its own key, so one phone can be removed without the others.
- The prototype's endpoints, cleaned up: get the PC's clipboard (text, picture or file),
  send to the PC, list and fetch history, a ping for discovery and diagnostics.

**Where the work happens:**
- The iPhone app: a Claude Code session on Michael's Mac (Xcode builds and runs it, and
  TestFlight puts it on his iPhone).
- The Windows app: a Claude Code session on Michael's Windows PC is best (it can build,
  run and test the real clipboard); it can be written in the cloud session, but not run
  there.
- This repository holds the plan, the protocol, and the prototype. The apps get their own
  repositories (or folders here: to decide).

---

## 5. Risks

- **App Review 4.2.3:** "Your app should work on its own without requiring installation of
  another app." Companion apps like Octoclip and KDE Connect are on the store, so it's
  passable [Likely]; the review notes, a demo video and the Microsoft Store link must make
  it easy for the reviewer. Rejection and a resubmission are possible.
- **Unknowns to test early on a real iPhone:** whether a Control Center action can write to
  the clipboard without opening the app; how reliably Bonjour finds Windows PCs on home
  routers.
- **Apple's own EU feature (2027+)** may cover plain text in the EU. Pictures, files,
  history and non-EU users stay ours; we should adopt Apple's API when it ships.
- **Small, crowded category:** ratings come slowly (rivals have few). A good first
  experience (pairing in under a minute) is what earns reviews.

---

## 6. Paperwork (drafted by Claude, submitted by Michael)

- App Store: name, subtitle, keywords, description, screenshots, 1024 px icon, privacy
  policy page and support page (can be free GitHub Pages), App Privacy answers ("Data Not
  Collected"), age rating, encryption export answers, review notes and demo video, the
  in-app purchase (name, description, price), Paid Apps Agreement with tax and bank details
  (needed for the $4.99 upgrade), EU trader status (a seller's address and phone are shown
  publicly in the EU).
- Microsoft Store: Partner Center account (free for individuals), age rating (IARC),
  privacy policy, screenshots, description.

---

## 7. Decisions needed from Michael

1. **Name.** "Phone Clipboard" is too generic for the App Store. App names can't use
   "iPhone" or Apple's feature names (like AirDrop or Handoff). Ideas to check for
   availability: PasteBridge, ClipCourier, Wavepaste.
2. **Ads or not** (recommendation above: no ads, $4.99 Pro).
3. **The free/Pro split** in section 3.
4. **Windows app rewritten in C#** (recommended) or the Python prototype packaged.
5. **iOS 18 or later** as the minimum.
6. **Later: the small server** for PC-to-iPhone notifications (yes/no/decide after launch).

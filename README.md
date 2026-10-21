# Phone Clipboard

Copy text or pictures on your Windows computer and paste them on your iPhone, and the other
way round. It works over your own Wi-Fi: nothing goes through the internet or anyone's
servers.

* **Computer to iPhone:** copy as usual (`Ctrl`+`C`), double-tap the back of the iPhone, paste.
  Works for text and pictures.
* **iPhone to computer:** copy on the iPhone, triple-tap the back of the iPhone, press `Ctrl`+`V`.
  For a picture: in Photos, tap **Share**, then **Send picture to PC**.

Windows and iOS don't do this by themselves: Apple's own copy and paste between devices
only works between Apple devices. Phone Clipboard fills the gap with a small program on the
computer and three shortcuts on the iPhone.

---

## Contents

1. [What you need](#1-what-you-need)
2. [Put it on your computer](#2-put-it-on-your-computer-once)
3. [Set up your iPhone](#3-set-up-your-iphone-once-about-5-minutes)
4. [Every day](#4-every-day)
5. [When something doesn't work](#5-when-something-doesnt-work)
6. [Updating and removing](#6-updating-and-removing)
7. [Privacy and safety](#7-privacy-and-safety)
8. [For helpers and developers](#8-for-helpers-and-developers)

---

## 1. What you need

* A Windows 10 or 11 computer.
* An iPhone with the **Shortcuts** app (it comes with every iPhone; if you deleted it,
  get it again from the App Store).
* Both on **the same Wi-Fi**: your own home, church or office network. (Guest networks and
  public Wi-Fi usually keep devices apart, so it won't work there.)
* An internet connection once, during set-up (it downloads about 30 MB).

---

## 2. Put it on your computer (once)

1. On the computer, go to **github.com/michaelcooke374/phone-clipboard** (sign in to GitHub
   if it asks: the page is private).
2. Click the green **Code** button, then **Download ZIP**.
3. Open your **Downloads** folder. Right-click **phone-clipboard-main.zip** and choose
   **Extract All...**. In the box, type `C:\` and click **Extract**.
   You now have the folder `C:\phone-clipboard-main`.
   (Don't put it on the Desktop or in Documents if OneDrive backs them up.)
4. Open `C:\phone-clipboard-main` and double-click **start.bat**.
   * If Windows asks "Do you want to run this file?", click **Run**.
   * If a blue box says "Windows protected your PC", click **More info**, then **Run anyway**.
     (Windows says this about files downloaded from the internet that it doesn't know yet.)
5. A black window sets things up. If it says Phone Clipboard needs a tool called **uv**,
   press **Enter** to install it. (If you use Ashera Clips, you already have it.)
   Then it downloads Python for Phone Clipboard's own use. This takes a minute or two.
6. Windows asks **"Do you want to allow this app to make changes to your device?"**
   Click **Yes**. This lets your iPhone through the Windows Firewall.
7. If a second window says Windows treats your network as **public**: if it's your own
   home, church or office network, type `Y` and press **Enter**. (Leave public Wi-Fi in a
   cafe or hotel as it is.)
8. Your web browser opens the **Phone Clipboard** page with a square code (a QR code).

From now on Phone Clipboard starts by itself when you sign in to Windows and works quietly
in the background. To see its page again: click **Start**, type **Phone Clipboard**, press
**Enter**.

---

## 3. Set up your iPhone (once, about 5 minutes)

### Open the iPhone page

1. Make sure the iPhone is on the same Wi-Fi as the computer.
2. Open the **Camera** on the iPhone and point it at the code on the computer's Phone
   Clipboard page. Tap the link that appears under it.
3. Safari opens a page called **Phone Clipboard** that says "Connected to your computer".

You can already use this page: **Copy to iPhone** copies the computer's text (a picture
shows on the page: touch and hold it, then tap **Copy** or **Save to Photos**).
**Send to computer** sends what you paste into the box, and **Send pictures...** sends
pictures from your photo library. The shortcuts below make it one tap.

### The address for the shortcuts

On the iPhone page, under **One-tap set-up**, there's an address starting with `http://`.
All the shortcuts use it. Tap **Copy** next to it before each shortcut below.

The same steps are on the iPhone page itself (tap a heading to open it), so you can follow
them there.

### Shortcut 1: Get from PC

1. Tap **Copy** next to the address on the iPhone page.
2. Open the **Shortcuts** app. Tap **+** (top right).
3. Tap **Search Actions**, type `Get Contents of URL` and tap it.
4. Tap the word **URL** in that step, then tap it again and choose **Paste**. Tap **Done**
   on the keyboard.
5. Search again: type `Copy to Clipboard` and tap it.
6. Search again: type `Show Notification` and tap it. Tap its text (**Hello World!**),
   delete it, and type `Copied from PC`.
7. Tap the name at the top (with the small arrow), choose **Rename**, and type
   `Get from PC`. Tap **Done**.
8. Try it: copy some text on the computer, then tap **Get from PC** in Shortcuts. The first
   time, the iPhone asks whether it may connect to your computer: tap **Allow** (or
   **Always Allow**).

It brings pictures too: copy a picture on the computer (or a picture file in File
Explorer), run **Get from PC**, and paste the picture on the iPhone.

### Shortcut 2: Send to PC

1. In Shortcuts, tap **+**.
2. Tap **Search Actions**, type `Get Clipboard` and tap it.
3. Search again: type `Get Contents of URL` and tap it. Tap **URL** and paste the same
   address.
4. Tap the small arrow at the right of that step to show more options. Tap **Method** and
   choose **POST**.
5. Tap **Request Body** and choose **JSON**. Tap **Add new field** and choose **Text**.
   In **Key**, type `text`. Then tap the box next to it (**Text**) and tap **Clipboard** in
   the bar above the keyboard.
6. Search again: type `Show Notification` and tap it. Tap its text, delete it, and tap
   **Contents of URL** in the bar above the keyboard. (Then the notification shows the
   computer's answer, like "Sent to your computer (42 characters)".)
7. Tap the name at the top, choose **Rename**, and type `Send to PC`. Tap **Done**.
8. Try it: copy some text on the iPhone, tap **Send to PC**, then press `Ctrl`+`V` on the
   computer. If the iPhone asks about pasting or connecting, choose **Allow** (or
   **Always Allow**).

So the iPhone stops asking before every paste: open **Settings**, **Apps**, **Shortcuts**,
**Paste from Other Apps**, and choose **Allow**.

### Shortcut 3: Send picture to PC

1. In Shortcuts, tap **+**.
2. Tap the name at the top (with the small arrow), choose **Rename**, and type
   `Send picture to PC`.
3. Tap the name again, choose **Details**, turn on **Show in Share Sheet**, and tap
   **Done**. A first step appears: **Receive Any input from Share Sheet**.
4. In that step, tap **Any**, choose only **Images**, and tap **Done**. Then tap
   **Continue** (after "If there's no input") and choose **Get Clipboard**.
5. Search for `Convert Image` and tap it. If its format isn't **JPEG**, tap the format and
   choose **JPEG**. (iPhone photos are in a format, HEIC, that Windows can't paste.)
6. Search for `Get Contents of URL` and tap it. Tap **URL** and paste the same address.
7. Tap the small arrow at the right of that step. Set **Method** to **POST**. Tap
   **Request Body** and choose **File**. Tap **File** (the blue word) and choose
   **Converted Image**.
8. Search for `Show Notification` and tap it. Tap its text, delete it, and tap
   **Contents of URL** in the bar above the keyboard. Tap **Done**.
9. Try it: in Photos, open a photo, tap **Share**, and choose **Send picture to PC** (scroll
   down the list if needed). Then press `Ctrl`+`V` on the computer.

It also sends a picture you copied on the iPhone: copy it, then run **Send picture to PC**.
One picture at a time; to send several at once, use **Send pictures...** on the iPhone page.

### One tap: the back of the iPhone

1. Open **Settings**, **Accessibility**, **Touch**, and at the bottom **Back Tap**.
2. Tap **Double Tap**, scroll down to **Shortcuts**, and choose **Get from PC**.
3. Go back, tap **Triple Tap**, and choose **Send to PC**.

Other ways to run the shortcuts: the Action button (iPhone 15 Pro and newer: **Settings**,
**Action Button**, **Shortcut**), a button in Control Center, an icon on the Home Screen, or
Siri ("Send to PC").

The menu names above are from recent iOS versions. If one is worded a little differently on
your iPhone, look for the closest match.

---

## 4. Every day

| To do this | Do this |
| --- | --- |
| Copy text or a picture from the computer to the iPhone | Copy on the computer (`Ctrl`+`C`; for a picture: right-click it and choose **Copy**, take a screenshot, or copy a picture file in File Explorer). **Double-tap** the back of the iPhone (or run **Get from PC**). A notification says "Copied from PC". Paste on the iPhone. |
| Copy text from the iPhone to the computer | Copy on the iPhone. **Triple-tap** the back of the iPhone (or run **Send to PC**). A notification says "Sent to your computer". Press `Ctrl`+`V` on the computer. |
| Send a photo from the iPhone to the computer | In Photos, open it, tap **Share**, choose **Send picture to PC**. Press `Ctrl`+`V` on the computer (in a document, an email, a chat, or a folder in File Explorer). |
| Send several photos at once | On the iPhone page (Phone Clipboard on your Home Screen), tap **Send pictures...** and choose them. They all land in **Pictures > Phone Clipboard** on the computer; the last one is ready to paste. |
| Find something the iPhone sent earlier | On the computer, open Phone Clipboard (Start menu). **From your iPhone** lists the last 10 texts and pictures, with a **Copy** button. Pictures stay in **Pictures > Phone Clipboard**. |

Emoji and any language work. Videos and other files aren't sent.

---

## 5. When something doesn't work

First, on the computer, open the Phone Clipboard page (click **Start**, type
**Phone Clipboard**, press **Enter**). If something on the computer is in the way, a yellow
box at the top says what and how to fix it.

| What happens | What to do |
| --- | --- |
| The shortcut says it **can't connect**, or takes long and gives up | Check that the iPhone is on the same Wi-Fi as the computer (not on mobile data, not on a guest network), and that the computer is on and awake. Open the Phone Clipboard page on the computer to make sure it's running. |
| It never worked on this iPhone | On the iPhone, open **Settings**, **Privacy & Security**, **Local Network**, and turn on **Shortcuts** (and **Safari**, if it's listed). |
| The page on the computer says Windows treats your network as **public** | If it's your own network, double-click **setup.bat** in the Phone Clipboard folder and type `Y` when it asks. Or: Windows **Settings**, **Network & internet**, **Wi-Fi** (or **Ethernet**), click your network, choose **Private network**. |
| The page says the **firewall rule is missing** | Double-click **setup.bat** and click **Yes** when Windows asks for permission. |
| You use another security program (Norton, McAfee, Bitdefender...) | It may have its own firewall. In it, allow incoming connections on port 8799 for your home network. |
| The notification says the **key is old** | A new key was made on the computer. Scan the code on the computer's page again with the iPhone's Camera, tap **Copy** next to the address, and paste it into both shortcuts in place of the old address. |
| It **worked before and stopped** | The computer's address may have changed (after a router restart, for example). Scan the code on the computer again and compare the address on the iPhone page with the one in your shortcuts. If it's different, put the new one into both shortcuts. (When the iPhone page can reach the computer by its name, the address uses the name and doesn't change.) |
| The iPhone page says **"Not Secure"** or shows a warning page | The page is on your own network, not the internet. Tap **Visit Website** (or similar). The warning only appears if **Not Secure Connection Warning** is turned on in **Settings**, **Apps**, **Safari**. |
| The iPhone asks for permission before every paste | **Settings**, **Apps**, **Shortcuts**, **Paste from Other Apps**, **Allow**. |
| "Your computer's clipboard has no text or picture" | The computer's clipboard holds something else (like a file that isn't a picture), or nothing. Copy some text or a picture first. |
| A message says **pictures need one more step** | On the computer, double-click **setup.bat** in the Phone Clipboard folder. It adds the part that handles pictures (about 7 MB, once). |
| A message says the photo is in **HEIC** format | In the **Send picture to PC** shortcut, add **Convert Image** (to JPEG) before **Get Contents of URL** (step 5 of Shortcut 3). |
| A picture won't paste into a program on the computer | Some programs only take files: open Phone Clipboard's page and click **Open the pictures folder**, or paste in File Explorer instead. |
| A message says **another program is using port 8799** | Close programs you started recently and try again. If it keeps happening: open `data\settings.json` in the Phone Clipboard folder with Notepad, change `8799` to `18799`, save, double-click **setup.bat**, and put the new address into both shortcuts. |
| The computer page says **Phone Clipboard isn't running** | Click **Start**, type **Phone Clipboard**, press **Enter**. If that doesn't help, double-click **setup.bat**. |

Phone Clipboard keeps a diary in `data\log.txt`: when it started, and when the iPhone
connected (how many letters or how big a picture, never the texts or pictures themselves).

---

## 6. Updating and removing

**To update:** download the zip again (step 2 above), extract it to `C:\` again and choose
**Replace the files in the destination**. Then double-click **setup.bat** (it restarts
Phone Clipboard with the new version, and adds anything new it needs, like the part that
handles pictures). Your key and settings are kept (they're in the `data` folder, which isn't
in the zip), so the iPhone shortcuts keep working.

**To remove:** double-click **uninstall.bat** and click **Yes** when Windows asks. It stops
Phone Clipboard and removes its firewall rule, Start menu entry and automatic start. Then
delete the folder. On the iPhone, delete the shortcuts (and turn off Back Tap if you set it).
Pictures the iPhone sent stay in **Pictures > Phone Clipboard** until you delete them.

---

## 7. Privacy and safety

* **Only your own network.** The computer only lets other devices in on networks Windows
  treats as private (home, church office). On public Wi-Fi it stays closed. Nothing goes
  through the internet or any company's servers.
* **A key keeps strangers out.** Phone Clipboard makes a long random password (the key)
  the first time it starts. It's part of the address your iPhone uses. Other people on the
  same Wi-Fi can't read or change your clipboard without it. If someone else got the
  address, click **Make a new key** on the computer's page and set up the iPhone again.
* **Not encrypted on the Wi-Fi.** The text travels across your Wi-Fi like an ordinary web
  page (http, not https). On your own home network that's fine. On a network many people
  share, someone with special tools could in principle read texts as they pass, so don't
  send passwords that way there.
* **Texts aren't stored.** They're never written to the disk or the log. The last 10 texts
  from the iPhone are kept in memory for the computer's page, until Phone Clipboard stops.
* **Pictures are kept.** Pictures from the iPhone are saved in **Pictures > Phone Clipboard**
  on the computer (many programs can only paste a picture from a file). Delete them there
  when you no longer need them. If your Pictures folder is backed up to OneDrive, they're
  backed up too.

---

## 8. For helpers and developers

### How it works

* `app/phone_clipboard.py` is a small web server (Python standard library, plus Pillow for
  pictures) that listens on port 8799 on every network of the computer (IPv4 and IPv6). It
  runs with `pythonw.exe`, so there's no window.
  * `GET /c/<key>` returns the computer's clipboard: its text (`text/plain`, LF line
    endings), or else its picture: a copied picture as `image/png`, or a copied picture file
    as it is (`image/jpeg`, `image/heic`...). 404 with an explanation when there's neither.
    `?json=1` returns `{"ok", "kind": "text" | "picture" | "none", "text", "has_text"}` (plus
    `"type"` and `"bytes"` for a picture); `?picture=1` returns only a picture. A copied
    picture is turned into PNG once per copy (by the clipboard's sequence number).
  * `POST /c/<key>` puts text on the computer's clipboard (CR LF line endings). The body can
    be JSON (`{"text": ...}`; any capitalisation of `text`, or the only text field), a form
    field `text` (urlencoded or multipart), or plain text. It answers with a sentence for the
    shortcut's notification (`?json=1`: `{"ok", "message"}`).
  * `POST /c/<key>` with a picture (`image/*`, unlabelled picture bytes, or a picture file in
    a multipart form; JPEG, PNG, GIF, WebP or BMP, the only formats it opens) saves it as sent in
    `Pictures\Phone Clipboard\iPhone <date> <time>.<ext>` and puts it on the clipboard as a
    bitmap (`CF_DIB`, turned the right way up by its EXIF orientation, transparency on
    white), as `PNG` (only for PNG pictures) and as the saved file (`CF_HDROP` with
    "Preferred DropEffect" copy). HEIC is refused with a message saying to convert it on
    the iPhone. Bodies up to 60 MB; the key is checked before the body is read.
  * `GET /p/<key>` is the iPhone's page; `GET /` is the computer's page for the computer
    itself and the iPhone's page (asking for the code) for anyone else.
  * `GET /api/ping` says it's Phone Clipboard (`{"app", "version", "name"}`, open to all
    sites so the iPhone page can test the `.local` name).
  * `/pc/status`, `/pc/qr.svg`, `/pc/picture/<id>`, `POST /pc/copy/<id>`,
    `POST /pc/show/<id>`, `POST /pc/open-folder`, `POST /pc/new-key` and `POST /pc/stop`
    answer only this computer: loopback address, a `Host` of localhost/127.0.0.1/::1 (no DNS rebinding), no
    cross-site `Sec-Fetch-Site`, and for changes an `Origin` of the page itself (or none,
    for scripts like uninstall).
  * Keys are compared in constant time; a wrong key waits 0.3 s and is noted on the
    computer's page. Pages carry a strict Content-Security-Policy (no inline scripts or
    styles) and are never cached.
* `app/winclip.py` reads and writes the Windows clipboard with ctypes (text as
  `CF_UNICODETEXT`; pictures as above, several formats in one go) and reads pictures with
  Pillow's `ImageGrab.grabclipboard()`. On other systems it uses a stand-in in memory, for
  testing.
* `app/pictures.py` does the picture work with Pillow: PNG for the iPhone, bitmap for
  Windows, the right way up, saved under a new name (never overwriting).
* `app/requirements.txt` pins Pillow (13.0.0, MIT-CMU license; 12.x has known security problems) with the fingerprints of its
  three Windows files for Python 3.12. setup.bat installs it into `.packages\` with
  `uv pip install --target ... --require-hashes`; the program adds that folder to its path.
  Without it, text works and the pages say to run setup.bat.
* `app/netinfo.py` finds the computer's addresses, and asks PowerShell (once a minute at
  most, with no window) which networks Windows treats as public and whether the firewall
  rule exists, for the warnings on the computer's page.
* `app/qr.py` draws QR codes as SVG (byte mode, error correction M, versions 1 to 20).
* `app/pages/` has the two pages, their script and style, and the icon.
* `app/windows-setup.ps1` does the set-up (see the notes at its top): Python 3.12 from uv
  into `.python\` (`--no-bin --no-registry`, so it doesn't touch the rest of the computer),
  Pillow into `.packages\`,
  shortcuts in the Startup folder and the Start menu (both run `pythonw.exe
  app\phone_clipboard.py`, the Start menu one with `--open`), and, with administrator
  permission, Windows Firewall rules named "Phone Clipboard" for TCP 8799 on private and
  domain networks (one by port, and one per Python program so Windows doesn't ask about it),
  after removing any rules that block that Python (made when someone clicks Cancel on
  Windows' question). It also offers to switch public networks to private.
* `data\settings.json` holds the port and the key; `data\log.txt` the diary;
  `data\setup-done.txt` marks a finished set-up (start.bat runs the set-up until it exists).
* The iPhone page tests whether the computer answers at `<computer name>.local` (Windows
  10 and 11 can answer to that name; the test shows whether they do on this network). If it does, the shortcut address
  uses the name, so it survives the computer getting a new number address.
* `.bat` and `.ps1` files are stored with Windows line endings (`.gitattributes`), since
  cmd.exe misreads labels in batch files with Unix line endings.

### Tests

From the folder, with any Python 3.9 or newer:

```
python -m unittest discover tests
```

They use a stand-in clipboard, so your real clipboard is left alone. The picture tests need
Pillow (`pip install pillow==13.0.0`); to also read the QR codes back with a real decoder:
`pip install zxing-cpp numpy`. Tests whose add-on is missing are skipped.

To try it without Windows: `python app/phone_clipboard.py --port 8799 --data some-folder`
(the clipboard is then a stand-in in memory).

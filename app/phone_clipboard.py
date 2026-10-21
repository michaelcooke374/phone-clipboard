"""Phone Clipboard: copy and paste text and pictures between this Windows computer and an iPhone.

It runs quietly in the background (it starts when you sign in to Windows) and answers on
your own Wi-Fi at http://<this computer>:8799:

  /            this computer only: the set-up page with the QR code for the iPhone, what
               the iPhone sent, and what to fix if the iPhone can't connect
  /p/<key>     the iPhone's page: copy the computer's text or picture, or send some over
  /c/<key>     for the iPhone's Shortcuts (and the page):
                 GET   the computer's clipboard: its text, or else its picture (a copied
                       picture as PNG, or a copied picture file as it is). ?json=1 says
                       which ({"kind": "text" | "picture" | "none"}); ?picture=1 gives only a
                       picture.
                 POST  text (JSON {"text": ...}, a form field "text", or plain text) or a
                       picture (image/*, or a picture file in a multipart form) onto the
                       computer's clipboard. Pictures are also saved in Pictures > Phone Clipboard.
  /api/ping    "is Phone Clipboard here?" (no key needed; says nothing private)

Everything else needs the key: a long random password made on the first start and kept in
data/settings.json. It's part of the link the QR code gives the iPhone, so nobody else on
the same Wi-Fi can read or change the clipboard. The set-up page (which shows the key)
only answers this computer itself.

Clipboard texts are never written to disk or to the log; the last few texts from the
iPhone are kept in memory, for the set-up page, until Phone Clipboard stops. Pictures from
the iPhone are saved (Windows can only paste a picture into some programs from a file).

    pythonw.exe app\\phone_clipboard.py [--open] [--port N] [--data FOLDER]
"""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import logging
import logging.handlers
import os
import re
import secrets
import socket
import socketserver
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from collections import deque
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import netinfo
import pictures
import qr
import winclip

APP = "phone-clipboard"
VERSION = "1.1.0"
ROOT = Path(__file__).resolve().parent.parent
PAGES = Path(__file__).resolve().parent / "pages"
sys.path.append(str(ROOT / ".packages"))        # Pillow, for pictures (setup.bat puts it there)
DEFAULT_PORT = 8799
MAX_BODY = 60_000_000                   # bytes the iPhone may send at once (a big photo)
KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,64}")
STATIC = {"style.css": "text/css; charset=utf-8", "pc.js": "text/javascript; charset=utf-8",
          "phone.js": "text/javascript; charset=utf-8", "icon.png": "image/png", "icon.ico": "image/x-icon"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

NOTHING_COPIED = ("Your computer's clipboard has no text or picture. Copy something on the computer first, "
                  "then try again.")
NO_PICTURES = ("Pictures need one more step on the computer: double-click setup.bat in the Phone Clipboard "
               "folder. (Text works already.)")
TOO_BIG = "That's too big to send (the limit is 60 MB)."
WRONG_KEY = ("This link or shortcut has an old key, so the computer refused it. On the computer, open "
             "Phone Clipboard (Start menu) and set up the iPhone again with the new code.")
BUSY = "Another program on the computer is using the clipboard. Try again in a moment."
EMPTY = "The iPhone's clipboard is empty. Copy some text on the iPhone first, then try again."
NOTHING_SENT = ("No text arrived. If you use the Send to PC shortcut: in its Get Contents of URL step, "
                "Request Body must be JSON, with a Text field called text whose value is Clipboard.")

log = logging.getLogger(APP)


# ---- settings ----------------------------------------------------------------------------

class Settings:
    """data/settings.json: the port and the key. Made on the first start."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.path = self.folder / "settings.json"
        self.port = DEFAULT_PORT
        self.key = ""
        self._load()

    def _load(self) -> None:
        data: dict = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("data/settings.json couldn't be read (%s); made new settings", exc)
            try:
                self.path.replace(self.path.with_name("settings.broken.json"))
            except OSError:
                pass
            data = {}
        port, key = data.get("port"), data.get("key")
        self.port = port if isinstance(port, int) and 1 <= port <= 65535 else DEFAULT_PORT
        self.key = key if isinstance(key, str) and KEY_PATTERN.fullmatch(key) else secrets.token_urlsafe(16)
        if port != self.port or key != self.key:
            self.save()

    def new_key(self) -> None:
        self.key = secrets.token_urlsafe(16)
        self.save()

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        data = {"port": self.port, "key": self.key,
                "about": "port: change it only if another program uses 8799, then double-click setup.bat. "
                         "key: the password in the iPhone's link; Make a new key on the set-up page instead "
                         "of editing it."}
        part = self.path.with_name("settings.json.part")
        part.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        part.replace(self.path)


# ---- line endings ------------------------------------------------------------------------

def for_phone(text: str) -> str:
    """Windows ends lines with CR LF; the iPhone with LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def for_windows(text: str) -> str:
    return for_phone(text).replace("\n", "\r\n")


# ---- what the iPhone sent ------------------------------------------------------------------

def _pick_text(value) -> str | None:
    """The text in a JSON value: the string itself, or the field called "text" (any
    capitals), or the only text field there is."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and k.strip().lower() == "text" and isinstance(v, str):
                return v
        texts = [v for v in value.values() if isinstance(v, str)]
        if len(texts) == 1:
            return texts[0]
    return None


def _decode(body: bytes, charset: str | None = None) -> str:
    if body.startswith((b"\xff\xfe", b"\xfe\xff")):
        return body.decode("utf-16")
    try:
        return body.decode(charset or "utf-8")
    except (LookupError, UnicodeDecodeError):
        return body.decode("utf-8", errors="replace")


def _parts(body: bytes, content_type: str) -> list:
    message = BytesParser(policy=policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1", "replace") + b"\r\n\r\n" + body)
    return list(message.iter_parts()) if message.is_multipart() else []


def picture_in(body: bytes, content_type: str) -> bytes | None:
    """The picture in a request body: the body itself (image/..., or unlabelled picture
    bytes) or a picture file in a multipart form. None when it's text."""
    ctype = content_type.split(";")[0].strip().lower()
    if ctype.startswith("image/"):
        return body
    # Senders that don't say (or say "form", like curl's default): judged by the first bytes.
    if ctype in ("", "application/octet-stream", "application/x-www-form-urlencoded") \
            and pictures.looks_like_picture(body):
        return body
    if ctype == "multipart/form-data":
        for part in _parts(body, content_type):
            payload = part.get_payload(decode=True) or b""
            if part.get_content_type().startswith("image/") or (part.get_filename() and pictures.looks_like_picture(payload)):
                return payload
    return None


def parse_body(body: bytes, content_type: str) -> str | None:
    """The text in a request body: JSON, a form, a multipart form, or plain text."""
    ctype = content_type.split(";")[0].strip().lower()
    charset = None
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    if m:
        charset = m.group(1)
    if ctype == "multipart/form-data":
        parts = _parts(body, content_type)
        named = [p for p in parts if (p.get_param("name", header="content-disposition") or "").lower() == "text"]
        for part in named + parts:
            payload = part.get_payload(decode=True) or b""
            return _decode(payload, part.get_content_charset())
        return None
    if ctype == "application/x-www-form-urlencoded":
        fields = urllib.parse.parse_qs(_decode(body, charset), keep_blank_values=True)
        for name, values in fields.items():
            if name.lower() == "text":
                return values[0]
        return next(iter(fields.values()))[0] if len(fields) == 1 else None
    text = _decode(body, charset)
    if "json" in ctype:
        try:
            return _pick_text(json.loads(text))
        except ValueError:
            return None
    return text


# ---- the server ----------------------------------------------------------------------------

class State:
    """What the pages show, shared by all requests."""

    def __init__(self, settings: Settings, clipboard=winclip, pictures_dir: Path | None = None):
        self.settings = settings
        self.clipboard = clipboard
        self.pictures_dir = pictures_dir or pictures.pictures_folder() / "Phone Clipboard"
        self.lock = threading.Lock()
        self.from_phone: deque[dict] = deque(maxlen=10)     # newest first; pictures keep their "path"
        self._next_id = 1
        self._picture: tuple[int, tuple[bytes, str] | None] | None = None
        self._picture_lock = threading.Lock()
        self.last_phone: dict | None = None
        self.last_refused: dict | None = None
        self.name = netinfo.local_name()
        self._win: dict | None = None
        self._win_time = 0.0
        self._win_lock = threading.Lock()
        self.stop = lambda: None

    def windows(self, fresh: bool = False) -> dict | None:
        """Windows' network and firewall facts, asked at most once a minute (it takes a second)."""
        with self._win_lock:
            if fresh or time.monotonic() - self._win_time > 60:
                self._win = netinfo.windows_status()
                self._win_time = time.monotonic()
            return self._win

    def picture(self) -> tuple[bytes, str] | None:
        """The computer's copied picture for the iPhone, made once per copy (the page asks
        twice: what's there, then the picture itself)."""
        if not pictures.available():
            raise pictures.PicturesUnavailable()
        with self._picture_lock:
            number = self.clipboard.sequence()
            if self._picture is None or self._picture[0] != number:
                try:
                    found = pictures.to_phone(self.clipboard.grab_picture())
                except (OSError, ValueError, SyntaxError) as exc:     # a damaged picture: as if none
                    log.warning("Couldn't read the copied picture: %s", exc)
                    found = None
                self._picture = (number, found)
            return self._picture[1]

    def add(self, entry: dict) -> dict:
        with self.lock:
            entry.update(id=self._next_id, time=time.time())
            self._next_id += 1
            self.from_phone.appendleft(entry)
        return entry

    def entry(self, entry_id: str) -> dict | None:
        with self.lock:
            return next((e for e in self.from_phone if str(e["id"]) == entry_id), None)

    def seen(self, ip: str) -> None:
        with self.lock:
            self.last_phone = {"time": time.time(), "ip": ip}

    def refused(self, ip: str) -> None:
        with self.lock:
            self.last_refused = {"time": time.time(), "ip": ip}


def client_ip(handler: BaseHTTPRequestHandler) -> str:
    ip = str(handler.client_address[0])
    return ip[7:] if ip.startswith("::ffff:") else ip


def host_name(value: str | None) -> str:
    """'localhost:8799' -> 'localhost', '[::1]:8799' -> '::1'."""
    value = (value or "").strip().lower()
    if value.startswith("["):
        return value[1:value.find("]")] if "]" in value else value
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class Handler(BaseHTTPRequestHandler):
    server_version = "PhoneClipboard/" + VERSION
    sys_version = ""
    state: State                                # set on the server's own subclass

    # -- answers --
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Connection", "close")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _text(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data).encode("utf-8"), "application/json")

    def _page(self, name: str) -> None:
        st = self.state
        connect = "'self'" + (f" http://{st.name}:{st.settings.port}" if st.name else "")
        csp = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
               f"connect-src {connect}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self._send(200, (PAGES / name).read_bytes(), "text/html; charset=utf-8", {"Content-Security-Policy": csp})

    def log_message(self, fmt: str, *args) -> None:     # the address holds the key: not logged
        pass

    # -- who is asking --
    def _local(self) -> bool:
        """This computer itself, at its own address (not a web site renamed to point here)."""
        try:
            loopback = ipaddress.ip_address(client_ip(self)).is_loopback
        except ValueError:
            loopback = False
        return loopback and host_name(self.headers.get("Host")) in LOCAL_HOSTS \
            and self.headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")

    def _local_change(self) -> bool:
        """A change from the set-up page itself (or a program on this computer, which sends no Origin)."""
        if not self._local():
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        parts = urllib.parse.urlsplit(origin)
        return parts.scheme == "http" and (parts.hostname or "") in LOCAL_HOSTS \
            and parts.port == self.server.server_address[1]

    def _key_ok(self, key: str) -> bool:
        good = hmac.compare_digest(key.encode("utf-8", "replace"), self.state.settings.key.encode("utf-8"))
        if not good:
            self.state.refused(client_ip(self))
            log.info("Refused a request with a wrong key from %s", client_ip(self))
            time.sleep(0.3)
        return good

    # -- requests --
    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        url = urllib.parse.urlsplit(self.path)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        want_json = query.get("json") == ["1"]
        if path == "/api/ping":
            self._send(200, json.dumps({"app": APP, "version": VERSION, "name": self.state.name}).encode(),
                       "application/json", {"Access-Control-Allow-Origin": "*"})
        elif path.startswith("/c/"):
            if self._key_ok(path[3:].rstrip("/")):
                self._give(want_json, picture_only=query.get("picture") == ["1"])
            else:
                self._fail(403, WRONG_KEY, want_json)
        elif path == "/" or path.startswith("/p/"):
            self._page("pc.html" if path == "/" and self._local() else "phone.html")
        elif path.startswith("/static/") and path[8:] in STATIC:
            self._send(200, (PAGES / path[8:]).read_bytes(), STATIC[path[8:]])
        elif path in ("/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
            name = "icon.ico" if path.endswith(".ico") else "icon.png"
            self._send(200, (PAGES / name).read_bytes(), STATIC[name])
        elif path == "/pc/status" and self._local():
            self._json(200, self._status(fresh=query.get("fresh") == ["1"]))
        elif path.startswith("/pc/picture/") and self._local():
            entry = self.state.entry(path[12:])
            if not entry or entry["kind"] != "picture" or not Path(entry["path"]).is_file():
                return self._text(404, "Not found.")
            ext = Path(entry["path"]).suffix.lower()
            self._send(200, Path(entry["path"]).read_bytes(), pictures.PHONE_TYPES.get(ext, "application/octet-stream"))
        elif path == "/pc/qr.svg" and self._local():
            host = query.get("host", [""])[0]
            self._send(200, qr.svg(self._phone_link(host)).encode("utf-8"), "image/svg+xml")
        else:
            self._text(404, "Not found.")

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        want_json = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("json") == ["1"]
        if path.startswith("/c/"):
            if not self._key_ok(path[3:].rstrip("/")):
                return self._fail(403, WRONG_KEY, want_json)
            body = self._body()
            if body is None:
                return
            picture = picture_in(body, self.headers.get("Content-Type") or "")
            if picture is not None:
                self._take_picture(picture, want_json)
            else:
                self._take_text(body, want_json)
        elif path.startswith("/pc/copy/") and self._local_change():
            self._copy_again(path[9:])
        elif path.startswith("/pc/show/") and self._local_change():
            entry = self.state.entry(path[9:])
            if not entry or entry["kind"] != "picture":
                return self._text(404, "Not found.")
            show_in_folder(Path(entry["path"]))
            self._json(200, {"ok": True})
        elif path == "/pc/open-folder" and self._local_change():
            self.state.pictures_dir.mkdir(parents=True, exist_ok=True)
            show_in_folder(self.state.pictures_dir, select=False)
            self._json(200, {"ok": True})
        elif path == "/pc/new-key" and self._local_change():
            self.state.settings.new_key()
            log.info("Made a new key; old iPhone links and shortcuts no longer work")
            self._json(200, {"ok": True})
        elif path == "/pc/stop" and self._local_change():
            log.info("Stopped from the set-up page")
            self._json(200, {"ok": True})
            threading.Thread(target=self.state.stop, daemon=True).start()
        else:
            self._text(404, "Not found.")

    def _body(self) -> bytes | None:
        """The request body (at most MAX_BODY bytes), or None after answering with an error."""
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            chunks, total = [], 0
            while True:
                line = self.rfile.readline(100)
                try:
                    size = int(line.split(b";")[0].strip() or b"0", 16)
                except ValueError:
                    self._text(400, "The request couldn't be read.")
                    return None
                if size == 0:
                    self.rfile.readline(100)
                    break
                total += size
                if total > MAX_BODY:
                    self._discard(size)
                    self._text(413, TOO_BIG)
                    return None
                chunks.append(self.rfile.read(size))
                self.rfile.readline(100)
            return b"".join(chunks)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._discard(length)
            self._text(413, TOO_BIG)
            return None
        return self.rfile.read(length) if length else b""

    def _discard(self, length: int) -> None:
        """Reads what's being sent without keeping it, so the sender gets the answer (instead
        of a broken connection). Up to 4 times the limit; beyond that the connection just ends."""
        left = min(length, 4 * MAX_BODY) if length > 0 else 0
        while left > 0:
            chunk = self.rfile.read(min(left, 1_000_000))
            if not chunk:
                break
            left -= len(chunk)

    def _fail(self, status: int, message: str, want_json: bool) -> None:
        if want_json:
            self._json(status, {"ok": False, "message": message})
        else:
            self._text(status, message)

    def _give(self, want_json: bool, picture_only: bool = False) -> None:
        """The computer's text, or else its picture."""
        ip = client_ip(self)
        st = self.state
        note = NOTHING_COPIED
        found = None
        try:
            text = "" if picture_only else for_phone(st.clipboard.read_text() or "")
            if not text:
                found = st.picture()
        except winclip.ClipboardBusy:
            return self._fail(503, BUSY, want_json)
        except pictures.PicturesUnavailable:
            note = NOTHING_COPIED + " " + NO_PICTURES
        except OSError as exc:
            log.warning("Couldn't read the clipboard: %s", exc)
            return self._fail(500, BUSY, want_json)
        st.seen(ip)
        if text:
            log.info("Gave %d characters to %s", len(text), ip)
            if want_json:
                return self._json(200, {"ok": True, "kind": "text", "text": text, "has_text": True})
            return self._text(200, text)
        if found:
            data, mime = found
            if want_json:                       # (the page asking what's there: the picture follows)
                return self._json(200, {"ok": True, "kind": "picture", "type": mime, "bytes": len(data),
                                        "text": "", "has_text": False})
            log.info("Gave a picture (%d KB) to %s", len(data) // 1024, ip)
            return self._send(200, data, mime)
        if want_json:
            return self._json(200, {"ok": True, "kind": "none", "text": "", "has_text": False, "message": note})
        self._text(404, note)

    def _take_picture(self, data: bytes, want_json: bool) -> None:
        ip = client_ip(self)
        st = self.state
        st.seen(ip)
        try:
            pic = pictures.from_phone(data)
        except pictures.PicturesUnavailable:
            return self._fail(503, NO_PICTURES, want_json)
        except pictures.NotAPicture as exc:
            return self._fail(400, str(exc), want_json)
        saved = None
        try:
            saved = pictures.save(pic, st.pictures_dir)
        except OSError as exc:
            log.warning("Couldn't save a picture in %s: %s", st.pictures_dir, exc)
        where = f"{st.pictures_dir.parent.name} > {st.pictures_dir.name}"
        try:
            st.clipboard.write_picture(pic.png, pic.dib, str(saved) if saved else None)
        except winclip.ClipboardBusy:
            return self._fail(503, BUSY + (f" The picture is saved in {where}." if saved else ""), want_json)
        except (OSError, MemoryError) as exc:
            log.warning("Couldn't put a picture on the clipboard: %s", exc)
            return self._fail(500, BUSY + (f" The picture is saved in {where}." if saved else ""), want_json)
        if saved:
            st.add({"kind": "picture", "path": str(saved), "name": saved.name,
                    "width": pic.width, "height": pic.height})
        log.info("Took a picture (%d x %d, %d KB) from %s", pic.width, pic.height, len(data) // 1024, ip)
        message = f"Picture sent to your computer ({pic.width} x {pic.height}). Paste there with Ctrl+V."
        if saved:
            message += f" It's also saved in {where}."
        self._json(200, {"ok": True, "message": message}) if want_json else self._text(200, message)

    def _copy_again(self, entry_id: str) -> None:
        """Puts something the iPhone sent earlier back on the computer's clipboard."""
        entry = self.state.entry(entry_id)
        if not entry:
            return self._text(404, "Not found.")
        try:
            if entry["kind"] == "text":
                self.state.clipboard.write_text(for_windows(entry["text"]))
            else:
                pic = pictures.from_phone(Path(entry["path"]).read_bytes())
                self.state.clipboard.write_picture(pic.png, pic.dib, entry["path"])
        except (pictures.PicturesUnavailable, pictures.NotAPicture, winclip.ClipboardBusy, OSError, MemoryError) as exc:
            log.warning("Couldn't copy again: %s", exc)
            return self._json(500, {"ok": False})
        self._json(200, {"ok": True})

    def _take_text(self, body: bytes, want_json: bool) -> None:
        ip = client_ip(self)
        text = parse_body(body, self.headers.get("Content-Type") or "")
        self.state.seen(ip)
        if not text:
            return self._fail(400, EMPTY if text == "" else NOTHING_SENT, want_json)
        try:
            self.state.clipboard.write_text(for_windows(text))
        except winclip.ClipboardBusy:
            return self._fail(503, BUSY, want_json)
        except (OSError, MemoryError) as exc:
            log.warning("Couldn't put text on the clipboard: %s", exc)
            return self._fail(500, BUSY, want_json)
        self.state.add({"kind": "text", "text": for_phone(text)})
        log.info("Took %d characters from %s", len(text), ip)
        n = len(text)
        message = f"Sent to your computer ({n} character{'' if n == 1 else 's'}). Paste there with Ctrl+V."
        self._json(200, {"ok": True, "message": message}) if want_json else self._text(200, message)

    # -- the set-up page's facts --
    def _hosts(self) -> tuple[list[str], dict | None]:
        return netinfo.lan_addresses(), self.state.windows()

    def _phone_link(self, host: str = "") -> str:
        addresses, win = self._hosts()
        if host not in addresses and host != self.state.name:
            host = netinfo.best_address(addresses, win) or "localhost"
        return f"http://{host}:{self.state.settings.port}/p/{self.state.settings.key}"

    def _status(self, fresh: bool = False) -> dict:
        st = self.state
        win = st.windows(fresh=fresh)
        addresses = netinfo.lan_addresses()
        best = netinfo.best_address(addresses, win)
        port, key = st.settings.port, st.settings.key
        nets = (win or {}).get("networks", {})
        with st.lock:
            from_phone = [{k: v for k, v in e.items() if k != "path"} for e in st.from_phone]
            last_phone, last_refused = st.last_phone, st.last_refused
        pictures_ok = pictures.available()
        warnings = []
        if not addresses:
            warnings.append({"title": "This computer isn't connected to a network.",
                             "text": "Connect it to the same Wi-Fi as your iPhone (or plug in its network cable)."})
        if not pictures_ok:
            warnings.append({"title": "Pictures need one more step.",
                             "text": "Double-click setup.bat in the Phone Clipboard folder. It adds the part "
                                     "that handles pictures. Text works already."})
        if win is not None:
            # Only the network the iPhone uses counts (not, say, a virtual network for other programs).
            net = nets.get(best or "", {})
            if net and not netinfo.is_private(net.get("category", "")):
                warnings.append({
                    "title": "Windows treats your network as public, so the iPhone can't reach this computer.",
                    "text": f"Network: {net.get('name') or net.get('adapter')}. If it's your own home, church or office network, "
                            "double-click setup.bat in the Phone Clipboard folder and answer Y when it asks, or "
                            "open Windows Settings, Network & internet, Wi-Fi (or Ethernet), click the network "
                            "and choose Private network."})
            if not win.get("rule"):
                warnings.append({
                    "title": "The Windows Firewall rule for Phone Clipboard is missing.",
                    "text": "Double-click setup.bat in the Phone Clipboard folder and click Yes when Windows "
                            "asks for permission."})
        return {
            "version": VERSION, "computer": netinfo.computer_name(), "name": st.name, "port": port,
            "addresses": [{"ip": ip, **nets.get(ip, {})} for ip in addresses],
            "best": best,
            "phone_link": f"http://{best or 'localhost'}:{port}/p/{key}",
            "shortcut_link": f"http://{best or 'localhost'}:{port}/c/{key}",
            "windows_checked": win is not None,
            "warnings": warnings,
            "from_phone": from_phone,
            "pictures": {"available": pictures_ok, "folder": str(st.pictures_dir)},
            "last_phone": last_phone,
            "last_refused": last_refused,
        }


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, "reuse address" would let two programs share the port. Exclusive use instead.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)    # IPv4 too
        socketserver.TCPServer.server_bind(self)        # (skips a slow name lookup in HTTPServer's)
        self.server_name, self.server_port = "localhost", self.server_address[1]

    def handle_error(self, request, client_address) -> None:
        log.exception("Error while answering %s", client_address[0])


def make_server(state: State, port: int) -> Server:
    """Listens on every network of this computer (IPv4 and IPv6 when possible)."""
    handler = type("BoundHandler", (Handler,), {"state": state})
    if socket.has_dualstack_ipv6():
        try:
            return type("Server6", (Server,), {"address_family": socket.AF_INET6})(("::", port), handler)
        except OSError as exc:
            if getattr(exc, "winerror", None) in (10048, 10013) or exc.errno in (98, 48, 13):
                raise                           # the port is taken: IPv4 alone wouldn't help
    return Server(("0.0.0.0", port), handler)


def show_in_folder(path: Path, select: bool = True) -> None:
    """Opens File Explorer at a file (selected) or a folder."""
    if sys.platform != "win32":
        return
    import subprocess
    if select:
        subprocess.Popen(f'explorer.exe /select,"{path}"')
    else:
        os.startfile(path)                      # noqa: S606 (our own folder)


# ---- starting --------------------------------------------------------------------------------

def already_running(port: int) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # never via a proxy
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/ping", timeout=3) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP
    except (OSError, ValueError):
        return False


def show_problem(title: str, text: str) -> None:
    """A message box (pythonw has no window to print in)."""
    log.error("%s %s", title, text)
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, f"Phone Clipboard: {title}", 0x30)
    else:
        print(f"{title}\n{text}", file=sys.stderr)


def setup_log(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(folder / "log.txt", maxBytes=300_000, backupCount=2,
                                                       encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Copy and paste between this computer and an iPhone.")
    ap.add_argument("--open", action="store_true", help="open the set-up page in the browser")
    ap.add_argument("--port", type=int, help="use this port instead of the one in data/settings.json")
    ap.add_argument("--data", type=Path, default=ROOT / "data", help="folder for settings and the log")
    args = ap.parse_args(argv)
    for name in ("stdout", "stderr"):           # pythonw has none; keep library messages from failing
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))

    setup_log(args.data)
    settings = Settings(args.data)
    port = args.port or settings.port
    settings.port = port
    page = f"http://localhost:{port}/"
    state = State(settings)
    try:
        server = make_server(state, port)
    except OSError:
        if already_running(port):
            if args.open:
                webbrowser.open(page)
            return 0
        show_problem("it couldn't start",
                     f"Another program is already using port {port}. Close programs you started recently "
                     "and try again. If it keeps happening, open data\\settings.json in the Phone Clipboard "
                     "folder with Notepad, change the port to 18799, save, and double-click setup.bat.")
        return 1
    state.stop = server.shutdown
    log.info("Phone Clipboard %s started on port %d (%s)%s", VERSION, port, ", ".join(netinfo.lan_addresses()),
             "" if pictures.available() else "; pictures need setup.bat")
    threading.Thread(target=state.windows, daemon=True).start()     # have the checks ready for the page
    if args.open:
        threading.Timer(0.3, webbrowser.open, (page,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log.info("Phone Clipboard stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())

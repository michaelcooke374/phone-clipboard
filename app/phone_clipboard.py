"""Phone Clipboard: copy and paste text between this Windows computer and an iPhone.

It runs quietly in the background (it starts when you sign in to Windows) and answers on
your own Wi-Fi at http://<this computer>:8799:

  /            this computer only: the set-up page with the QR code for the iPhone, the
               texts the iPhone sent, and what to fix if the iPhone can't connect
  /p/<key>     the iPhone's page: copy the computer's text, or send text to the computer
  /c/<key>     for the iPhone's Shortcuts: GET gives the computer's clipboard text; POST
               (JSON {"text": ...}, a form field "text", or plain text) puts text on it
  /api/ping    "is Phone Clipboard here?" (no key needed; says nothing private)

Everything else needs the key: a long random password made on the first start and kept in
data/settings.json. It's part of the link the QR code gives the iPhone, so nobody else on
the same Wi-Fi can read or change the clipboard. The set-up page (which shows the key)
only answers this computer itself.

Clipboard texts are never written to disk or to the log; the last few texts from the
iPhone are kept in memory, for the set-up page, until Phone Clipboard stops.

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
import qr
import winclip

APP = "phone-clipboard"
VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parent.parent
PAGES = Path(__file__).resolve().parent / "pages"
DEFAULT_PORT = 8799
MAX_BODY = 2_000_000                    # bytes the iPhone may send at once (a long document)
KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,64}")
STATIC = {"style.css": "text/css; charset=utf-8", "pc.js": "text/javascript; charset=utf-8",
          "phone.js": "text/javascript; charset=utf-8", "icon.png": "image/png", "icon.ico": "image/x-icon"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

NO_TEXT = "Your computer's clipboard has no text. Copy some text on the computer first, then try again."
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


def parse_body(body: bytes, content_type: str) -> str | None:
    """The text in a request body: JSON, a form, a multipart form, or plain text."""
    ctype = content_type.split(";")[0].strip().lower()
    charset = None
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    if m:
        charset = m.group(1)
    if ctype == "multipart/form-data":
        message = BytesParser(policy=policy.HTTP).parsebytes(
            b"Content-Type: " + content_type.encode("latin-1", "replace") + b"\r\n\r\n" + body)
        parts = [p for p in message.iter_parts()] if message.is_multipart() else []
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

    def __init__(self, settings: Settings, clipboard=winclip):
        self.settings = settings
        self.clipboard = clipboard
        self.lock = threading.Lock()
        self.from_phone: deque[dict] = deque(maxlen=10)
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
                self._give_text(want_json)
            elif want_json:
                self._json(403, {"ok": False, "message": WRONG_KEY})
            else:
                self._text(403, WRONG_KEY)
        elif path == "/" or path.startswith("/p/"):
            self._page("pc.html" if path == "/" and self._local() else "phone.html")
        elif path.startswith("/static/") and path[8:] in STATIC:
            self._send(200, (PAGES / path[8:]).read_bytes(), STATIC[path[8:]])
        elif path in ("/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
            name = "icon.ico" if path.endswith(".ico") else "icon.png"
            self._send(200, (PAGES / name).read_bytes(), STATIC[name])
        elif path == "/pc/status" and self._local():
            self._json(200, self._status(fresh=query.get("fresh") == ["1"]))
        elif path == "/pc/qr.svg" and self._local():
            host = query.get("host", [""])[0]
            self._send(200, qr.svg(self._phone_link(host)).encode("utf-8"), "image/svg+xml")
        else:
            self._text(404, "Not found.")

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        want_json = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("json") == ["1"]
        if path.startswith("/c/"):
            body = self._body()
            if body is None:
                return
            if not self._key_ok(path[3:].rstrip("/")):
                return self._json(403, {"ok": False, "message": WRONG_KEY}) if want_json else self._text(403, WRONG_KEY)
            self._take_text(body, want_json)
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
                    self._text(413, "That text is too long to send (the limit is about 2 million letters).")
                    return None
                chunks.append(self.rfile.read(size))
                self.rfile.readline(100)
            return b"".join(chunks)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._text(413, "That text is too long to send (the limit is about 2 million letters).")
            return None
        return self.rfile.read(length) if length else b""

    def _give_text(self, want_json: bool) -> None:
        ip = client_ip(self)
        try:
            text = self.state.clipboard.read_text()
        except winclip.ClipboardBusy:
            return self._json(503, {"ok": False, "message": BUSY}) if want_json else self._text(503, BUSY)
        except OSError as exc:
            log.warning("Couldn't read the clipboard: %s", exc)
            return self._json(500, {"ok": False, "message": BUSY}) if want_json else self._text(500, BUSY)
        self.state.seen(ip)
        text = for_phone(text or "")
        log.info("Gave %d characters to %s", len(text), ip)
        if want_json:
            self._json(200, {"ok": True, "text": text, "has_text": bool(text.strip())})
        elif text:
            self._text(200, text)
        else:
            self._text(404, NO_TEXT)

    def _take_text(self, body: bytes, want_json: bool) -> None:
        ip = client_ip(self)
        text = parse_body(body, self.headers.get("Content-Type") or "")
        self.state.seen(ip)
        if not text:
            message = EMPTY if text == "" else NOTHING_SENT
            return self._json(400, {"ok": False, "message": message}) if want_json else self._text(400, message)
        try:
            self.state.clipboard.write_text(for_windows(text))
        except winclip.ClipboardBusy:
            return self._json(503, {"ok": False, "message": BUSY}) if want_json else self._text(503, BUSY)
        except (OSError, MemoryError) as exc:
            log.warning("Couldn't put text on the clipboard: %s", exc)
            return self._json(500, {"ok": False, "message": BUSY}) if want_json else self._text(500, BUSY)
        with self.state.lock:
            self.state.from_phone.appendleft({"time": time.time(), "text": for_phone(text)})
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
            from_phone = list(st.from_phone)
            last_phone, last_refused = st.last_phone, st.last_refused
        warnings = []
        if not addresses:
            warnings.append({"title": "This computer isn't connected to a network.",
                             "text": "Connect it to the same Wi-Fi as your iPhone (or plug in its network cable)."})
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
    log.info("Phone Clipboard %s started on port %d (%s)", VERSION, port, ", ".join(netinfo.lan_addresses()))
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

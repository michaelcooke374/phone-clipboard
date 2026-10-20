"""Tests for Phone Clipboard. Run from the Phone Clipboard folder:

    python -m unittest discover tests

They use a stand-in clipboard, so your real clipboard is left alone. The QR test also reads
the codes back if the zxing-cpp package is installed (pip install zxing-cpp numpy).
"""

from __future__ import annotations

import json
import random
import string
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import netinfo  # noqa: E402
import phone_clipboard as pc  # noqa: E402
import qr  # noqa: E402


class FakeClipboard:
    def __init__(self):
        self.text: str | None = None

    def read_text(self):
        return self.text

    def write_text(self, text):
        self.text = text


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = pc.Settings(Path(self.tmp.name))
        self.clip = FakeClipboard()
        self.state = pc.State(self.settings, clipboard=self.clip)
        self.server = pc.make_server(self.state, 0)
        self.state.stop = self.server.shutdown
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None, method=None, host="127.0.0.1"):
        req = urllib.request.Request(f"http://{host}:{self.port}{path}", data=data, headers=headers or {},
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode("utf-8", "replace"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers

    def key_path(self, extra=""):
        return f"/c/{self.settings.key}{extra}"

    # -- settings --
    def test_settings_made_once_and_kept(self):
        saved = json.loads((Path(self.tmp.name) / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["port"], 8799)
        self.assertRegex(saved["key"], r"^[A-Za-z0-9_-]{22}$")
        self.assertEqual(pc.Settings(Path(self.tmp.name)).key, saved["key"])

    def test_broken_settings_are_replaced(self):
        (Path(self.tmp.name) / "settings.json").write_text("{not json", encoding="utf-8")
        s = pc.Settings(Path(self.tmp.name))
        self.assertRegex(s.key, r"^[A-Za-z0-9_-]{22}$")
        self.assertTrue((Path(self.tmp.name) / "settings.broken.json").exists())

    # -- computer to iPhone --
    def test_get_text_with_windows_line_endings(self):
        self.clip.text = "line 1\r\nline 2 ✓"
        status, body, headers = self.request(self.key_path())
        self.assertEqual((status, body), (200, "line 1\nline 2 ✓"))
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_get_when_clipboard_has_no_text(self):
        status, body, _ = self.request(self.key_path())
        self.assertEqual((status, body), (404, pc.NO_TEXT))
        status, body, _ = self.request(self.key_path("?json=1"))
        self.assertEqual(json.loads(body), {"ok": True, "text": "", "has_text": False})

    # -- iPhone to computer --
    def test_post_json_like_the_shortcut(self):
        status, body, _ = self.request(self.key_path(), json.dumps({"text": "Hi\nthere \U0001F600"}).encode(),
                                       {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertIn("Sent to your computer (10 characters)", body)
        self.assertEqual(self.clip.text, "Hi\r\nthere \U0001F600")
        self.assertEqual(self.state.from_phone[0]["text"], "Hi\nthere \U0001F600")

    def test_post_other_body_kinds(self):
        cases = [
            (b"plain words", {"Content-Type": "text/plain; charset=utf-8"}, "plain words"),
            (b"text=form+words%21", {"Content-Type": "application/x-www-form-urlencoded"}, "form words!"),
            (json.dumps({"Text": "capital key"}).encode(), {"Content-Type": "application/json"}, "capital key"),
            (json.dumps({"anything": "only field"}).encode(), {"Content-Type": "application/json"}, "only field"),
            (b'--XyZ\r\nContent-Disposition: form-data; name="text"\r\n\r\nmulti\r\n--XyZ--\r\n',
             {"Content-Type": "multipart/form-data; boundary=XyZ"}, "multi"),
        ]
        for body, headers, expected in cases:
            with self.subTest(expected=expected):
                status, _, _ = self.request(self.key_path(), body, headers)
                self.assertEqual(status, 200)
                self.assertEqual(self.clip.text, expected)

    def test_post_empty_and_unreadable(self):
        status, body, _ = self.request(self.key_path(), b'{"text": ""}', {"Content-Type": "application/json"})
        self.assertEqual((status, body), (400, pc.EMPTY))
        status, body, _ = self.request(self.key_path(), b'{"number": 5}', {"Content-Type": "application/json"})
        self.assertEqual((status, body), (400, pc.NOTHING_SENT))
        self.assertIsNone(self.clip.text)

    def test_post_too_long(self):
        status, _, _ = self.request(self.key_path(), b"a" * (pc.MAX_BODY + 1), {"Content-Type": "text/plain"})
        self.assertEqual(status, 413)

    # -- the key --
    def test_wrong_key_is_refused(self):
        self.clip.text = "secret"
        status, body, _ = self.request("/c/AAAAAAAAAAAAAAAAAAAAAA")
        self.assertEqual((status, body), (403, pc.WRONG_KEY))
        status, _, _ = self.request("/c/AAAAAAAAAAAAAAAAAAAAAA", b"x", {"Content-Type": "text/plain"})
        self.assertEqual(status, 403)
        self.assertEqual(self.clip.text, "secret")
        self.assertIsNotNone(self.state.last_refused)

    def test_new_key_replaces_the_old_one(self):
        old = self.settings.key
        status, _, _ = self.request("/pc/new-key", b"", method="POST", host="localhost")
        self.assertEqual(status, 200)
        self.assertNotEqual(self.settings.key, old)
        self.assertEqual(self.request(f"/c/{old}")[0], 403)

    # -- what only this computer may see or do --
    def test_setup_page_only_for_this_computer(self):
        status, body, _ = self.request("/", host="localhost")
        self.assertIn("pc.js", body)
        self.assertEqual(self.request("/pc/status", host="localhost")[0], 200)
        # A web site that points its own name at this computer (DNS rebinding) gets the phone page only.
        status, body, _ = self.request("/", headers={"Host": "evil.example"})
        self.assertIn("phone.js", body)
        for path in ("/pc/status", "/pc/qr.svg"):
            self.assertEqual(self.request(path, headers={"Host": "evil.example"})[0], 404)
            self.assertEqual(self.request(path, headers={"Sec-Fetch-Site": "cross-site"}, host="localhost")[0], 404)

    def test_changes_refused_from_other_pages(self):
        old = self.settings.key
        for origin in ("http://evil.example", "http://localhost:1"):
            status, _, _ = self.request("/pc/new-key", b"", {"Origin": origin}, method="POST", host="localhost")
            self.assertEqual(status, 404)
        self.assertEqual(self.settings.key, old)

    def test_status_and_qr(self):
        status, body, _ = self.request("/pc/status", host="localhost")
        data = json.loads(body)
        self.assertEqual(data["port"], self.settings.port)
        self.assertTrue(data["phone_link"].endswith(f"/p/{self.settings.key}"))
        status, body, headers = self.request("/pc/qr.svg", host="localhost")
        self.assertEqual(headers["Content-Type"], "image/svg+xml")
        self.assertTrue(body.startswith("<svg"))

    def test_public_network_warning_only_for_the_iphones_network(self):
        real = netinfo.lan_addresses
        netinfo.lan_addresses = lambda: ["192.168.1.5", "172.20.0.1"]
        try:
            virtual = {"name": "Unidentified network", "adapter": "vEthernet", "category": "Public"}
            self.state.windows = lambda fresh=False: {"rule": True, "networks": {
                "192.168.1.5": {"name": "Home", "adapter": "Wi-Fi", "category": "Private"}, "172.20.0.1": virtual}}
            data = json.loads(self.request("/pc/status", host="localhost")[1])
            self.assertEqual((data["best"], data["warnings"]), ("192.168.1.5", []))
            self.state.windows = lambda fresh=False: {"rule": False, "networks": {
                "192.168.1.5": {"name": "Home", "adapter": "Wi-Fi", "category": "Public"}, "172.20.0.1": virtual}}
            data = json.loads(self.request("/pc/status", host="localhost")[1])
            self.assertEqual(len(data["warnings"]), 2)
            self.assertIn("Network: Home.", data["warnings"][0]["text"])
        finally:
            netinfo.lan_addresses = real

    def test_static_files_and_nothing_else(self):
        for name in pc.STATIC:
            self.assertEqual(self.request(f"/static/{name}")[0], 200)
        self.assertEqual(self.request("/static/../../data/settings.json")[0], 404)
        self.assertEqual(self.request("/static/phone_clipboard.py")[0], 404)

    def test_ping(self):
        status, body, headers = self.request("/api/ping")
        self.assertEqual(json.loads(body)["app"], "phone-clipboard")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertNotIn(self.settings.key, body)

    def test_second_copy_finds_the_first(self):
        self.assertTrue(pc.already_running(self.port))
        with self.assertRaises(OSError):
            pc.make_server(self.state, self.port)


class HelpersTest(unittest.TestCase):
    def test_line_endings(self):
        self.assertEqual(pc.for_windows("a\nb\r\nc\rd"), "a\r\nb\r\nc\r\nd")
        self.assertEqual(pc.for_phone("a\r\nb"), "a\nb")

    def test_host_name(self):
        self.assertEqual(pc.host_name("localhost:8799"), "localhost")
        self.assertEqual(pc.host_name("[::1]:8799"), "::1")
        self.assertEqual(pc.host_name("127.0.0.1"), "127.0.0.1")

    def test_best_address_prefers_private_network(self):
        status = {"networks": {"172.20.0.1": {"category": "Public"}, "192.168.1.5": {"category": "Private"}}}
        self.assertEqual(netinfo.best_address(["172.20.0.1", "192.168.1.5"], status), "192.168.1.5")
        self.assertEqual(netinfo.best_address(["10.0.0.2"], None), "10.0.0.2")
        self.assertIsNone(netinfo.best_address([], None))


class QrTest(unittest.TestCase):
    def test_versions_and_capacity(self):
        self.assertEqual(len(qr.matrix("a")), 21)                       # version 1
        self.assertEqual(len(qr.matrix("x" * 666)), 20 * 4 + 17)        # version 20, level M, full
        with self.assertRaises(ValueError):
            qr.matrix("x" * 667)

    def test_codes_read_back(self):
        try:
            import numpy as np
            import zxingcpp
        except ImportError:
            self.skipTest("zxing-cpp isn't installed")
        rng = random.Random(3)
        for n in [1, 14, 15, 40, 62, 63, 120, 213, 214, 331, 500, 666]:
            text = "".join(rng.choice(string.ascii_letters + string.digits + ":/._-") for _ in range(n))
            rows = qr.matrix(text)
            size = len(rows) + 8
            img = np.full((size, size), 255, np.uint8)
            for y, row in enumerate(rows):
                for x, dark in enumerate(row):
                    if dark:
                        img[y + 4, x + 4] = 0
            img = np.kron(img, np.ones((4, 4), np.uint8))
            found = zxingcpp.read_barcodes(img)
            with self.subTest(n=n):
                self.assertTrue(found and found[0].text == text)


if __name__ == "__main__":
    unittest.main()

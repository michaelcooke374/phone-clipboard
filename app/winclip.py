"""The Windows clipboard: text (any language, emoji included) and pictures.

Uses Windows' own clipboard functions directly. Reading a picture uses Pillow's
ImageGrab (pictures.py needs Pillow anyway). On other systems (only used when testing
the program) a stand-in clipboard kept in memory is used instead.

    text = read_text()          # None when the clipboard holds no text (a picture, a file, nothing)
    write_text("Hello")
    found = grab_picture()      # a Pillow image, a list of copied file names, or None
    write_picture(png, dib, path)
    sequence()                  # changes whenever anything is copied
"""

from __future__ import annotations

import struct
import sys
import threading
import time
from contextlib import contextmanager

_lock = threading.Lock()                # one clipboard job at a time


class ClipboardBusy(Exception):
    """Another program kept the clipboard open for longer than a second."""


def drop_files(paths: list[str]) -> bytes:
    """Copied files, the way File Explorer puts them on the clipboard (CF_HDROP): a
    DROPFILES header (where the names start; wide characters) and the names, each ending
    in a zero, with one more zero at the end."""
    names = "".join(p + "\0" for p in paths) + "\0"
    return struct.pack("<IiiII", 20, 0, 0, 0, 1) + names.encode("utf-16-le")


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    CF_DIB = 8
    CF_UNICODETEXT = 13
    CF_HDROP = 15
    GMEM_MOVEABLE = 0x0002
    DROPEFFECT_COPY = 1

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Exact argument and result types, so 64-bit handles aren't cut short.
    _user32.OpenClipboard.argtypes = [wintypes.HWND]
    _user32.OpenClipboard.restype = wintypes.BOOL
    _user32.CloseClipboard.argtypes = []
    _user32.CloseClipboard.restype = wintypes.BOOL
    _user32.EmptyClipboard.argtypes = []
    _user32.EmptyClipboard.restype = wintypes.BOOL
    _user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    _user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    _user32.GetClipboardData.argtypes = [wintypes.UINT]
    _user32.GetClipboardData.restype = wintypes.HANDLE
    _user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    _user32.SetClipboardData.restype = wintypes.HANDLE
    _user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    _user32.RegisterClipboardFormatW.restype = wintypes.UINT
    _user32.GetClipboardSequenceNumber.argtypes = []
    _user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    _user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.DestroyWindow.restype = wintypes.BOOL
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    _kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalLock.restype = wintypes.LPVOID
    _kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalUnlock.restype = wintypes.BOOL
    _kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalSize.restype = ctypes.c_size_t
    _kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalFree.restype = wintypes.HGLOBAL

    @contextmanager
    def _opened():
        # Windows wants a window to own the clipboard when text is put on it, so a hidden,
        # invisible one is made for the moment and removed again.
        hwnd = _user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, None, None, None, None)
        try:
            deadline = time.monotonic() + 1.0
            while not _user32.OpenClipboard(hwnd):
                if time.monotonic() > deadline:     # another program is holding it
                    raise ClipboardBusy()
                time.sleep(0.02)
            try:
                yield
            finally:
                _user32.CloseClipboard()
        finally:
            if hwnd:
                _user32.DestroyWindow(hwnd)

    def read_text() -> str | None:
        with _lock, _opened():
            if not _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return None
            handle = _user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            pointer = _kernel32.GlobalLock(handle)
            if not pointer:
                return None
            try:
                size = _kernel32.GlobalSize(handle)
                raw = ctypes.string_at(pointer, size - size % 2)
            finally:
                _kernel32.GlobalUnlock(handle)
        text = raw.decode("utf-16-le", errors="replace")
        end = text.find("\0")
        return text if end < 0 else text[:end]

    def _put(items: list[tuple[int, bytes]]) -> None:
        """Replace the clipboard with these formats, all at once (so apps pick the one they like)."""
        handles = []
        try:
            for fmt, data in items:
                handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
                if not handle:
                    raise MemoryError("Windows couldn't make room on the clipboard.")
                handles.append((fmt, handle))
                pointer = _kernel32.GlobalLock(handle)
                if not pointer:
                    raise MemoryError("Windows couldn't make room on the clipboard.")
                ctypes.memmove(pointer, data, len(data))
                _kernel32.GlobalUnlock(handle)
            with _lock, _opened():
                if not _user32.EmptyClipboard():
                    raise ctypes.WinError(ctypes.get_last_error())
                while handles:
                    fmt, handle = handles[0]
                    if not _user32.SetClipboardData(fmt, handle):
                        raise ctypes.WinError(ctypes.get_last_error())
                    handles.pop(0)              # Windows owns it now: it must not be freed
        finally:
            for _fmt, handle in handles:        # the ones Windows didn't take are still ours
                _kernel32.GlobalFree(handle)

    def write_text(text: str) -> None:
        _put([(CF_UNICODETEXT, text.encode("utf-16-le") + b"\0\0")])

    def write_picture(png: bytes | None, dib: bytes, path: str | None) -> None:
        """The picture as a bitmap (for any program), as PNG (programs that keep transparency
        and full quality) and as the saved file (File Explorer, upload boxes, chat programs)."""
        items = [(CF_DIB, dib)]
        if png:
            items.append((_user32.RegisterClipboardFormatW("PNG"), png))
        if path:
            items.append((CF_HDROP, drop_files([path])))
            items.append((_user32.RegisterClipboardFormatW("Preferred DropEffect"),
                          struct.pack("<I", DROPEFFECT_COPY)))
        _put(items)

    def grab_picture():
        from PIL import ImageGrab
        with _lock:
            for _ in range(50):                 # another program may hold the clipboard a moment
                try:
                    return ImageGrab.grabclipboard()
                except OSError:
                    time.sleep(0.02)
        raise ClipboardBusy()

    def sequence() -> int:
        return int(_user32.GetClipboardSequenceNumber())

else:
    _memory: dict = {"text": None, "picture": None, "sequence": 0}

    def read_text() -> str | None:
        with _lock:
            return _memory["text"]

    def write_text(text: str) -> None:
        with _lock:
            _memory.update(text=text, picture=None, sequence=_memory["sequence"] + 1)

    def write_picture(png: bytes | None, dib: bytes, path: str | None) -> None:
        with _lock:
            _memory.update(text=None, picture=[path] if path else None, sequence=_memory["sequence"] + 1)

    def grab_picture():
        with _lock:
            return _memory["picture"]

    def sequence() -> int:
        with _lock:
            return _memory["sequence"]

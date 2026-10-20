"""The Windows clipboard: read and write plain text (any language, emoji included).

Uses Windows' own clipboard functions directly, so nothing extra has to be installed.
On other systems (only used when testing the program) a stand-in clipboard kept in memory
is used instead.

    text = read_text()      # None when the clipboard holds no text (a picture, a file, nothing)
    write_text("Hello")
"""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager

_lock = threading.Lock()                # one clipboard job at a time


class ClipboardBusy(Exception):
    """Another program kept the clipboard open for longer than a second."""


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

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

    def write_text(text: str) -> None:
        data = text.encode("utf-16-le") + b"\0\0"
        handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise MemoryError("Windows couldn't make room for the text.")
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:
            _kernel32.GlobalFree(handle)
            raise MemoryError("Windows couldn't make room for the text.")
        ctypes.memmove(pointer, data, len(data))
        _kernel32.GlobalUnlock(handle)
        try:
            with _lock, _opened():
                if not _user32.EmptyClipboard():
                    raise ctypes.WinError(ctypes.get_last_error())
                if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
                    raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            _kernel32.GlobalFree(handle)        # Windows didn't take it, so it's still ours to free
            raise
        # From here on the text belongs to Windows: it must not be freed.

else:
    _memory: str | None = None

    def read_text() -> str | None:
        with _lock:
            return _memory

    def write_text(text: str) -> None:
        global _memory
        with _lock:
            _memory = text

"""Pictures between the iPhone and this computer.

Uses Pillow (installed into the .packages folder by setup.bat: the exact version in
app/requirements.txt). Without it, text still works and pictures explain what to do.

    available()             Pillow is there
    to_phone(found)         what winclip.grab_picture() found -> (bytes, type) to send, or None
    from_phone(data)        a picture the iPhone sent -> Picture, ready for the clipboard
    save(picture, folder)   keeps it in a file -> the file's path
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from pathlib import Path

# Picture files the iPhone shows as they are; others are turned into PNG first.
PHONE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
               ".heic": "image/heic", ".heif": "image/heif", ".webp": "image/webp"}
CONVERT = {".bmp", ".dib"}
# The only formats opened at all: what iPhones and the clipboard actually carry. (Pillow can
# read dozens more; the rarely used ones are where its security problems tend to be.)
EXTENSIONS = {"JPEG": ".jpg", "MPO": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp", "BMP": ".bmp"}
FORMATS = ["JPEG", "PNG", "GIF", "WEBP", "BMP"]           # (iPhone "MPO" photos open as JPEG)
MAX_FILE = 60_000_000

HEIC = ("This photo is in Apple's HEIC format, which Windows can't paste. In the Send picture to PC "
        "shortcut, add Convert Image (to JPEG) before Get Contents of URL.")
NOT_A_PICTURE = "That isn't a picture the computer can open (JPEG, PNG, GIF, WebP or BMP)."


class PicturesUnavailable(Exception):
    """Pillow isn't installed (setup.bat installs it)."""


class NotAPicture(Exception):
    """What arrived can't be opened as a picture. The message says why, in plain words."""


@dataclass
class Picture:
    data: bytes             # exactly as the iPhone sent it (this is what's saved)
    ext: str                # ".jpg", ".png", ...
    png: bytes | None       # for programs that take PNG from the clipboard (pictures that are PNG anyway)
    dib: bytes              # the classic Windows bitmap every program can paste
    width: int
    height: int


def _pil():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise PicturesUnavailable() from exc
    return Image, ImageOps


def available() -> bool:
    try:
        _pil()
        return True
    except PicturesUnavailable:
        return False


def looks_like_picture(data: bytes) -> bool:
    """By its first bytes, for senders that don't say what they send."""
    head = data[:18]
    bmp = head[:2] == b"BM" and len(head) == 18 and int.from_bytes(head[14:18], "little") in (12, 40, 52, 56, 108, 124)
    return (head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"II*\0", b"MM\0*"))
            or bmp or (head[:4] == b"RIFF" and head[8:12] == b"WEBP") or head[4:8] == b"ftyp")


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=3)
    return buf.getvalue()


def _for_png(img):
    """Modes PNG can hold. A screenshot's bitmap often says "transparent" for every dot
    (Windows leaves that part empty): that one is made solid."""
    if img.mode in ("RGBA", "LA") and img.getchannel("A").getextrema() == (0, 0):
        return img.convert("RGB")
    if img.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "I;16"):
        has_alpha = "A" in img.getbands() or "transparency" in img.info
        return img.convert("RGBA" if has_alpha else "RGB")
    return img


def to_phone(found) -> tuple[bytes, str] | None:
    """The computer's copied picture, ready for the iPhone: a copied picture as PNG, or a
    copied picture file (from File Explorer) as it is."""
    if found is None:
        return None
    Image, _ = _pil()
    if isinstance(found, list):
        for name in found:
            path = Path(name)
            ext = path.suffix.lower()
            try:
                if not path.is_file() or path.stat().st_size > MAX_FILE:
                    continue
                if ext in PHONE_TYPES:
                    return path.read_bytes(), PHONE_TYPES[ext]
                if ext in CONVERT:
                    with Image.open(path, formats=FORMATS) as img:
                        return _png(_for_png(img)), "image/png"
            except OSError:
                continue
        return None
    return _png(_for_png(found)), "image/png"


def from_phone(data: bytes) -> Picture:
    Image, ImageOps = _pil()
    try:
        img = Image.open(io.BytesIO(data), formats=FORMATS)
        img.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        if data[4:8] == b"ftyp":
            raise NotAPicture(HEIC) from exc
        raise NotAPicture(NOT_A_PICTURE) from exc
    ext = EXTENSIONS.get((img.format or "").upper())
    if not ext:
        raise NotAPicture(NOT_A_PICTURE)
    # iPhone photos are often stored sideways with a note saying which way is up.
    turned = img if img.getexif().get(0x0112, 1) in (None, 1) else ImageOps.exif_transpose(img)
    has_alpha = "A" in turned.getbands() or "transparency" in turned.info
    shown = turned.convert("RGBA" if has_alpha else "RGB")
    if has_alpha:
        flat = Image.new("RGB", shown.size, (255, 255, 255))
        flat.paste(shown, mask=shown.getchannel("A"))
    else:
        flat = shown
    bmp = io.BytesIO()
    flat.save(bmp, "BMP")
    # PNG on the clipboard only for pictures that are PNG anyway (screenshots, graphics): for
    # photos it would only be slow and big; the bitmap and the saved file cover them.
    if ext == ".png":
        png = data if turned is img else _png(shown)
    else:
        png = None
    return Picture(data=data, ext=ext, png=png, dib=bmp.getvalue()[14:], width=flat.width, height=flat.height)


def save(picture: Picture, folder: Path, when: float | None = None) -> Path:
    """Saves the picture as the iPhone sent it: "iPhone 2026-10-21 14.03.22.jpg"."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H.%M.%S", time.localtime(when))
    path = folder / f"iPhone {stamp}{picture.ext}"
    n = 2
    while path.exists():
        path = folder / f"iPhone {stamp} ({n}){picture.ext}"
        n += 1
    part = path.with_name(path.name + ".part")
    part.write_bytes(picture.data)
    part.replace(path)
    return path


def pictures_folder() -> Path:
    """Windows' Pictures folder (wherever it was moved to, OneDrive included)."""
    import sys
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        import uuid

        class GUID(ctypes.Structure):
            _fields_ = [("data", ctypes.c_ubyte * 16)]

        folder_id = GUID()
        folder_id.data[:] = uuid.UUID("33E28130-4E1E-4676-835A-98395C3BC3BB").bytes_le   # FOLDERID_Pictures
        out = ctypes.c_wchar_p()
        shell32 = ctypes.WinDLL("shell32")
        ole32 = ctypes.WinDLL("ole32")
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                                 ctypes.POINTER(ctypes.c_wchar_p)]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(out)) == 0:
            try:
                return Path(out.value)
            finally:
                ole32.CoTaskMemFree(ctypes.cast(out, ctypes.c_void_p))
    return Path.home() / "Pictures"

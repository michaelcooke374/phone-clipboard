"""QR codes, drawn as SVG pictures (for the set-up page on the computer).

The iPhone's Camera reads the code and opens the link in it, so nobody has to type a long
address. Byte mode, error correction level M (a smudged or partly covered code still reads),
versions 1 to 20 (up to 666 bytes, far more than a link needs). The method follows
the QR standard (ISO/IEC 18004) as explained by Project Nayuki.

Usage:
    svg = qr.svg("http://192.168.1.20:8799/p/abc")
"""

from __future__ import annotations

# Level M, per version (index 0 unused): error-correction bytes per block, number of blocks.
_ECC_PER_BLOCK = (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26)
_BLOCKS = (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16)
_MAX_VERSION = 20
_FORMAT_M = 0                                   # the two bits that mean "level M"

_MASKS = (
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
)


def _raw_modules(ver: int) -> int:
    """How many squares of a version hold data and error correction (not fixed patterns)."""
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        align = ver // 7 + 2
        n -= (25 * align - 10) * align - 55
        if ver >= 7:
            n -= 36
    return n


def _data_bytes(ver: int) -> int:
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ver] * _BLOCKS[ver]


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _codewords(data: bytes) -> tuple[int, list[int]]:
    """Pick the smallest version that fits, and return it with the final byte sequence
    (data, padding and error correction, interleaved as the standard says)."""
    for ver in range(1, _MAX_VERSION + 1):
        count_bits = 8 if ver <= 9 else 16
        if 4 + count_bits + 8 * len(data) <= _data_bytes(ver) * 8:
            break
    else:
        raise ValueError(f"Too much text for a QR code ({len(data)} bytes).")
    capacity = _data_bytes(ver) * 8
    bits: list[int] = []

    def put(value: int, n: int) -> None:
        bits.extend((value >> i) & 1 for i in reversed(range(n)))

    put(0b0100, 4)                              # byte mode
    put(len(data), count_bits)
    for b in data:
        put(b, 8)
    put(0, min(4, capacity - len(bits)))        # terminator
    put(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < capacity:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    blocks_n, ecc_len = _BLOCKS[ver], _ECC_PER_BLOCK[ver]
    raw = _raw_modules(ver) // 8
    short_n = blocks_n - raw % blocks_n
    short_len = raw // blocks_n
    divisor = _rs_divisor(ecc_len)
    blocks: list[list[int]] = []
    k = 0
    for i in range(blocks_n):
        size = short_len - ecc_len + (0 if i < short_n else 1)
        block = words[k:k + size]
        k += size
        ecc = _rs_remainder(block, divisor)
        if i < short_n:
            block.append(0)                     # placeholder, skipped when interleaving
        blocks.append(block + ecc)
    out: list[int] = []
    for i in range(len(blocks[0])):
        for j, block in enumerate(blocks):
            if i != short_len - ecc_len or j >= short_n:
                out.append(block[i])
    return ver, out


class _Grid:
    def __init__(self, ver: int):
        self.ver = ver
        self.size = ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set_fixed(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def alignment_positions(self) -> list[int]:
        if self.ver == 1:
            return []
        n = self.ver // 7 + 2
        step = (self.ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
        return list(reversed([self.size - 7 - i * step for i in range(n - 1)] + [6]))

    def draw_patterns(self) -> None:
        size = self.size
        for i in range(size):                   # timing lines
            self.set_fixed(6, i, i % 2 == 0)
            self.set_fixed(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):     # the three big corner squares
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self.set_fixed(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = self.alignment_positions()
        last = len(pos) - 1
        for i, ax in enumerate(pos):
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set_fixed(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)                     # reserves the format areas; redrawn later
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = size - 11 + i % 3, i // 3
                self.set_fixed(a, b, bit)
                self.set_fixed(b, a, bit)

    def draw_format(self, mask: int) -> None:
        data = _FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1    # noqa: E731
        size = self.size
        for i in range(6):
            self.set_fixed(8, i, bit(i))
        self.set_fixed(8, 7, bit(6))
        self.set_fixed(8, 8, bit(7))
        self.set_fixed(7, 8, bit(8))
        for i in range(9, 15):
            self.set_fixed(14 - i, 8, bit(i))
        for i in range(8):
            self.set_fixed(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set_fixed(8, size - 15 + i, bit(i))
        self.set_fixed(8, size - 8, True)       # always dark

    def draw_data(self, words: list[int]) -> None:
        size = self.size
        i, total = 0, len(words) * 8
        right = size - 1
        while right >= 1:
            if right == 6:                      # the vertical timing line is skipped
                right = 5
            for vert in range(size):
                for j in range(2):
                    x = right - j
                    upward = (right + 1) & 2 == 0
                    y = size - 1 - vert if upward else vert
                    if not self.fixed[y][x] and i < total:
                        self.dark[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        test = _MASKS[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and test(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        """How hard this pattern is for a camera to read (lower is better)."""
        size, grid = self.size, self.dark
        score = 0
        lines = [row for row in grid] + [[grid[y][x] for y in range(size)] for x in range(size)]
        finder_a = [True, False, True, True, True, False, True, False, False, False, False]
        finder_b = finder_a[::-1]
        for line in lines:
            run = 1
            for k in range(1, size + 1):
                if k < size and line[k] == line[k - 1]:
                    run += 1
                    continue
                if run >= 5:
                    score += 3 + run - 5
                run = 1
            for k in range(size - 10):
                window = line[k:k + 11]
                if window == finder_a or window == finder_b:
                    score += 40
        for y in range(size - 1):
            for x in range(size - 1):
                c = grid[y][x]
                if c == grid[y][x + 1] == grid[y + 1][x] == grid[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in grid)
        total = size * size
        score += abs(dark * 20 - total * 10) // total * 10
        return score


def matrix(text: str) -> list[list[bool]]:
    """The QR code for `text` (UTF-8) as rows of squares, True = dark. No quiet margin."""
    ver, words = _codewords(text.encode("utf-8"))
    best: _Grid | None = None
    best_score = 0
    for mask in range(8):
        grid = _Grid(ver)
        grid.draw_patterns()
        grid.draw_data(words)
        grid.apply_mask(mask)
        grid.draw_format(mask)
        score = grid.penalty()
        if best is None or score < best_score:
            best, best_score = grid, score
    assert best is not None
    return best.dark


def svg(text: str, margin: int = 4) -> str:
    """The QR code for `text` as an SVG picture: black squares on white, with the quiet
    margin cameras need around it. It scales to any size (set its width in the page)."""
    rows = matrix(text)
    n = len(rows) + 2 * margin
    path = "".join(f"M{x + margin},{y + margin}h1v1h-1z"
                   for y, row in enumerate(rows) for x, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges" '
            f'role="img" aria-label="QR code"><rect width="{n}" height="{n}" fill="#fff"/>'
            f'<path d="{path}" fill="#000"/></svg>')

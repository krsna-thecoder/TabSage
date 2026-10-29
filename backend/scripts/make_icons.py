"""Generate TabSage extension icons (16/48/128 px) with no third-party deps.

Writes PNGs to ../../extension/icons/. This is dev tooling and is NOT part of
the shipped extension (only extension/ is zipped for the Store).

Design: an indigo rounded square with a white "T". Simple, legible at 16px.

Run (from backend/, venv active):
    python scripts/make_icons.py
"""
from __future__ import annotations

import os
import struct
import zlib

_ICON_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "extension", "icons")
)

BRAND = (27, 27, 27)    # charcoal (matches the in-UI brand badge)
WHITE = (255, 255, 255)


def _png(path: str, size: int, pixels: list[tuple[int, int, int, int]]) -> None:
    """Encode an RGBA pixel list (row-major) as a PNG file."""
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # filter type 0 (none) per scanline
        for x in range(size):
            r, g, b, a = pixels[y * size + x]
            rows.extend((r, g, b, a))
    compressed = zlib.compress(bytes(rows), 9)

    def chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    with open(path, "wb") as f:
        f.write(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b""))


def _in_rounded_rect(x: int, y: int, size: int, radius: float) -> bool:
    """True if (x,y) is inside a rounded square of side `size`."""
    r = radius
    # distances from the nearest corner centers
    cx = min(max(x + 0.5, r), size - r)
    cy = min(max(y + 0.5, r), size - r)
    dx = (x + 0.5) - cx
    dy = (y + 0.5) - cy
    return dx * dx + dy * dy <= r * r


def _in_tee(x: int, y: int, size: int) -> bool:
    """True if (x,y) falls on the white 'T' glyph."""
    fx = (x + 0.5) / size
    fy = (y + 0.5) / size
    top_bar = (0.22 <= fx <= 0.78) and (0.24 <= fy <= 0.38)
    stem = (0.44 <= fx <= 0.56) and (0.24 <= fy <= 0.80)
    return top_bar or stem


def make(size: int) -> None:
    radius = size * 0.22
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            if not _in_rounded_rect(x, y, size, radius):
                pixels.append((0, 0, 0, 0))  # transparent outside the square
            elif _in_tee(x, y, size):
                pixels.append((*WHITE, 255))
            else:
                pixels.append((*BRAND, 255))
    os.makedirs(_ICON_DIR, exist_ok=True)
    path = os.path.join(_ICON_DIR, f"icon{size}.png")
    _png(path, size, pixels)
    print(f"wrote {path} ({size}x{size})")


def main() -> int:
    for size in (16, 48, 128):
        make(size)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

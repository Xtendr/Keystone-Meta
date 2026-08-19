#!/usr/bin/env python3
"""Generate an original 64x64 TGA mark for Keystone Meta. Not a Cutoffs asset."""

from __future__ import annotations

import math
import struct
from pathlib import Path


def clamp(value: float) -> int:
    return max(0, min(255, int(value)))


def main() -> None:
    size = 64
    pixels = []
    cx = (size - 1) / 2
    cy = (size - 1) / 2
    for y in range(size):
        row = []
        for x in range(size):
            dx = (x - cx) / 22.0
            dy = (y - cy) / 22.0
            diamond = abs(dx) + abs(dy)
            inside = diamond <= 1.05
            edge = 0.86 <= diamond <= 1.05
            pulse = abs((x - 18) / 28.0 * math.sin((x + y) / 7.0) + (32 - y) / 18.0)
            r = g = b = 8
            a = 0
            if inside:
                a = 255
                glow = max(0.0, 1.0 - diamond)
                r = 16 + 40 * glow
                g = 28 + 90 * glow
                b = 36 + 110 * glow
                if pulse < 0.18:
                    r, g, b = 185, 236, 255
                if edge:
                    r, g, b = 197, 155, 82
            row.append((clamp(b), clamp(g), clamp(r), a))
        pixels.append(row)

    header = struct.pack(
        "<BBBHHBHHHHBB",
        0, 0, 2, 0, 0, 0, 0, 0, size, size, 32, 8,
    )
    body = bytearray()
    for y in range(size):
        for x in range(size):
            body.extend(pixels[y][x])
    path = Path(__file__).with_name("KeystoneMeta_logo.tga")
    path.write_bytes(header + body)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
